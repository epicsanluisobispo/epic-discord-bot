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
from logging_utils import log_to_discord, log_error_to_discord
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
    one of the rule's required role groups, AND — if the rule specifies
    `excluded_if_member_has_any_of_these_roles` — they don't hold any of
    those excluded roles. The exclusion list is optional; rules without it
    behave exactly as before."""
    member_qualifies_via_groups = any(
        all(required_role_name in member_role_names for required_role_name in role_group)
        for role_group in rule["granted_if_member_has_any_of_these_role_groups"]
    )
    if not member_qualifies_via_groups:
        return False

    excluded_role_names = rule.get("excluded_if_member_has_any_of_these_roles", [])
    if any(excluded_role_name in member_role_names for excluded_role_name in excluded_role_names):
        return False

    return True


async def apply_role_rules_to_member(member):
    """Grant/remove roles on a single member according to ROLE_GRANT_RULES.
    Returns True if any role was actually added or removed.

    All roles that need adding are applied in a single add_roles(...) call,
    and all roles that need removing in a single remove_roles(...) call —
    at most 2 Discord API calls per member no matter how many individual
    roles changed, instead of one call per role. This is both faster and
    much friendlier to Discord's rate limits during a full guild sweep.
    """
    guild = member.guild
    member_role_names = [role.name for role in member.roles]

    roles_to_add = []
    roles_to_remove = []

    for rule in ROLE_GRANT_RULES:
        role_to_grant_name = rule["grants_role_named"]
        role_to_grant = discord.utils.get(guild.roles, name=role_to_grant_name)

        if not role_to_grant:
            await log_error_to_discord(f"❌ Role '{role_to_grant_name}' not found.")
            continue

        member_qualifies = _member_qualifies_for_rule(member_role_names, rule)
        member_already_has_role = role_to_grant in member.roles

        if member_qualifies and not member_already_has_role:
            roles_to_add.append(role_to_grant)
        elif not member_qualifies and member_already_has_role:
            roles_to_remove.append(role_to_grant)

    did_change_a_role = False

    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add)
            for role in roles_to_add:
                await log_to_discord(f"➕ Gave **{role.name}** to **{member.display_name}**")
            did_change_a_role = True
        except Exception as error:
            role_names_text = ", ".join(role.name for role in roles_to_add)
            await log_error_to_discord(
                f"❌ Could not add roles ({role_names_text}) to {member.display_name}: {error}"
            )

    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove)
            for role in roles_to_remove:
                await log_to_discord(f"➖ Removed **{role.name}** from **{member.display_name}**")
            did_change_a_role = True
        except Exception as error:
            role_names_text = ", ".join(role.name for role in roles_to_remove)
            await log_error_to_discord(
                f"❌ Could not remove roles ({role_names_text}) from {member.display_name}: {error}"
            )

    return did_change_a_role


async def sweep_all_guild_members():
    """Re-check every member in the bot's (first) guild against
    ROLE_GRANT_RULES. Only pauses after a member whose roles actually
    changed (an API call was made) — members needing no changes are
    checked back-to-back with no delay, since that check itself makes no
    Discord API call and can't trigger a rate limit."""
    global is_sweep_in_progress
    is_sweep_in_progress = True
    members_changed_count = 0
    bot = get_bot()

    try:
        if not bot.guilds:
            await log_error_to_discord("❌ Bot is not in any servers.")
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