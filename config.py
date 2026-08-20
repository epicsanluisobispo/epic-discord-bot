"""
Centralized configuration for the Epic Discord bot.

This file contains every constant used across the project: Discord channel
IDs, Google Sheet URLs/tabs, spreadsheet column numbers, and the role
eligibility rules. Keeping everything here means there is exactly one place
to update an ID or a rule instead of hunting through multiple files.
"""

# ----------------------------------------------------------------------
# Discord channel IDs
# ----------------------------------------------------------------------

# Where the bot posts its own activity/status logs (role changes, sweep
# results, errors, etc.)
LOG_CHANNEL_ID = 1388219823384690838

# Where new ETL (Event/Team Leader) approval requests are posted, for both
# the media sheet and the event request sheet. Both original source files
# used the same channel ID for this, so it now lives here once.
ETL_NOTIFICATIONS_CHANNEL_ID = 1395968665287135262

# Media-request specific channel.
MEDIA_TEAM_CHANNEL_ID = 1517743044731076698

# Where the live-updating "active links" embed is posted and kept edited
# in place (replaces the old Google Sites / Flask "/media-links" page).
LINK_BOARD_CHANNEL_ID = 1532078440021491843

# "Large group slides" channel. This is the same channel used both when
# announcing an approved media request that needs a slide, and as the
# "large group" team channel for approved event requests.
LARGE_GROUP_SLIDES_CHANNEL_ID = 1517742824336916490

# Per-team channels used to announce approved event requests.
EVENT_TEAM_CHANNEL_MAP = {
    "large group": LARGE_GROUP_SLIDES_CHANNEL_ID,
    "outreach": 1517742881417330739,
    "inreach": 1517742931140808796,
    "media": MEDIA_TEAM_CHANNEL_ID,
    "mens isi": 1517743670575763557, #isi merged into one channel
    "womens isi": 1517743670575763557,
    "4th year cg": 1517743743342608514,
    "worship": 1517743293348450324,
    "boys t1": 1517743609896763512, #t1 merged into one channel
    "girls t1": 1517743609896763512,
    "retreats": 1517742971435614288,
    "prayer": 1517743338281767013,
    "staff": 1517743843041218660,
}

# ----------------------------------------------------------------------
# Google Sheets configuration
# ----------------------------------------------------------------------

MEDIA_SHEET_URL = "https://docs.google.com/spreadsheets/d/1w3zSbQyQwcFIGgE60nF5j4jSB--TZfz-M8mx3BZ8p4E/edit?usp=sharing"
MEDIA_SHEET_QUARTER_TABS = ["Fall Semester", "Spring Semester"]

# 1-indexed spreadsheet columns used as "have we already notified for this
# row?" flags, so the bot doesn't send duplicate Discord messages.
MEDIA_ETL_NOTIFIED_STATUS_COLUMN = 24   # Column X
MEDIA_TEAM_NOTIFIED_STATUS_COLUMN = 25  # Column Y

EVENT_REQUEST_SHEET_URL = "https://docs.google.com/spreadsheets/d/1qBHkcxutxlkn4ZQfx-knbuLwsnrXyYorwjq7OFUQ-M4/edit?usp=sharing"
EVENT_REQUEST_SHEET_TABS = ["Form Responses 1"]

# Single ETL approval column (previously three separate approver columns
# at X/Y/Z). The status-tracking columns below shift up to start right
# after it instead of starting at AA.
EVENT_APPROVED_STATUS_COLUMN = 24           # Column X
EVENT_ETL_NOTIFIED_STATUS_COLUMN = 25       # Column Y
EVENT_APPROVAL_NOTIFIED_STATUS_COLUMN = 26  # Column Z
EVENT_DISCORD_EVENT_ID_COLUMN = 27          # Column AA

# Google Calendar that approved events get added to.
EVENT_CALENDAR_ID = "epicsanluisobispo@gmail.com"

DISCIPLESHIP_SHEET_URL = "https://docs.google.com/spreadsheets/d/1Z2nUHkSrR67NiOgUbCwKpLbZguBLFg3pAeIaMmR12WM/edit?usp=sharing"
DISCIPLESHIP_SHEET_TAB = "Form Responses 1"
DISCIPLESHIP_NOTIFIED_STATUS_COLUMN = 30  # Column AD

# ----------------------------------------------------------------------
# Stale-request reminders
# ----------------------------------------------------------------------
# If a request has been sitting unapproved for this many days, the bot
# nudges the ETL channel once (per request) as a reminder.
REQUEST_REMINDER_THRESHOLD_DAYS = 14

# Column J ("date form open") on the media sheet doubles as the
# submission date for reminder purposes.
MEDIA_REMINDER_SENT_STATUS_COLUMN = 26  # Column Z

