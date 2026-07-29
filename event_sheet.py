import os
import json
import asyncio
from datetime import datetime, timedelta
import pytz

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from discord.ext import tasks
from discord.enums import ScheduledEventEntityType, ScheduledEventPrivacyLevel

# ----------------------------
# Google Sheets + Calendar Setup
# ----------------------------
SERVICE_ACCOUNT_INFO = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar"
]
creds = Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
gc = gspread.authorize(creds)
calendar_service = build("calendar", "v3", credentials=creds)

SECOND_SHEET_URL = "https://docs.google.com/spreadsheets/d/1ynvQRNEG26NKE8zYZFhjaLL0RiBmA7hWD-np3EwqbeQ/edit?usp=sharing"
SECOND_SHEET_TABS = ["Use this one"]

CHANNEL_Z_ID = 1395968665287135262  # ETL notifications
STATUS_COL_AA = 27  # ETL notification status
STATUS_COL_AB = 28  # Approval notification status
DISCORD_ID_COL = 29  # New: Discord Event ID column

CHANNEL_MAP = {
    "large group": 1388258914629451917,
    "outreach": 1388259127528259645,
    "inreach": 1388259483335135232,
    "media": 1388259539714969830,
    "mens isi": 1388259626906030252,
    "womens isi": 1388259678391242864,
    "4th year cg": 1388259730958450889,
    "worship": 1388259786990030928,
    "boys t1": 1388259868959441047,
    "girls t1": 1388259923078549504, 
    "retreats": 1388259981001887744,
}

spreadsheet = gc.open_by_url(SECOND_SHEET_URL)

# ----------------------------
# Helper functions
# ----------------------------

def parse_datetime(date_str, time_str):
    formats = ("%m/%d/%Y %I:%M:%S %p", "%Y-%m-%d %I:%M:%S %p")
    for fmt in formats:
        try:
            return datetime.strptime(f"{date_str} {time_str}", fmt)
        except ValueError:
            continue
    return None

def create_calendar_event(summary, start_dt, end_dt, calendar_id="epicsanluisobispo@gmail.com"):
    event = {
        "summary": summary,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Los_Angeles"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Los_Angeles"},
    }
    result = calendar_service.events().insert(calendarId=calendar_id, body=event).execute()
    return result.get("htmlLink")

async def create_discord_event(bot, guild, name, start_dt, end_dt, location="TBA", description=""):
    try:
        event = await guild.create_scheduled_event(
            name=name,
            description=description,
            start_time=start_dt,
            end_time=end_dt,
            entity_type=ScheduledEventEntityType.external,
            location=location,
            privacy_level=ScheduledEventPrivacyLevel.guild_only
        )
        print(f"✅ Discord event created: {name}")
        return event.id
    except Exception as e:
        print(f"❌ Failed to create Discord event '{name}': {e}")
        return None

async def update_discord_event(bot, guild, event_id, name, start_dt, end_dt, description=""):
    try:
        event = await guild.fetch_scheduled_event(event_id)
        await event.edit(
            name=name,
            start_time=start_dt,
            end_time=end_dt,
            description=description
        )
        print(f"🔄 Discord event updated: {name}")
    except Exception as e:
        print(f"❌ Failed to update Discord event '{name}': {e}")

async def delete_discord_event(bot, guild, event_id):
    try:
        event = await guild.fetch_scheduled_event(event_id)
        await event.delete()
        print(f"🗑 Discord event deleted: {event.name}")
    except Exception as e:
        print(f"❌ Failed to delete Discord event ID {event_id}: {e}")

# ----------------------------
# Main task
# ----------------------------

def setup_event_sheet_task(bot):
    @tasks.loop(seconds=60)
    async def check_second_sheet():
        tz = pytz.timezone("America/Los_Angeles")
        now = datetime.now(tz)

        for tab_name in SECOND_SHEET_TABS:
            try:
                sheet = await asyncio.to_thread(spreadsheet.worksheet, tab_name)
                all_rows = await asyncio.to_thread(sheet.get_all_values)
            except Exception as e:
                print(f"[Error loading tab '{tab_name}']: {e}")
                continue

            for i, row in enumerate(all_rows):
                if i < 1:
                    continue  # skip header

                row += [""] * max(0, DISCORD_ID_COL - len(row))
                requester = row[1].strip()             # Column B
                team = row[2].strip().lower()          # Column C
                recurring_name = row[6].strip()        # Column G
                one_time_name = row[11].strip()        # Column L
                date_str = row[12].strip()             # Column M
                start_str = row[13].strip()            # Column N
                end_str = row[14].strip()              # Column O
                josh = row[23].strip().lower()         # Column X
                nikki = row[24].strip().lower()        # Column Y
                ellie = row[25].strip().lower()        # Column Z
                status_aa = row[STATUS_COL_AA - 1].strip().lower()
                status_ab = row[STATUS_COL_AB - 1].strip().lower()
                discord_event_id = row[DISCORD_ID_COL - 1].strip()

                # Notify ETLs of new requests
                if requester and status_aa != "sent":
                    chan = bot.get_channel(CHANNEL_Z_ID)
                    if chan:
                        await chan.send(f"📌 **{requester}** submitted an **event request** for **{team}** team. Please review!")
                        await asyncio.to_thread(sheet.update_cell, i+1, STATUS_COL_AA, "SENT")

                # Notify team if approved by all ETLs
                if josh == nikki == ellie == "approved" and status_ab != "sent":
                    description = recurring_name or one_time_name or "a request"
                    if team in CHANNEL_MAP:
                        chan = bot.get_channel(CHANNEL_MAP[team])
                        if chan:
                            await chan.send(f"✅ Your event request for **{description}** has been approved by the ETLs!")
                            await asyncio.to_thread(sheet.update_cell, i+1, STATUS_COL_AB, "SENT")

                        # Parse dates for one-time events
                        if date_str and start_str and end_str:
                            start_dt = parse_datetime(date_str, start_str)
                            end_dt = parse_datetime(date_str, end_str)
                            if start_dt and end_dt:
                                # Google Calendar
                                try:
                                    await asyncio.to_thread(create_calendar_event, description, start_dt, end_dt)
                                except Exception as ce:
                                    print(f"🛑 Calendar event failed: {ce}")

                                # Discord event handling
                                guild = bot.guilds[0]
                                within_2_weeks = 0 <= (start_dt - now).days <= 14

                                # If event already exists
                                if discord_event_id:
                                    # Check if event has passed
                                    if end_dt < now:
                                        await delete_discord_event(bot, guild, discord_event_id)
                                        await asyncio.to_thread(sheet.update_cell, i+1, DISCORD_ID_COL, "")
                                    elif within_2_weeks:
                                        # Update event if still upcoming
                                        await update_discord_event(bot, guild, discord_event_id, description, start_dt, end_dt, description)
                                else:
                                    # Create event only if within 2 weeks
                                    if within_2_weeks:
                                        new_event_id = await create_discord_event(bot, guild, description, start_dt, end_dt, description=description)
                                        if new_event_id:
                                            await asyncio.to_thread(sheet.update_cell, i+1, DISCORD_ID_COL, new_event_id)
                                    else:
                                        print(f"ℹ️ Event '{description}' is more than 2 weeks away; skipping Discord creation.")

    check_second_sheet.start()
