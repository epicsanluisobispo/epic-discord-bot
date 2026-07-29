"""
Flask web server run alongside the bot: a simple uptime-check endpoint plus
a public page listing currently-active event links pulled from the media
sheet.
"""

import logging
from datetime import datetime, time
from threading import Thread

import pytz
from dateutil import parser
from flask import Flask, Response

from config import MEDIA_SHEET_QUARTER_TABS

logger = logging.getLogger(__name__)

app = Flask(__name__)

PACIFIC_TIMEZONE = pytz.timezone("America/Los_Angeles")


@app.route("/")
def home():
    return "✅ Bot is running!"


@app.route("/media-links")
def media_links():
    # Imported here (rather than at module load time) to avoid a circular
    # import, since media_sheet.py doesn't need to know about the web server.
    from media_sheet import spreadsheet

    now = datetime.now(PACIFIC_TIMEZONE)
    logger.info("🌐 Media-links called, now = %s", now)

    html = """
    <html>
    <head>
        <title>Media Links</title>
        <style>
            body {
                font-family: 'Segoe UI', sans-serif;
                max-width: 700px;
                margin: 40px auto;
                padding: 20px;
                background: #f9f9f9;
                color: #333;
            }
            h1 { text-align: center; color: #444; }
            ul { list-style-type: none; padding: 0; }
            li {
                background: white;
                margin: 10px 0;
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }
            a { text-decoration: none; color: #0073e6; font-weight: bold; }
            .no-links { text-align: center; font-style: italic; color: #888; margin-top: 40px; }
        </style>
    </head>
    <body>
        <h1>Active Epic SLO Links</h1>
        <ul>
    """

    active_link_count = 0

    for tab_name in MEDIA_SHEET_QUARTER_TABS:
        logger.info(f"➡️ Loading tab '{tab_name}'")
        try:
            worksheet = spreadsheet.worksheet(tab_name)
            rows = worksheet.get_all_values()
            logger.info(f"   ✅ Loaded {len(rows)} rows")
        except Exception as error:
            logger.error(f"   ❌ Failed to load tab {tab_name}: {error}")
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
                logger.error(f"     ❌ Date parse error (row {row_index + 1}): {error}")
                continue

            if window_start <= now <= window_end:
                display_name = event_name if event_name else event_link
                html += f"<li><a href='{event_link}' target='_blank'>{display_name}</a></li>"
                active_link_count += 1

    if active_link_count == 0:
        html += "<div class='no-links'>No active links at the moment. Check back soon!</div>"

    html += "</ul></body></html>"
    return Response(html, mimetype="text/html")


def run_flask_app():
    app.run(host="0.0.0.0", port=8080)


def start_flask_in_background_thread():
    Thread(target=run_flask_app).start()