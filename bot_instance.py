"""
Holds the single shared discord.Bot instance so other modules (like
logging_utils.py and role_manager.py) can reach it without importing
main.py directly, which would create a circular import.
"""

_bot = None


def set_bot(bot_instance):
    global _bot
    _bot = bot_instance


def get_bot():
    if _bot is None:
        raise RuntimeError("Bot instance has not been set yet. Call set_bot() from main.py first.")
    return _bot