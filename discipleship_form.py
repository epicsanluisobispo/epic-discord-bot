"""
Background task that polls the Discipleship form-responses sheet and posts
a one-line notification to the ETL channel whenever a new entry appears.
This is intentionally minimal compared to media_sheet.py/event_sheet.py —
it doesn't do any approval routing, just "new row -> one message".
"""

import asyncio
from functools import partial

from discord.ext import tasks

from config import (
    DISCIPLESHIP_SHEET_URL,
    DISCIPLESHIP_SHEET_TAB,
    DISCIPLESHIP_NOTIFIED_STATUS_COLUMN,
    ETL_NOTIFICATIONS_CHANNEL_ID,
    SHEET_POLL_INTERVAL_SECONDS,
)
from google_auth import get_sheets_client
from failure_throttle import log_failure_once, clear_failure
from sheet_utils import update_cell_with_retry
from task_health import record_task_success

TASK_NAME = "discipleship_form"

gspread_client = get_sheets_client()
spreadsheet = gspread_client.open_by_url(DISCIPLESHIP_SHEET_URL)


def _blocking_fetch_worksheet_rows(sheet, tab_name):
    worksheet = sheet.worksheet(tab_name)
    return worksheet, worksheet.get_all_values()


def setup_discipleship_form_task(bot):
    @tasks.loop(seconds=SHEET_POLL_INTERVAL_SECONDS)
    async def check_discipleship_form_for_new_entries():
        # Top-level safety net: an unhandled exception here would otherwise
        # silently kill this loop forever. Catching it keeps the task alive
        # to try again next cycle, and surfaces the failure instead of
        # letting it disappear.
        try:
            await _run_one_polling_pass(bot)
            record_task_success(TASK_NAME)
            clear_failure("discipleship_form:unexpected")
        except Exception as error:
            print(f"🛑 Unexpected error in discipleship form poll: {error}")
            await log_failure_once(
                "discipleship_form:unexpected", f"❌ Discipleship form poll failed unexpectedly: {error}"
            )

    check_discipleship_form_for_new_entries.start()


async def _run_one_polling_pass(bot):
    event_loop = asyncio.get_running_loop()
    tab_load_failure_key = "discipleship_form:tab_load"

    try:
        worksheet, all_rows = await asyncio.wait_for(
            event_loop.run_in_executor(
                None, partial(_blocking_fetch_worksheet_rows, spreadsheet, DISCIPLESHIP_SHEET_TAB)
            ),
            timeout=15,
        )
        clear_failure(tab_load_failure_key)
    except asyncio.TimeoutError:
        print(f"🛑 Timeout loading '{DISCIPLESHIP_SHEET_TAB}' tab")
        await log_failure_once(tab_load_failure_key, "❌ Timed out loading discipleship form sheet.")
        return
    except Exception as error:
        print(f"[Error in sheet '{DISCIPLESHIP_SHEET_TAB}']: {error}")
        await log_failure_once(
            tab_load_failure_key, f"❌ Failed to load discipleship form sheet: {error}"
        )
        return

    for row_index, row in enumerate(all_rows):
        if row_index < 1:
            continue  # Skip header row

        row += [""] * max(0, DISCIPLESHIP_NOTIFIED_STATUS_COLUMN - len(row))

        respondent_name = row[1].strip()  # Column B
        notified_status = row[DISCIPLESHIP_NOTIFIED_STATUS_COLUMN - 1].strip().lower()  # Column AA

        if respondent_name and notified_status != "sent":
            etl_channel = bot.get_channel(ETL_NOTIFICATIONS_CHANNEL_ID)
            if etl_channel:
                await etl_channel.send(f"📖 Discipleship form has been filled out by **{respondent_name}**! ✨")
                await update_cell_with_retry(
                    worksheet,
                    row_index + 1,
                    DISCIPLESHIP_NOTIFIED_STATUS_COLUMN,
                    "SENT",
                    context_label=f"discipleship notified, row {row_index + 1}",
                )