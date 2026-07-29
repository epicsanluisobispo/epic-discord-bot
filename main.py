"""
Entry point: creates the Discord bot, wires up event handlers and
commands, starts the Flask uptime server, and runs the bot.
"""

import os
import logging

import discord
from discord.ext import commands

from bot_instance import set_bot
from logging_utils import log_to_discord
from role_manager import handle_member_role_update, sweep_all_guild_members
from bot_commands import register_commands
from web_server import start_flask_in_background_thread
from media_sheet import setup_media_sheet_task
from event_sheet import setup_event_sheet_task

logging.basicConfig(level=logging.INFO)

print("Discord.py version:", discord.__version__)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
set_bot(bot)

register_commands(bot)

_media_sheet_task_started = False
_event_sheet_task_started = False


@bot.event
async def on_ready():
    global _media_sheet_task_started, _event_sheet_task_started

    print(f"✅ Logged in as {bot.user}")
    await log_to_discord(f"🤖 Bot started as {bot.user}")
    await sweep_all_guild_members()

    if not _media_sheet_task_started:
        setup_media_sheet_task(bot)
        _media_sheet_task_started = True

    if not _event_sheet_task_started:
        setup_event_sheet_task(bot)
        _event_sheet_task_started = True


@bot.event
async def on_member_update(before, after):
    await handle_member_role_update(before, after)


if __name__ == "__main__":
    start_flask_in_background_thread()
    bot.run(os.environ["BOT_TOKEN"])