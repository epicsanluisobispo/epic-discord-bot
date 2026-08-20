"""
Report-building logic for the !status and !pending admin commands. Kept
separate from bot_commands.py so that file stays focused on just wiring up
commands, not gathering/formatting data.
"""

import asyncio
import time

from config import (
    MEDIA_SHEET_QUARTER_TABS,
    EVENT_REQUEST_SHEET_TABS,
    DISCIPLESHIP_SHEET_TAB,
    TASK_DISPLAY_NAMES,
)
from task_health import get_last_successful_run_timestamp

import media_sheet
import event_sheet
import discipleship_form

# Discord messages are capped at 2000 characters; leave headroom so a long
# report still fits in one message.
MESSAGE_CHARACTER_LIMIT = 1900


def _format_seconds_ago(seconds_ago):
    if seconds_ago < 60:
        return f"{int(seconds_ago)}s ago"
    if seconds_ago < 3600:
        return f"{int(seconds_ago // 60)}m ago"
    return f"{seconds_ago / 3600:.1f}h ago"


def _truncate_for_discord(text):
    if len(text) <= MESSAGE_CHARACTER_LIMIT:
        return text
    return text[:MESSAGE_CHARACTER_LIMIT] + "\n*(truncated)*"


async def _check_sheet_tab_reachable(spreadsheet, tab_name):
    """Returns (is_reachable, row_count_or_error_message)."""
    try:
        worksheet = await asyncio.to_thread(spreadsheet.worksheet, tab_name)
        rows = await asyncio.to_thread(worksheet.get_all_values)
        return True, len(rows)
    except Exception as error:
        return False, str(error)


async def build_status_report():
    lines = ["**🩺 Bot Status**", "", "**Background tasks:**"]

    now = time.time()
    for task_name, display_name in TASK_DISPLAY_NAMES.items():
        last_run_timestamp = get_last_successful_run_timestamp(task_name)
        if last_run_timestamp is None:
            lines.append(f"• {display_name}: ⚠️ hasn't completed a run yet this session")
        else:
            lines.append(f"• {display_name}: ✅ last ran {_format_seconds_ago(now - last_run_timestamp)}")

    lines.append("")
    lines.append("**Sheet reachability (live check):**")

    sheet_checks = [
        ("Media sheet", media_sheet.spreadsheet, MEDIA_SHEET_QUARTER_TABS),
        ("Event request sheet", event_sheet.spreadsheet, EVENT_REQUEST_SHEET_TABS),
        ("Discipleship form sheet", discipleship_form.spreadsheet, [DISCIPLESHIP_SHEET_TAB]),
    ]

    for label, spreadsheet_obj, tab_names in sheet_checks:
        total_row_count = 0
        all_tabs_reachable = True
        first_error_message = None

        for tab_name in tab_names:
            is_reachable, result = await _check_sheet_tab_reachable(spreadsheet_obj, tab_name)
            if is_reachable:
                total_row_count += result
            else:
                all_tabs_reachable = False
                first_error_message = result

        if all_tabs_reachable:
            lines.append(f"• {label}: ✅ reachable ({total_row_count} rows across {len(tab_names)} tab(s))")
        else:
            lines.append(f"• {label}: ❌ error — {first_error_message}")

    return _truncate_for_discord("\n".join(lines))


async def build_pending_report():
    lines = ["**📋 Pending Requests**", "", "**Media requests awaiting ETL approval:**"]

    pending_media_lines = []
    for tab_name in MEDIA_SHEET_QUARTER_TABS:
        try:
            worksheet = await asyncio.to_thread(media_sheet.spreadsheet.worksheet, tab_name)
            rows = await asyncio.to_thread(worksheet.get_all_values)
        except Exception:
            continue

        for row_index, row in enumerate(rows):
            if row_index < 2:
                continue  # Skip header rows

            row += [""] * 4
            etl_approved = row[0].strip().lower()   # Column A
            requester_name = row[1].strip()          # Column B
            event_name = row[3].strip()              # Column D

            if requester_name and event_name and etl_approved != "yes":
                pending_media_lines.append(f"• **{requester_name}** — {event_name} ({tab_name})")

    lines.extend(pending_media_lines if pending_media_lines else ["• None 🎉"])

    lines.append("")
    lines.append("**Event requests awaiting ETL approval:**")

    pending_event_lines = []
    for tab_name in EVENT_REQUEST_SHEET_TABS:
        try:
            worksheet = await asyncio.to_thread(event_sheet.spreadsheet.worksheet, tab_name)
            rows = await asyncio.to_thread(worksheet.get_all_values)
        except Exception:
            continue

        for row_index, row in enumerate(rows):
            if row_index < 1:
                continue  # Skip header row

            row += [""] * 24
            requester_name = row[1].strip()               # Column B
            team_name = row[2].strip()                     # Column C
            recurring_event_name = row[6].strip()           # Column G
            one_time_event_name = row[11].strip()           # Column L
            event_approved_status = row[23].strip().lower() # Column X

            is_approved = event_approved_status == "approved"

            if requester_name and not is_approved:
                description = recurring_event_name or one_time_event_name or "(unnamed)"
                pending_event_lines.append(f"• **{requester_name}** — {description} ({team_name})")

    lines.extend(pending_event_lines if pending_event_lines else ["• None 🎉"])

    return _truncate_for_discord("\n".join(lines))