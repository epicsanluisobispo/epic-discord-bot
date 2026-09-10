"""
Shared helpers for posting to Discord log channels: log_to_discord for
general activity/status notices, log_error_to_discord for failures/errors
specifically. Both fall back to a plain print if their channel can't be
found.
"""

from config import LOG_CHANNEL_ID, ERROR_LOG_CHANNEL_ID
from bot_instance import get_bot


async def log_to_discord(message_text):
    bot = get_bot()
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(message_text)
    else:
        print(f"[LOG] {message_text}")


async def log_error_to_discord(message_text):
    bot = get_bot()
    error_channel = bot.get_channel(ERROR_LOG_CHANNEL_ID)
    if error_channel:
        await error_channel.send(message_text)
    else:
        print(f"[ERROR LOG] {message_text}")