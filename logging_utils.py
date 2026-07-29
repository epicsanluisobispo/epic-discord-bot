"""
Shared helper for posting bot activity/status messages to the Discord log
channel, falling back to a plain print if the channel can't be found.
"""

from config import LOG_CHANNEL_ID
from bot_instance import get_bot


async def log_to_discord(message_text):
    bot = get_bot()
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(message_text)
    else:
        print(f"[LOG] {message_text}")