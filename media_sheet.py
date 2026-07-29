import os, json, asyncio
import gspread
from google.oauth2.service_account import Credentials
from discord.ext import tasks
from functools import partial

SERVICE_ACCOUNT_INFO = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
gc = gspread.authorize(creds)

#SHEET_URL = "https://docs.google.com/spreadsheets/d/15pvTgbZSvFKl5PHBDC-WRhRYE3tF_XWu8qkoCRivCtM/edit?usp=sharing" old
SHEET_URL = "https://docs.google.com/spreadsheets/d/1mTtVfZdIV62hWSGT4zNYkQRlzjM3DynILR1y3O1wPEs/edit?usp=sharing"
SHEET_TABS = ["Fall Quarter", "Winter Quarter", "Spring Quarter"]

CHANNEL_Z_ID = 1395968665287135262  #etl
CHANNEL_X_ID = 1388259539714969830  #media
CHANNEL_Y_ID = 1388258914629451917  #large group slides

sent_to_etl = 24
sent_to_team = 25

spreadsheet = gc.open_by_url(SHEET_URL)

def blocking_fetch_rows(sheet, tab_name):
    ws = sheet.worksheet(tab_name)
    return ws, ws.get_all_values()

def blocking_update_cell(ws, row, col, value):
    ws.update_cell(row, col, value)

def setup_media_sheet_task(bot):
    @tasks.loop(seconds=60)
    async def check_sheet():
        loop = asyncio.get_running_loop()
        for tab_name in SHEET_TABS:
            try:
                ws, all_rows = await asyncio.wait_for(
                    loop.run_in_executor(None, partial(blocking_fetch_rows, spreadsheet, tab_name)),
                    timeout=15
                )
            except asyncio.TimeoutError:
                print(f"🛑 Timeout loading '{tab_name}' tab")
                continue
            except Exception as e:
                print(f"[Error in sheet '{tab_name}']: {e}")
                continue

            for i, row in enumerate(all_rows):
                if i < 2:
                    continue

                row += [""] * max(0, sent_to_team - len(row))
                a = row[0].strip().lower()   # Column A, etl approved
                b = row[1].strip()           # Column B, requester name
                d = row[3].strip()           # Column D, event name
                j = row[9].strip()           # Column J, date form open
                k = row[10].strip()          # Column K, date form close
                l = row[11].strip().lower()  # Column L, instagram post
                m = row[12].strip().lower()  # Column M, instagram story
                r = row[17].strip().lower()  # Column R, lg slide
                status_x = row[sent_to_etl - 1].strip().lower()    # Column X, mark etl
                status_y = row[sent_to_team - 1].strip().lower()    # Column Y, mark lg/slide team

                if b and d and status_x != "sent":
                    chan = bot.get_channel(CHANNEL_Z_ID)
                    if chan:
                        await chan.send(f"📢 **{b}** has added {d} to the **media live sheet**. Waiting to be reviewed!")
                        await loop.run_in_executor(None, partial(blocking_update_cell, ws, i+1, sent_to_etl, "SENT"))
                    continue

                if a == "yes" and status_y != "sent":
                    sent = False
                    if l == "true" and m == "true":
                        chan = bot.get_channel(CHANNEL_X_ID)
                        if chan:
                            await chan.send(f"📢 The ETLs have approved **{b}**'s media request of {d}. They are requesting both an Instagram post and a story. Please check the media live sheet!")
                            sent = True
                    elif l == "true":
                        chan = bot.get_channel(CHANNEL_X_ID)
                        if chan:
                            await chan.send(f"📢 The ETLs have approved **{b}**'s media request of {d}. They are requesting an Instagram post. Please check the media live sheet!")
                            sent = True
                    elif  m == "true":
                        chan = bot.get_channel(CHANNEL_X_ID)
                        if chan:
                            await chan.send(f"📢 The ETLs have approved **{b}**'s media request of {d}. They are requesting an Instagram story. Please check the media live sheet!")
                            sent = True
                            
                    if r == "true":
                        chan = bot.get_channel(CHANNEL_Y_ID)
                        if chan:
                            await chan.send(f"📢 The ETLs have approved **{b}**'s media request of {d}. They are requesting a large group slide. Please check the media live sheet!")
                            sent = True
                    if sent:
                        await loop.run_in_executor(None, partial(blocking_update_cell, ws, i+1, sent_to_team, "SENT"))

    check_sheet.start()