# ASSUMPTION, please confirm: column A on the event request sheet is a
# Google Forms "Timestamp" column recording when the request was
# submitted. If that's not what column A actually contains, this
# threshold logic will need a different column.
EVENT_SUBMITTED_TIMESTAMP_COLUMN = 1    # Column A
EVENT_REMINDER_SENT_STATUS_COLUMN = 28  # Column AB

# ----------------------------------------------------------------------
# Background task health monitoring
# ----------------------------------------------------------------------
# How often (seconds) the health monitor checks whether each polling task
# has completed a successful run recently.
TASK_HEALTH_CHECK_INTERVAL_SECONDS = 60

# If a task hasn't completed a successful run in this many seconds, the
# health monitor posts a one-time warning to the log channel (it re-warns
# only after the task recovers and then goes stale again).
TASK_STALE_THRESHOLD_SECONDS = 300  # 5 minutes

# Human-readable names for each polling task, used by the health monitor
# and the !status command. Keys must match the names each task registers
# itself under via task_health.record_task_success(...).
TASK_DISPLAY_NAMES = {
    "media_sheet": "Media sheet poller",
    "event_sheet": "Event request sheet poller",
    "link_board": "Link board updater",
    "discipleship_form": "Discipleship form poller",
}

# ----------------------------------------------------------------------
# Role eligibility rules
# ----------------------------------------------------------------------
# Each rule grants `grants_role_named` to a member if the member already
# holds ALL roles in at least one of the groups listed in
# `granted_if_member_has_any_of_these_role_groups`. If a member no longer
# qualifies, the granted role is removed again.

ROLE_GRANT_RULES = [
    # Approval for mens/womens channels
    {"grants_role_named": "mens", "granted_if_member_has_any_of_these_role_groups": [["approved", "male"]]},
    {"grants_role_named": "womens", "granted_if_member_has_any_of_these_role_groups": [["approved", "female"]]},

    # Class-year approvals
    {"grants_role_named": "1st year approved", "granted_if_member_has_any_of_these_role_groups": [["approved", "1st year"]]},
    {"grants_role_named": "2nd year approved", "granted_if_member_has_any_of_these_role_groups": [["approved", "2nd year"]]},
    {"grants_role_named": "3rd year approved", "granted_if_member_has_any_of_these_role_groups": [["approved", "3rd year"]]},
    {"grants_role_named": "4th year approved", "granted_if_member_has_any_of_these_role_groups": [["approved", "4th year"]]},
    {"grants_role_named": "5th+ year approved", "granted_if_member_has_any_of_these_role_groups": [["approved", "5th+ year"]]},
    {"grants_role_named": "alumni approved", "granted_if_member_has_any_of_these_role_groups": [["approved", "alumni"]]},

    # Anyone currently approved for any class year (1st through 5th+) gets
    # "Active Epic Member" — except alumni, who are excluded even if they
    # still happen to hold a year-approved role from before graduating.
    {
        "grants_role_named": "Active Epic Member",
        "granted_if_member_has_any_of_these_role_groups": [
            ["1st year approved"],
            ["2nd year approved"],
            ["3rd year approved"],
            ["4th year approved"],
            ["5th+ year approved"],
        ],
        "excluded_if_member_has_any_of_these_roles": ["alumni approved"],
    },

    # Community Group (CG) roles, each with multiple qualifying paths
    {"grants_role_named": "T1 men", "granted_if_member_has_any_of_these_role_groups": [["1st year approved", "male", "YES CG!!"]]},
    {"grants_role_named": "T1 women", "granted_if_member_has_any_of_these_role_groups": [["1st year approved", "female", "YES CG!!"]]},

    {
        "grants_role_named": "ISI men",
        "granted_if_member_has_any_of_these_role_groups": [
            ["2nd year approved", "male", "YES CG!!"],
            ["3rd year approved", "male", "YES CG!!"],
        ],
    },
    {
        "grants_role_named": "ISI women",
        "granted_if_member_has_any_of_these_role_groups": [
            ["2nd year approved", "female", "YES CG!!"],
            ["3rd year approved", "female", "YES CG!!"],
        ],
    },
    {
        "grants_role_named": "4th year cg",
        "granted_if_member_has_any_of_these_role_groups": [
            ["4th year approved", "YES CG!!"],
            ["5th+ year approved", "YES CG!!"],
        ],
    },
]

# ----------------------------------------------------------------------
# Misc behavior tuning
# ----------------------------------------------------------------------

# Minimum seconds between processing two role-change events for the same
# member, to avoid reacting to Discord's own multi-step role updates.
ROLE_UPDATE_COOLDOWN_SECONDS = 3

# Seconds to pause between members while sweeping the whole guild, to avoid
# hitting Discord's rate limits.
SWEEP_DELAY_BETWEEN_MEMBERS_SECONDS = 2

# How often (seconds) the sheet-polling background tasks run.
SHEET_POLL_INTERVAL_SECONDS = 60