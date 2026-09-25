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
# results, general startup/shutdown notices, etc.)
LOG_CHANNEL_ID = 1388219823384690838

# Dedicated channel for failures/errors specifically (sheet load failures,
# Discord/Calendar API errors, missing roles, etc.) — kept separate from
# LOG_CHANNEL_ID so that channel isn't diluted with genuine problems mixed
# into routine activity notices.
ERROR_LOG_CHANNEL_ID = 1541991775567224893

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

# Reuses the column freed up when the media reminder feature was removed.
# Tracks which currently-active links have already had a "new link
# posted" announcement sent, so a row only ever triggers one alert no
# matter how many times it's polled or how many times the bot restarts —
# this ties the "already announced" state to the actual sheet row instead
# of an in-memory guess based on matching content, which is what the
# in-memory version this replaced was vulnerable to.
MEDIA_LINK_ANNOUNCED_STATUS_COLUMN = 26  # Column Z

EVENT_REQUEST_SHEET_URL = "https://docs.google.com/spreadsheets/d/1qBHkcxutxlkn4ZQfx-knbuLwsnrXyYorwjq7OFUQ-M4/edit?usp=sharing"
EVENT_REQUEST_SHEET_TABS = ["Form Responses 1"]

# Single ETL approval column (previously three separate approver columns
# at X/Y/Z). The status-tracking columns below shift up to start right
# after it instead of starting at AA.
EVENT_APPROVED_STATUS_COLUMN = 24           # Column X
EVENT_ETL_NOTIFIED_STATUS_COLUMN = 25       # Column Y
EVENT_APPROVAL_NOTIFIED_STATUS_COLUMN = 26  # Column Z
EVENT_DISCORD_EVENT_ID_COLUMN = 27          # Column AA

# Reuses the column freed up when the event-sheet reminder feature was
# removed. Tracks whether a Calendar event has already been created for
# this row, independently of the one-time "approved!" notification — this
# is what lets calendar creation safely run on every poll for an approved
# row (needed so the alert and the event itself still get created even
# after the approval notification has already been sent) without ever
# creating a second, duplicate Calendar event for the same request.
EVENT_CALENDAR_CREATED_STATUS_COLUMN = 28   # Column AB

# Google Calendar that approved events get added to.
EVENT_CALENDAR_ID = "epicsanluisobispo@gmail.com"

DISCIPLESHIP_SHEET_URL = "https://docs.google.com/spreadsheets/d/1Z2nUHkSrR67NiOgUbCwKpLbZguBLFg3pAeIaMmR12WM/edit?usp=sharing"
DISCIPLESHIP_SHEET_TAB = "Form Responses 1"
DISCIPLESHIP_NOTIFIED_STATUS_COLUMN = 30  # Column AD

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
# Year migration (used by !migrate_roles)
# ----------------------------------------------------------------------
# Each (source_role, target_role) pair is processed in this EXACT order.
# Both "4th year" and "5th+ year" graduate straight to "alumni" together,
# and that step is processed BEFORE "3rd year" -> "4th year" — this
# ordering is required: if 3rd-year promotions ran first, the newly-
# promoted 4th-years would immediately get caught by the "4th year" ->
# "alumni" step in that same run, graduating a cohort that should stay
# another year. Processing top-down (highest existing year first) means a
# member promoted by an earlier step in this run is never accidentally
# re-caught and promoted again by a later step in the same run.
YEAR_MIGRATION_CHAIN = [
    ("5th+ year", "alumni"),
    ("4th year", "alumni"),
    ("3rd year", "4th year"),
    ("2nd year", "3rd year"),
    ("1st year", "2nd year"),
]

# How long (seconds) !migrate_roles waits for a typed "Yes" confirmation
# before automatically cancelling, given how consequential this action is.
MIGRATE_ROLES_CONFIRMATION_TIMEOUT_SECONDS = 30

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

    # Anyone currently approved for any class year (1st through 5th+), or
    # holding the "staff" role, gets "Active Epic Member" — except alumni,
    # who are excluded even if they still happen to hold a year-approved
    # or staff role from before graduating.
    {
        "grants_role_named": "Active Epic Member",
        "granted_if_member_has_any_of_these_role_groups": [
            ["1st year approved"],
            ["2nd year approved"],
            ["3rd year approved"],
            ["4th year approved"],
            ["5th+ year approved"],
            ["staff"],
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

# Seconds to pause after a member whose roles actually changed, while
# sweeping the whole guild, to avoid hitting Discord's rate limits. Only
# applied when a change actually happened (members needing no changes
# aren't delayed at all), and role changes are batched into a single
# add_roles + single remove_roles call per member — so this can be much
# lower than a naive "pause after every member" approach would need.
SWEEP_DELAY_BETWEEN_MEMBERS_SECONDS = 0.5

# How often (seconds) the sheet-polling background tasks run.
SHEET_POLL_INTERVAL_SECONDS = 60