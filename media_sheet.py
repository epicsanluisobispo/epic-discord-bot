"""
Background task that polls the media-request Google Sheet and posts Discord
notifications when: (1) a new media request is submitted (notify ETLs), and
(2) a request is approved by the ETLs (notify the media/large-group teams).
"""

import asyncio
from functools import partial

from discord.ext import tasks

from config import (
    MEDIA_SHEET_URL,
    MEDIA_SHEET_QUARTER_TABS,
    MEDIA_ETL_NOTIFIED_STATUS_COLUMN,
    MEDIA_TEAM_NOTIFIED_STATUS_COLUMN,
    ETL_NOTIFICATIONS_CHANNEL_ID,
    MEDIA_TEAM_CHANNEL_ID,
    LARGE_GROUP_SLIDES_CHANNEL_ID,
    SHEET_POLL_INTERVAL_SECONDS,
)
from google_auth import get_sheets_client
from failure_throttle import log_failure_once, clear_failure
from sheet_utils import update_cell_with_retry
from task_health import record_task_success

TASK_NAME = "media_sheet"

gspread_client = get_sheets_client()
spreadsheet = gspread_client.open_by_url(MEDIA_SHEET_URL)


def _blocking_fetch_worksheet_rows(sheet, tab_name):
    worksheet = sheet.worksheet(tab_name)
    return worksheet, worksheet.get_all_values()


def setup_media_sheet_task(bot):
    @tasks.loop(seconds=SHEET_POLL_INTERVAL_SECONDS)
    async def check_media_sheet_for_updates():
        # Top-level safety net: an unhandled exception anywhere below would
        # otherwise silently kill this entire polling loop forever (discord.
        # ext.tasks does not auto-restart a loop that raises). Catching here
        # means the loop always survives to try again next cycle, and the
        # failure gets surfaced instead of disappearing.
        try:
            await _run_one_polling_pass(bot)
            record_task_success(TASK_NAME)
            clear_failure("media_sheet:unexpected")
        except Exception as error:
            print(f"🛑 Unexpected error in media sheet poll: {error}")
            await log_failure_once(
                "media_sheet:unexpected", f"❌ Media sheet poll failed unexpectedly: {error}"
            )

    check_media_sheet_for_updates.start()


async def _run_one_polling_pass(bot):
    event_loop = asyncio.get_running_loop()

    for tab_name in MEDIA_SHEET_QUARTER_TABS:
        tab_load_failure_key = f"media_sheet:tab_load:{tab_name}"
        try:
            worksheet, all_rows = await asyncio.wait_for(
                event_loop.run_in_executor(
                    None, partial(_blocking_fetch_worksheet_rows, spreadsheet, tab_name)
                ),
                timeout=15,
            )
            clear_failure(tab_load_failure_key)
        except asyncio.TimeoutError:
            print(f"🛑 Timeout loading '{tab_name}' tab")
            await log_failure_once(tab_load_failure_key, f"❌ Timed out loading media sheet tab '{tab_name}'.")
            continue
        except Exception as error:
            print(f"[Error in sheet '{tab_name}']: {error}")
            await log_failure_once(
                tab_load_failure_key, f"❌ Failed to load media sheet tab '{tab_name}': {error}"
            )
            continue

        for row_index, row in enumerate(all_rows):
            if row_index < 2:
                continue  # Skip header rows

            row += [""] * max(0, MEDIA_TEAM_NOTIFIED_STATUS_COLUMN - len(row))

            etl_approved = row[0].strip().lower()               # Column A
            requester_name = row[1].strip()                     # Column B
            event_name = row[3].strip()                         # Column D
            wants_instagram_post = row[11].strip().lower()      # Column L
            wants_instagram_story = row[12].strip().lower()     # Column M
            wants_large_group_slide = row[17].strip().lower()   # Column R
            etl_notified_status = row[MEDIA_ETL_NOTIFIED_STATUS_COLUMN - 1].strip().lower()     # Column X
            team_notified_status = row[MEDIA_TEAM_NOTIFIED_STATUS_COLUMN - 1].strip().lower()   # Column Y

            # New request submitted -> notify ETLs once.
            if requester_name and event_name and etl_notified_status != "sent":
                etl_channel = bot.get_channel(ETL_NOTIFICATIONS_CHANNEL_ID)
                if etl_channel:
                    await etl_channel.send(
                        f"📢 **{requester_name}** has added {event_name} to the **media live sheet**. "
                        f"Waiting to be reviewed!"
                    )
                    await update_cell_with_retry(
                        worksheet,
                        row_index + 1,
                        MEDIA_ETL_NOTIFIED_STATUS_COLUMN,
                        "SENT",
                        context_label=f"media etl-notified, row {row_index + 1}",
                    )
                continue

            # Request approved by ETLs -> notify the relevant team(s) once.
            if etl_approved == "yes" and team_notified_status != "sent":
                notified_a_team = False

                if wants_instagram_post == "true" and wants_instagram_story == "true":
                    media_channel = bot.get_channel(MEDIA_TEAM_CHANNEL_ID)
                    if media_channel:
                        await media_channel.send(
                            f"📢 The ETLs have approved **{requester_name}**'s media request of {event_name}. "
                            f"They are requesting both an Instagram post and a story. "
                            f"Please check the media live sheet!"
                        )
                        notified_a_team = True
                elif wants_instagram_post == "true":
                    media_channel = bot.get_channel(MEDIA_TEAM_CHANNEL_ID)
                    if media_channel:
                        await media_channel.send(
                            f"📢 The ETLs have approved **{requester_name}**'s media request of {event_name}. "
                            f"They are requesting an Instagram post. Please check the media live sheet!"
                        )
                        notified_a_team = True
                elif wants_instagram_story == "true":
                    media_channel = bot.get_channel(MEDIA_TEAM_CHANNEL_ID)
                    if media_channel:
                        await media_channel.send(
                            f"📢 The ETLs have approved **{requester_name}**'s media request of {event_name}. "
                            f"They are requesting an Instagram story. Please check the media live sheet!"
                        )
                        notified_a_team = True

                if wants_large_group_slide == "true":
                    large_group_channel = bot.get_channel(LARGE_GROUP_SLIDES_CHANNEL_ID)
                    if large_group_channel:
                        await large_group_channel.send(
                            f"📢 The ETLs have approved **{requester_name}**'s media request of {event_name}. "
                            f"They are requesting a large group slide. Please check the media live sheet!"
                        )
                        notified_a_team = True

                if notified_a_team:
                    await update_cell_with_retry(
                        worksheet,
                        row_index + 1,
                        MEDIA_TEAM_NOTIFIED_STATUS_COLUMN,
                        "SENT",
                        context_label=f"media team-notified, row {row_index + 1}",
                    )