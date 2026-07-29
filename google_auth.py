"""
Shared Google service-account authentication for Sheets and Calendar
access, so credential-loading code isn't duplicated across media_sheet.py
and event_sheet.py.
"""

import os
import json

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SPREADSHEET_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_AND_CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar",
]


def _load_service_account_credentials(scopes):
    service_account_info = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    return Credentials.from_service_account_info(service_account_info, scopes=scopes)


def get_sheets_client(scopes=SPREADSHEET_SCOPES):
    """Return an authorized gspread client only (no calendar access)."""
    credentials = _load_service_account_credentials(scopes)
    return gspread.authorize(credentials)


def get_sheets_client_and_credentials(scopes):
    """Return both an authorized gspread client and the underlying
    credentials object, for callers (like event_sheet.py) that also need
    to build a Calendar service from the same credentials."""
    credentials = _load_service_account_credentials(scopes)
    client = gspread.authorize(credentials)
    return client, credentials


def get_calendar_service(credentials):
    return build("calendar", "v3", credentials=credentials)