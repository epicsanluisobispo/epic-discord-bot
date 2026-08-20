"""
Background task that polls the event-request Google Sheet and:
 - notifies ETLs of new event requests
 - once the ETLs approve, notifies the relevant team channel and
   creates a Google Calendar event
 - for one-time events (not recurring), also creates/updates/deletes a
   matching Discord scheduled event
 - reminds the ETL channel if a request has sat unapproved too long
"""

import asyncio
from datetime import datetime

import pytz
from dateutil import parser
from discord.enums import ScheduledEventEntityType, ScheduledEventPrivacyLevel
from discord.ext import tasks

from config import (
    EVENT_REQUEST_SHEET_URL,
    EVENT_REQUEST_SHEET_TABS,
    EVENT_APPROVED_STATUS_COLUMN,
    EVENT_ETL_NOTIFIED_STATUS_COLUMN,
    EVENT_APPROVAL_NOTIFIED_STATUS_COLUMN,
    EVENT_DISCORD_EVENT_ID_COLUMN,
    EVENT_SUBMITTED_TIMESTAMP_COLUMN,
    EVENT_REMINDER_SENT_STATUS_COLUMN,
    REQUEST_REMINDER_THRESHOLD_DAYS,
    EVENT_TEAM_CHANNEL_MAP,
    EVENT_CALENDAR_ID,
    ETL_NOTIFICATIONS_CHANNEL_ID,
    SHEET_POLL_INTERVAL_SECONDS,
)
from google_auth import (
    get_sheets_client_and_credentials,
    get_calendar_service,
    SPREADSHEET_AND_CALENDAR_SCOPES,
)
from logging_utils import log_to_discord
from failure_throttle import log_failure_once, clear_failure
from sheet_utils import update_cell_with_retry
from task_health import record_task_success

TASK_NAME = "event_sheet"

gspread_client, google_credentials = get_sheets_client_and_credentials(SPREADSHEET_AND_CALENDAR_SCOPES)
calendar_service = get_calendar_service(google_credentials)
spreadsheet = gspread_client.open_by_url(EVENT_REQUEST_SHEET_URL)

PACIFIC_TIMEZONE = pytz.timezone("America/Los_Angeles")

# Only create/keep a Discord scheduled event if it starts within this many
# days from now (events too far out tend to get forgotten/unmaintained).
DISCORD_EVENT_CREATION_WINDOW_DAYS = 14


def parse_event_datetime(date_str, time_str):
    """Parse a sheet date + time pair into a Pacific-timezone-aware
    datetime, trying the couple of formats the sheet has historically used.

    Returning a timezone-aware value here (rather than a naive one) is
    required: this result gets compared against and subtracted from `now`,
    which is timezone-aware, and Python raises a TypeError if you mix
    naive and aware datetimes in that kind of arithmetic.
    """
    candidate_formats = ("%m/%d/%Y %I:%M:%S %p", "%Y-%m-%d %I:%M:%S %p")
    for date_format in candidate_formats:
        try:
            naive_datetime = datetime.strptime(f"{date_str} {time_str}", date_format)
            return PACIFIC_TIMEZONE.localize(naive_datetime)
        except ValueError:
            continue
    return None


def create_google_calendar_event(summary, start_datetime, end_datetime):
    event_body = {
        "summary": summary,
        "start": {"dateTime": start_datetime.isoformat(), "timeZone": "America/Los_Angeles"},
        "end": {"dateTime": end_datetime.isoformat(), "timeZone": "America/Los_Angeles"},
    }
    result = calendar_service.events().insert(calendarId=EVENT_CALENDAR_ID, body=event_body).execute()
    return result.get("htmlLink")


async def create_discord_scheduled_event(guild, name, start_datetime, end_datetime, location="TBA", description=""):
    failure_key = f"event_sheet:create:{name}"
    try:
        scheduled_event = await guild.create_scheduled_event(
            name=name,
            description=description,
            start_time=start_datetime,
            end_time=end_datetime,
            entity_type=ScheduledEventEntityType.external,
            location=location,
            privacy_level=ScheduledEventPrivacyLevel.guild_only,
        )
        print(f"✅ Discord event created: {name}")
        clear_failure(failure_key)
        return scheduled_event.id
    except Exception as error:
        print(f"❌ Failed to create Discord event '{name}': {error}")
        await log_failure_once(failure_key, f"❌ Failed to create Discord event **{name}**: {error}")
        return None


