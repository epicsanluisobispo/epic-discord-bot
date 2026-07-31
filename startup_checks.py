"""
One-time startup sanity check: validates config.py against the bot's
actual guild — do the roles referenced in ROLE_GRANT_RULES exist? are the
channel IDs in config.py valid? — and posts one consolidated warning to
the log channel if not, instead of letting misconfiguration surface later
as scattered runtime noise (e.g. a "role not found" message per member
during a sweep, or an approved request silently going nowhere because its
team's channel ID typo'd).
"""

from config import (
    ROLE_GRANT_RULES,
    LOG_CHANNEL_ID,
    ETL_NOTIFICATIONS_CHANNEL_ID,
    MEDIA_TEAM_CHANNEL_ID,
    LINK_BOARD_CHANNEL_ID,
    LARGE_GROUP_SLIDES_CHANNEL_ID,
    EVENT_TEAM_CHANNEL_MAP,
)
from logging_utils import log_to_discord


def _collect_role_names_referenced_by_rules():
    role_names = set()
    for rule in ROLE_GRANT_RULES:
        role_names.add(rule["grants_role_named"])
        for role_group in rule["granted_if_member_has_any_of_these_role_groups"]:
            role_names.update(role_group)
    return sorted(role_names)


def _collect_channel_ids_referenced_by_config():
    """Returns a dict of {human-readable config location: channel ID}."""
    channel_ids_by_config_location = {
        "LOG_CHANNEL_ID": LOG_CHANNEL_ID,
        "ETL_NOTIFICATIONS_CHANNEL_ID": ETL_NOTIFICATIONS_CHANNEL_ID,
        "MEDIA_TEAM_CHANNEL_ID": MEDIA_TEAM_CHANNEL_ID,
        "LINK_BOARD_CHANNEL_ID": LINK_BOARD_CHANNEL_ID,
        "LARGE_GROUP_SLIDES_CHANNEL_ID": LARGE_GROUP_SLIDES_CHANNEL_ID,
    }
    for team_name, channel_id in EVENT_TEAM_CHANNEL_MAP.items():
        channel_ids_by_config_location[f"EVENT_TEAM_CHANNEL_MAP['{team_name}']"] = channel_id
    return channel_ids_by_config_location


async def run_startup_config_checks(bot):
    """Checks config.py against the bot's first guild and posts one
    consolidated warning (or an all-clear) to the log channel."""
    if not bot.guilds:
        await log_to_discord("⚠️ Startup config check skipped: bot is not in any servers.")
        return

    guild = bot.guilds[0]
    problems = []

    existing_role_names = {role.name for role in guild.roles}
    for role_name in _collect_role_names_referenced_by_rules():
        if role_name not in existing_role_names:
            problems.append(f"• Role **{role_name}** (used in ROLE_GRANT_RULES) does not exist on this server.")

    for config_location, channel_id in _collect_channel_ids_referenced_by_config().items():
        if bot.get_channel(channel_id) is None:
            problems.append(f"• Channel ID `{channel_id}` (**{config_location}**) could not be found.")

    if problems:
        problems_text = "\n".join(problems)
        await log_to_discord(f"⚠️ **Startup config check found {len(problems)} issue(s):**\n{problems_text}")
    else:
        await log_to_discord("✅ Startup config check passed: all configured roles and channels found.")