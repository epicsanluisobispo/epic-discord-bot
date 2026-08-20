"""
Shared retry helper for writing back to a sheet cell (e.g. marking a row
"SENT" after a notification goes out, or saving a new Discord event ID).

This matters because in every polling task, the Discord message/action
happens *before* the sheet gets marked. If that write then fails outright,
the row still looks "unprocessed" next poll and the action repeats (a
duplicate notification, or a duplicate Discord event). Retrying the write
a couple of times with backoff shrinks that window considerably; if all
retries still fail, the caller is told so it can log/handle it instead of
finding out via a duplicate.
"""

import asyncio

from failure_throttle import log_failure_once, clear_failure

MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1, 3, 7)


async def update_cell_with_retry(worksheet, row_number, column_number, value, context_label=""):
    """Attempts worksheet.update_cell(...), retrying on failure with
    backoff. Returns True on success, False if every attempt failed (in
    which case a warning has been logged to the log channel — but only
    once per (row, column) until it next succeeds, so a persistently
    failing cell doesn't spam the channel on every poll)."""
    failure_key = f"sheet_write:{worksheet.title}:{row_number}:{column_number}"
    last_error = None

    for attempt_number in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            await asyncio.to_thread(worksheet.update_cell, row_number, column_number, value)
            clear_failure(failure_key)
            return True
        except Exception as error:
            last_error = error
            if attempt_number < MAX_RETRY_ATTEMPTS:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS[attempt_number - 1])

    label_suffix = f" [{context_label}]" if context_label else ""
    await log_failure_once(
        failure_key,
        f"❌ Failed to update sheet cell (row {row_number}, col {column_number}){label_suffix} "
        f"after {MAX_RETRY_ATTEMPTS} attempts: {last_error}. This row may get reprocessed next poll.",
    )
    return False