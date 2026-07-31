"""
Tracks the last time each background polling task (media_sheet,
event_sheet, link_board, discipleship_form) completed a successful run,
and warns the log channel if one of them goes quiet for too long.

Without this, a task that silently stops working (e.g. an unhandled
exception killing its discord.ext.tasks loop) could go unnoticed
indefinitely — this is the safety net for that.
"""

import time

from discord.ext import tasks

from config import (
    TASK_DISPLAY_NAMES,
    TASK_HEALTH_CHECK_INTERVAL_SECONDS,
    TASK_STALE_THRESHOLD_SECONDS,
)
from logging_utils import log_to_discord

_last_successful_run_timestamp_by_task_name = {}
_has_already_warned_stale_by_task_name = {}


def record_task_success(task_name):
    """Call this at the end of every successful iteration of a polling
    task's loop body."""
    _last_successful_run_timestamp_by_task_name[task_name] = time.time()
    _has_already_warned_stale_by_task_name[task_name] = False


def get_last_successful_run_timestamp(task_name):
    """Returns a unix timestamp, or None if the task has never completed
    a successful run since the bot started."""
    return _last_successful_run_timestamp_by_task_name.get(task_name)


def setup_task_health_monitor(bot):
    @tasks.loop(seconds=TASK_HEALTH_CHECK_INTERVAL_SECONDS)
    async def check_task_health():
        now = time.time()

        for task_name, display_name in TASK_DISPLAY_NAMES.items():
            last_run_timestamp = _last_successful_run_timestamp_by_task_name.get(task_name)

            # Give tasks a grace period right after startup before treating
            # "hasn't run yet" as a problem.
            if last_run_timestamp is None:
                continue

            seconds_since_last_success = now - last_run_timestamp
            already_warned = _has_already_warned_stale_by_task_name.get(task_name, False)

            if seconds_since_last_success > TASK_STALE_THRESHOLD_SECONDS and not already_warned:
                minutes_stale = int(seconds_since_last_success // 60)
                await log_to_discord(
                    f"⚠️ **{display_name}** hasn't completed a successful run in "
                    f"{minutes_stale} minute(s). It may have stopped working — check the logs."
                )
                _has_already_warned_stale_by_task_name[task_name] = True

    check_task_health.start()