async def update_discord_scheduled_event(
    guild, discord_event_id, name, start_datetime, end_datetime, location="TBA", description=""
):
    failure_key = f"event_sheet:update:{discord_event_id}"
    try:
        scheduled_event = await guild.fetch_scheduled_event(discord_event_id)
        await scheduled_event.edit(
            name=name,
            start_time=start_datetime,
            end_time=end_datetime,
            location=location,
            description=description,
        )
        print(f"🔄 Discord event updated: {name}")
        clear_failure(failure_key)
    except Exception as error:
        print(f"❌ Failed to update Discord event '{name}': {error}")
        await log_failure_once(failure_key, f"❌ Failed to update Discord event **{name}**: {error}")


async def delete_discord_scheduled_event(guild, discord_event_id):
    failure_key = f"event_sheet:delete:{discord_event_id}"
    try:
        scheduled_event = await guild.fetch_scheduled_event(discord_event_id)
        await scheduled_event.delete()
        print(f"🗑 Discord event deleted: {scheduled_event.name}")
        clear_failure(failure_key)
    except Exception as error:
        print(f"❌ Failed to delete Discord event ID {discord_event_id}: {error}")
        await log_failure_once(
            failure_key, f"❌ Failed to delete Discord event ID {discord_event_id}: {error}"
        )


def setup_event_sheet_task(bot):
    @tasks.loop(seconds=SHEET_POLL_INTERVAL_SECONDS)
    async def check_event_request_sheet_for_updates():
        # Top-level safety net: an unhandled exception anywhere below would
        # otherwise silently kill this entire polling loop forever. Catching
        # here means the loop always survives to try again next cycle.
        try:
            await _run_one_polling_pass(bot)
            record_task_success(TASK_NAME)
            clear_failure("event_sheet:unexpected")
        except Exception as error:
            print(f"🛑 Unexpected error in event sheet poll: {error}")
            await log_failure_once(
                "event_sheet:unexpected", f"❌ Event sheet poll failed unexpectedly: {error}"
            )

    check_event_request_sheet_for_updates.start()


