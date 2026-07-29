"""
Discord chat commands (`!check_roles`, `!sweep_roles`, `!migrate_roles`).
"""

import asyncio

import discord
from discord.ext import commands

from logging_utils import log_to_discord
from role_manager import apply_role_rules_to_member, sweep_all_guild_members


def register_commands(bot):
    @bot.command()
    async def check_roles(ctx, member: discord.Member = None):
        if member is None:
            member = ctx.author
        await ctx.send(f"🔍 Checking roles for {member.display_name}")
        await apply_role_rules_to_member(member)
        await ctx.send("✅ Check complete.")

    @bot.command()
    @commands.has_permissions(administrator=True)
    async def sweep_roles(ctx):
        await ctx.send("🔄 Sweeping all members...")
        await log_to_discord(f"🧹 {ctx.author.display_name} triggered a sweep.")
        await sweep_all_guild_members()
        await ctx.send("✅ Sweep complete.")

    @bot.command()
    @commands.has_permissions(administrator=True)
    async def migrate_roles(ctx):
        guild = ctx.guild

        source_role_names = ["4th year", "5th+ year"]
        target_role_name = "alumni"

        source_roles = [discord.utils.get(guild.roles, name=name) for name in source_role_names]
        target_role = discord.utils.get(guild.roles, name=target_role_name)

        if not target_role or any(role is None for role in source_roles):
            await ctx.send("❌ One or more roles not found. Check role names.")
            return

        migrated_member_count = 0
        for member in guild.members:
            if any(role in member.roles for role in source_roles):
                try:
                    await member.add_roles(target_role)
                    for role in source_roles:
                        if role in member.roles:
                            await member.remove_roles(role)
                    await log_to_discord(f"🔁 Migrated {member.display_name} → {target_role.name}")
                    migrated_member_count += 1
                    await asyncio.sleep(0.1)
                except Exception as error:
                    await log_to_discord(f"❌ Failed to migrate {member.display_name}: {error}")

        await ctx.send(f"✅ Migrated {migrated_member_count} members to {target_role.name}.")
        await log_to_discord(f"✅ Batch role migration completed. {migrated_member_count} members updated.")