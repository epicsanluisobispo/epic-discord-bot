"""
Background task that polls the event-request Google Sheet and:
 - notifies ETLs of new event requests
 - once all three ETLs approve, notifies the relevant team channel,
   creates a Google Calendar event, and creates/updates/deletes a matching
   Discord scheduled event.
"""

import asyncio
from datetime import datetime

import pytz
from discord.enums import ScheduledEventEntityType, ScheduledEventPrivacyLevel
from discord.ext import tasks

from config import (
    EVENT_REQUEST_SHEET_URL,
    EVENT_REQUEST_SHEET_TABS,
    EVENT_ETL_NOTIFIED_STATUS_COLUMN,
    EVENT_APPROVAL_NOTIFIED_STATUS_COLUMN,
    EVENT_DISCORD_EVENT_ID_COLUMN,
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
        return scheduled_event.id
    except Exception as error:
        print(f"❌ Failed to create Discord event '{name}': {error}")
        return None


async def update_discord_scheduled_event(guild, discord_event_id, name, start_datetime, end_datetime, description=""):
    try:
        scheduled_event = await guild.fetch_scheduled_event(discord_event_id)
        await scheduled_event.edit(
            name=name,
            start_time=start_datetime,
            end_time=end_datetime,
            description=description,
        )
        print(f"🔄 Discord event updated: {name}")
    except Exception as error:
        print(f"❌ Failed to update Discord event '{name}': {error}")


async def delete_discord_scheduled_event(guild, discord_event_id):
    try:
        scheduled_event = await guild.fetch_scheduled_event(discord_event_id)
        await scheduled_event.delete()
        print(f"🗑 Discord event deleted: {scheduled_event.name}")
    except Exception as error:
        print(f"❌ Failed to delete Discord event ID {discord_event_id}: {error}")


def setup_event_sheet_task(bot):
    @tasks.loop(seconds=SHEET_POLL_INTERVAL_SECONDS)
    async def check_event_request_sheet_for_updates():
        now = datetime.now(PACIFIC_TIMEZONE)

        for tab_name in EVENT_REQUEST_SHEET_TABS:
            try:
                worksheet = await asyncio.to_thread(spreadsheet.worksheet, tab_name)
                all_rows = await asyncio.to_thread(worksheet.get_all_values)
            except Exception as error:
                print(f"[Error loading tab '{tab_name}']: {error}")
                continue

            for row_index, row in enumerate(all_rows):
                if row_index < 1:
                    continue  # Skip header row

                row += [""] * max(0, EVENT_DISCORD_EVENT_ID_COLUMN - len(row))

                requester_name = row[1].strip()                  # Column B
                team_name = row[2].strip().lower()                # Column C
                recurring_event_name = row[6].strip()              # Column G
                one_time_event_name = row[11].strip()              # Column L
                event_date_str = row[12].strip()                   # Column M
                event_start_time_str = row[13].strip()             # Column N
                event_end_time_str = row[14].strip()               # Column O
                josh_approval_status = row[23].strip().lower()     # Column X
                nikki_approval_status = row[24].strip().lower()    # Column Y
                ellie_approval_status = row[25].strip().lower()    # Column Z
                etl_notified_status = row[EVENT_ETL_NOTIFIED_STATUS_COLUMN - 1].strip().lower()
                approval_notified_status = row[EVENT_APPROVAL_NOTIFIED_STATUS_COLUMN - 1].strip().lower()
                discord_scheduled_event_id = row[EVENT_DISCORD_EVENT_ID_COLUMN - 1].strip()

                # New request submitted -> notify ETLs once.
                if requester_name and etl_notified_status != "sent":
                    etl_channel = bot.get_channel(ETL_NOTIFICATIONS_CHANNEL_ID)
                    if etl_channel:
                        await etl_channel.send(
                            f"📌 **{requester_name}** submitted an **event request** for **{team_name}** team. "
                            f"Please review!"
                        )
                        await asyncio.to_thread(
                            worksheet.update_cell, row_index + 1, EVENT_ETL_NOTIFIED_STATUS_COLUMN, "SENT"
                        )

                # All three ETLs approved -> notify team + create calendar/Discord events.
                all_etls_approved = (
                    josh_approval_status == nikki_approval_status == ellie_approval_status == "approved"
                )
                if all_etls_approved and approval_notified_status != "sent":
                    event_description = recurring_event_name or one_time_event_name or "a request"

                    if team_name in EVENT_TEAM_CHANNEL_MAP:
                        team_channel = bot.get_channel(EVENT_TEAM_CHANNEL_MAP[team_name])
                        if team_channel:
                            await team_channel.send(
                                f"✅ Your event request for **{event_description}** has been approved by the ETLs!"
                            )
                            await asyncio.to_thread(
                                worksheet.update_cell, row_index + 1, EVENT_APPROVAL_NOTIFIED_STATUS_COLUMN, "SENT"
                            )

                        if event_date_str and event_start_time_str and event_end_time_str:
                            event_start_datetime = parse_event_datetime(event_date_str, event_start_time_str)
                            event_end_datetime = parse_event_datetime(event_date_str, event_end_time_str)

                            if event_start_datetime and event_end_datetime:
                                try:
                                    await asyncio.to_thread(
                                        create_google_calendar_event,
                                        event_description,
                                        event_start_datetime,
                                        event_end_datetime,
                                    )
                                except Exception as calendar_error:
                                    print(f"🛑 Calendar event failed: {calendar_error}")

                                guild = bot.guilds[0]
                                days_until_event = (event_start_datetime - now).days
                                event_is_within_creation_window = (
                                    0 <= days_until_event <= DISCORD_EVENT_CREATION_WINDOW_DAYS
                                )

                                if discord_scheduled_event_id:
                                    if event_end_datetime < now:
                                        await delete_discord_scheduled_event(guild, discord_scheduled_event_id)
                                        await asyncio.to_thread(
                                            worksheet.update_cell, row_index + 1, EVENT_DISCORD_EVENT_ID_COLUMN, ""
                                        )
                                    elif event_is_within_creation_window:
                                        await update_discord_scheduled_event(
                                            guild,
                                            discord_scheduled_event_id,
                                            event_description,
                                            event_start_datetime,
                                            event_end_datetime,
                                            event_description,
                                        )
                                else:
                                    if event_is_within_creation_window:
                                        new_discord_event_id = await create_discord_scheduled_event(
                                            guild,
                                            event_description,
                                            event_start_datetime,
                                            event_end_datetime,
                                            description=event_description,
                                        )
                                        if new_discord_event_id:
                                            await asyncio.to_thread(
                                                worksheet.update_cell,
                                                row_index + 1,
                                                EVENT_DISCORD_EVENT_ID_COLUMN,
                                                new_discord_event_id,
                                            )
                                    else:
                                        print(
                                            f"ℹ️ Event '{event_description}' is more than "
                                            f"{DISCORD_EVENT_CREATION_WINDOW_DAYS} days away; skipping Discord creation."
                                        )

    check_event_request_sheet_for_updates.start()