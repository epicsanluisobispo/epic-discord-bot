"""
Background task that keeps a single Discord message updated with the list
of currently-active links from the media sheet (columns D, I, J, K).

This replaces the old Flask "/media-links" page: instead of a web page,
the same "is this link active right now?" logic now renders as an embed
that gets edited in place in LINK_BOARD_CHANNEL_ID, so there's only ever
one message to check instead of a growing feed.
"""

import logging
from datetime import datetime, time

import discord
import pytz
from dateutil import parser
from discord.ext import tasks

from config import (
    MEDIA_SHEET_QUARTER_TABS,
    LINK_BOARD_CHANNEL_ID,
    SHEET_POLL_INTERVAL_SECONDS,
)
from logging_utils import log_to_discord
from failure_throttle import log_failure_once, clear_failure
from media_sheet import spreadsheet
from task_health import record_task_success

TASK_NAME = "link_board"

logger = logging.getLogger(__name__)

PACIFIC_TIMEZONE = pytz.timezone("America/Los_Angeles")

# Embed descriptions are capped at 4096 characters by Discord; leave some
# headroom before that limit so a long list still fits in one edit.
EMBED_DESCRIPTION_CHARACTER_LIMIT = 3900

# Cached in memory once found/created, so we don't have to search pinned
# messages on every single poll — only on the first run after a restart.
_cached_board_message = None


def _collect_active_links():
    """Walk every quarter tab and return a list of (display_name, link)
    tuples for rows whose active window currently contains `now`."""
    now = datetime.now(PACIFIC_TIMEZONE)
    active_links = []

    for tab_name in MEDIA_SHEET_QUARTER_TABS:
        try:
            worksheet = spreadsheet.worksheet(tab_name)
            rows = worksheet.get_all_values()
        except Exception as error:
            logger.error(f"❌ Failed to load tab '{tab_name}' for link board: {error}")
            continue

        for row_index, row in enumerate(rows):
            if row_index < 2:
                continue  # Skip header rows

            row += [""] * 11
            event_name = row[3].strip()       # Column D
            event_link = row[8].strip()       # Column I
            start_date_str = row[9].strip()   # Column J
            end_date_str = row[10].strip()    # Column K

            if not event_link or not start_date_str or not end_date_str:
                continue

            try:
                start_date = parser.parse(start_date_str).date()
                end_date = parser.parse(end_date_str).date()
                window_start = PACIFIC_TIMEZONE.localize(datetime.combine(start_date, time.min))
                window_end = PACIFIC_TIMEZONE.localize(datetime.combine(end_date, time.max))
            except Exception as error:
                logger.error(f"❌ Date parse error on link board (row {row_index + 1}): {error}")
                continue

            if window_start <= now <= window_end:
                display_name = event_name if event_name else event_link
                active_links.append((display_name, event_link))

    return active_links


def _build_link_board_embed():
    active_links = _collect_active_links()

    embed = discord.Embed(
        title="📎 Active Epic SLO Links",
        color=discord.Color.blue(),
    )

    if not active_links:
        embed.description = "*No active links at the moment. Check back soon!*"
    else:
        description_lines = [f"• [{display_name}]({event_link})" for display_name, event_link in active_links]
        description = "\n".join(description_lines)

        if len(description) > EMBED_DESCRIPTION_CHARACTER_LIMIT:
            description = description[:EMBED_DESCRIPTION_CHARACTER_LIMIT] + "\n*(list truncated)*"

        embed.description = description

    embed.set_footer(text=f"Last updated {datetime.now(PACIFIC_TIMEZONE).strftime('%b %d, %I:%M %p %Z')}")
    return embed


async def _get_or_create_board_message(bot):
    """Return the message to keep editing, reusing an existing one from a
    previous bot run if it exists, otherwise creating a new one. Since this
    channel is dedicated to the link board, any prior message from the bot
    is assumed to be it."""
    global _cached_board_message

    if _cached_board_message is not None:
        return _cached_board_message

    channel = bot.get_channel(LINK_BOARD_CHANNEL_ID)
    if channel is None:
        await log_failure_once(
            "link_board:channel_missing", f"❌ Link board channel {LINK_BOARD_CHANNEL_ID} not found."
        )
        return None

    try:
        async for message in channel.history(limit=50):
            if message.author == bot.user and message.embeds:
                _cached_board_message = message
                clear_failure("link_board:history_read")
                return _cached_board_message
        clear_failure("link_board:history_read")
    except Exception as error:
        await log_failure_once(
            "link_board:history_read", f"❌ Failed to read message history in link board channel: {error}"
        )

    # No existing board message found — create a new one.
    try:
        placeholder_embed = discord.Embed(title="📎 Active Epic SLO Links", description="Loading...")
        new_message = await channel.send(embed=placeholder_embed)
        _cached_board_message = new_message
        clear_failure("link_board:create_message")
    except Exception as error:
        await log_failure_once(
            "link_board:create_message", f"❌ Failed to create link board message: {error}"
        )
        return None

    return _cached_board_message


def setup_link_board_task(bot):
    @tasks.loop(seconds=SHEET_POLL_INTERVAL_SECONDS)
    async def check_link_board_for_updates():
        # Top-level safety net: an unhandled exception here would otherwise
        # silently kill this loop forever. Catching it keeps the task alive
        # to try again next cycle, and surfaces the failure instead of
        # letting it disappear.
        try:
            board_message = await _get_or_create_board_message(bot)
            if board_message is None:
                return

            embed = _build_link_board_embed()
            await board_message.edit(embed=embed)
            record_task_success(TASK_NAME)
            clear_failure("link_board:edit")
        except Exception as error:
            print(f"🛑 Unexpected error updating link board: {error}")
            await log_failure_once("link_board:edit", f"❌ Failed to update link board message: {error}")

    check_link_board_for_updates.start()