async def _run_one_polling_pass(bot):
    now = datetime.now(PACIFIC_TIMEZONE)

    for tab_name in EVENT_REQUEST_SHEET_TABS:
        tab_load_failure_key = f"event_sheet:tab_load:{tab_name}"
        try:
            worksheet = await asyncio.to_thread(spreadsheet.worksheet, tab_name)
            all_rows = await asyncio.to_thread(worksheet.get_all_values)
            clear_failure(tab_load_failure_key)
        except Exception as error:
            print(f"[Error loading tab '{tab_name}']: {error}")
            await log_failure_once(
                tab_load_failure_key, f"❌ Failed to load event sheet tab '{tab_name}': {error}"
            )
            continue

        for row_index, row in enumerate(all_rows):
            if row_index < 1:
                continue  # Skip header row

            row += [""] * max(0, EVENT_REMINDER_SENT_STATUS_COLUMN - len(row))

            submitted_timestamp_str = row[EVENT_SUBMITTED_TIMESTAMP_COLUMN - 1].strip()  # Column A
            requester_name = row[1].strip()                  # Column B
            team_name = row[2].strip().lower()                # Column C
            recurring_event_name = row[6].strip()              # Column G
            one_time_event_name = row[11].strip()              # Column L
            event_date_str = row[12].strip()                   # Column M
            event_start_time_str = row[13].strip()             # Column N
            event_end_time_str = row[14].strip()               # Column O
            event_location = row[15].strip()                   # Column P
            event_approved_status = row[EVENT_APPROVED_STATUS_COLUMN - 1].strip().lower()  # Column X
            etl_notified_status = row[EVENT_ETL_NOTIFIED_STATUS_COLUMN - 1].strip().lower()
            approval_notified_status = row[EVENT_APPROVAL_NOTIFIED_STATUS_COLUMN - 1].strip().lower()
            discord_scheduled_event_id = row[EVENT_DISCORD_EVENT_ID_COLUMN - 1].strip()
            reminder_sent_status = row[EVENT_REMINDER_SENT_STATUS_COLUMN - 1].strip().lower()

            # Requests marked recurring don't get a Discord scheduled event —
            # a single Discord event can't represent an ongoing weekly/
            # monthly series, so we only manage Calendar + team notification
            # for these, and never touch column AC (Discord event ID) at all.
            is_recurring_event = bool(recurring_event_name)

            # New request submitted -> notify ETLs once.
            if requester_name and etl_notified_status != "sent":
                etl_channel = bot.get_channel(ETL_NOTIFICATIONS_CHANNEL_ID)
                if etl_channel:
                    await etl_channel.send(
                        f"📌 **{requester_name}** submitted an **event request** for **{team_name}** team. "
                        f"Please review!"
                    )
                    await update_cell_with_retry(
                        worksheet,
                        row_index + 1,
                        EVENT_ETL_NOTIFIED_STATUS_COLUMN,
                        "SENT",
                        context_label=f"event etl-notified, row {row_index + 1}",
                    )

            is_event_approved = event_approved_status == "approved"

            # Still awaiting ETL approval after too long -> remind once.
            if (
                requester_name
                and not is_event_approved
                and reminder_sent_status != "sent"
                and submitted_timestamp_str
            ):
                try:
                    days_pending = (now.date() - parser.parse(submitted_timestamp_str).date()).days
                except Exception:
                    days_pending = None

                if days_pending is not None and days_pending >= REQUEST_REMINDER_THRESHOLD_DAYS:
                    etl_channel = bot.get_channel(ETL_NOTIFICATIONS_CHANNEL_ID)
                    if etl_channel:
                        await etl_channel.send(
                            f"⏰ Reminder: **{requester_name}**'s event request for **{team_name}** team has been "
                            f"waiting for ETL approval for {days_pending} days. Please review!"
                        )
                        await update_cell_with_retry(
                            worksheet,
                            row_index + 1,
                            EVENT_REMINDER_SENT_STATUS_COLUMN,
                            "SENT",
                            context_label=f"event reminder-sent, row {row_index + 1}",
                        )

            # ETL approved -> notify team + create calendar/Discord events.
            if is_event_approved and approval_notified_status != "sent":
                event_description = recurring_event_name or one_time_event_name or "a request"

                if team_name in EVENT_TEAM_CHANNEL_MAP:
                    team_channel = bot.get_channel(EVENT_TEAM_CHANNEL_MAP[team_name])
                    if team_channel:
                        await team_channel.send(
                            f"✅ Your event request for **{event_description}** has been approved by the ETLs!"
                        )
                        await update_cell_with_retry(
                            worksheet,
                            row_index + 1,
                            EVENT_APPROVAL_NOTIFIED_STATUS_COLUMN,
                            "SENT",
                            context_label=f"event approval-notified, row {row_index + 1}",
                        )

                    if event_date_str and event_start_time_str and event_end_time_str:
                        event_start_datetime = parse_event_datetime(event_date_str, event_start_time_str)
                        event_end_datetime = parse_event_datetime(event_date_str, event_end_time_str)

                        if event_start_datetime and event_end_datetime:
                            calendar_failure_key = f"event_sheet:calendar:{event_description}"
                            try:
                                await asyncio.to_thread(
                                    create_google_calendar_event,
                                    event_description,
                                    event_start_datetime,
                                    event_end_datetime,
                                )
                                clear_failure(calendar_failure_key)
                            except Exception as calendar_error:
                                print(f"🛑 Calendar event failed: {calendar_error}")
                                await log_failure_once(
                                    calendar_failure_key,
                                    f"❌ Failed to create calendar event **{event_description}**: {calendar_error}",
                                )

                            if is_recurring_event:
                                print(
                                    f"ℹ️ Event '{event_description}' is recurring; skipping Discord event creation."
                                )
                            else:
                                guild = bot.guilds[0]
                                days_until_event = (event_start_datetime - now).days
                                event_is_within_creation_window = (
                                    0 <= days_until_event <= DISCORD_EVENT_CREATION_WINDOW_DAYS
                                )

                                if discord_scheduled_event_id:
                                    if event_end_datetime < now:
                                        await delete_discord_scheduled_event(guild, discord_scheduled_event_id)
                                        await update_cell_with_retry(
                                            worksheet,
                                            row_index + 1,
                                            EVENT_DISCORD_EVENT_ID_COLUMN,
                                            "",
                                            context_label=f"event discord-id clear, row {row_index + 1}",
                                        )
                                    elif event_is_within_creation_window:
                                        await update_discord_scheduled_event(
                                            guild,
                                            discord_scheduled_event_id,
                                            event_description,
                                            event_start_datetime,
                                            event_end_datetime,
                                            location=event_location or "TBA",
                                            description=event_description,
                                        )
                                else:
                                    if event_is_within_creation_window:
                                        new_discord_event_id = await create_discord_scheduled_event(
                                            guild,
                                            event_description,
                                            event_start_datetime,
                                            event_end_datetime,
                                            location=event_location or "TBA",
                                            description=event_description,
                                        )
                                        if new_discord_event_id:
                                            await update_cell_with_retry(
                                                worksheet,
                                                row_index + 1,
                                                EVENT_DISCORD_EVENT_ID_COLUMN,
                                                new_discord_event_id,
                                                context_label=f"event discord-id save, row {row_index + 1}",
                                            )
                                    else:
                                        print(
                                            f"ℹ️ Event '{event_description}' is more than "
                                            f"{DISCORD_EVENT_CREATION_WINDOW_DAYS} days away; skipping Discord creation."
                                        )