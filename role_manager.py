"""
Role-syncing logic: given ROLE_GRANT_RULES in config.py, grant or remove
roles on guild members so their roles always match what they're currently
eligible for.
"""

import asyncio
import time
from collections import defaultdict

import discord

from config import (
    ROLE_GRANT_RULES,
    SWEEP_DELAY_BETWEEN_MEMBERS_SECONDS,
    ROLE_UPDATE_COOLDOWN_SECONDS,
)
from logging_utils import log_to_discord
from bot_instance import get_bot

# True while a full-guild sweep is running. The on_member_update event
# handler skips processing while this is True, since the sweep itself
# triggers role-change events we don't need to react to individually.
is_sweep_in_progress = False

# Tracks the last time (unix timestamp) we processed a role-change event
# for each member, keyed by member ID, so rapid-fire Discord role update
# events for the same member get debounced.
_last_role_update_timestamp_by_member_id = defaultdict(float)


def _member_qualifies_for_rule(member_role_names, rule):
    """A member qualifies for a rule if they hold every role in at least
    one of the rule's required role groups."""
    return any(
        all(required_role_name in member_role_names for required_role_name in role_group)
        for role_group in rule["granted_if_member_has_any_of_these_role_groups"]
    )


async def apply_role_rules_to_member(member):
    """Grant/remove roles on a single member according to ROLE_GRANT_RULES.
    Returns True if any role was actually added or removed."""
    guild = member.guild
    member_role_names = [role.name for role in member.roles]
    did_change_a_role = False

    for rule in ROLE_GRANT_RULES:
        role_to_grant_name = rule["grants_role_named"]
        role_to_grant = discord.utils.get(guild.roles, name=role_to_grant_name)

        if not role_to_grant:
            await log_to_discord(f"❌ Role '{role_to_grant_name}' not found.")
            continue

        member_qualifies = _member_qualifies_for_rule(member_role_names, rule)
        member_already_has_role = role_to_grant in member.roles

        if member_qualifies and not member_already_has_role:
            try:
                await member.add_roles(role_to_grant)
                await log_to_discord(f"➕ Gave **{role_to_grant.name}** to **{member.display_name}**")
                did_change_a_role = True
            except Exception as error:
                await log_to_discord(f"❌ Could not add {role_to_grant.name} to {member.display_name}: {error}")

        elif not member_qualifies and member_already_has_role:
            try:
                await member.remove_roles(role_to_grant)
                await log_to_discord(f"➖ Removed **{role_to_grant.name}** from **{member.display_name}**")
                did_change_a_role = True
            except Exception as error:
                await log_to_discord(f"❌ Could not remove {role_to_grant.name} from {member.display_name}: {error}")

    return did_change_a_role


async def sweep_all_guild_members():
    """Re-check every member in the bot's (first) guild against
    ROLE_GRANT_RULES."""
    global is_sweep_in_progress
    is_sweep_in_progress = True
    members_changed_count = 0
    bot = get_bot()

    try:
        if not bot.guilds:
            await log_to_discord("❌ Bot is not in any servers.")
            return

        guild = bot.guilds[0]
        members = guild.members
        await log_to_discord(f"🔍 Sweeping {len(members)} members...")

        for member in members:
            member_was_changed = await apply_role_rules_to_member(member)
            if member_was_changed:
                members_changed_count += 1
            await asyncio.sleep(SWEEP_DELAY_BETWEEN_MEMBERS_SECONDS)
    finally:
        is_sweep_in_progress = False
        await log_to_discord(f"✅ Sweep completed. {members_changed_count} members had roles changed.")


async def handle_member_role_update(member_before, member_after):
    """Called from the on_member_update event. Debounces rapid updates and
    re-applies role rules when a member's roles actually changed."""
    if is_sweep_in_progress:
        return

    if set(member_before.roles) == set(member_after.roles):
        return  # No role change, nothing to do.

    now = time.time()
    member_id = member_after.id
    if now - _last_role_update_timestamp_by_member_id[member_id] < ROLE_UPDATE_COOLDOWN_SECONDS:
        return
    _last_role_update_timestamp_by_member_id[member_id] = now

    await asyncio.sleep(1.5)  # Let Discord finish processing the role change.
    await apply_role_rules_to_member(member_after)