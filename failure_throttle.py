"""
Prevents a repeating failure (e.g. a sheet that's unreachable for an hour)
from posting the same warning to the log channel on every single poll. A
given failure `key` is only logged once; it won't log again until a
matching `clear_failure(key)` call (on the next success) resets it.
"""

from logging_utils import log_to_discord

_already_warned_keys = set()


async def log_failure_once(key, message):
    """Log `message` to the log channel only if we haven't already logged
    a failure for this same `key` since it last recovered."""
    if key in _already_warned_keys:
        return
    _already_warned_keys.add(key)
    await log_to_discord(message)


def clear_failure(key):
    """Call this whenever the operation associated with `key` succeeds, so
    the next failure for that same key is logged again instead of staying
    silenced forever."""
    _already_warned_keys.discard(key)