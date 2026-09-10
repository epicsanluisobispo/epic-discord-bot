"""
Discord chat commands (`!check_roles`, `!sweep_roles`, `!migrate_roles`,
`!status`, `!pending`).
"""

import asyncio

import discord
from discord.ext import commands

from config import (
    YEAR_MIGRATION_CHAIN,
    MIGRATE_ROLES_CONFIRMATION_TIMEOUT_SECONDS,
    SWEEP_DELAY_BETWEEN_MEMBERS_SECONDS,
)
from logging_utils import log_to_discord, log_error_to_discord
from role_manager import apply_role_rules_to_member, sweep_all_guild_members
from diagnostics import build_status_report, build_pending_report


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

        migration_steps_text = "\n".join(
            f"• **{source_role_name}** → **{target_role_name}**"
            for source_role_name, target_role_name in YEAR_MIGRATION_CHAIN
        )

        await ctx.send(
            "⚠️ This will migrate **every member's class year up one level**, server-wide:\n"
            f"{migration_steps_text}\n\n"
            "This can affect a large number of members and cannot be undone automatically. "
            f"Type **Yes** within {MIGRATE_ROLES_CONFIRMATION_TIMEOUT_SECONDS} seconds to confirm."
        )

        def confirmation_check(message):
            return (
                message.author == ctx.author
                and message.channel == ctx.channel
                and message.content.strip().lower() == "yes"
            )

        try:
            await bot.wait_for(
                "message", check=confirmation_check, timeout=MIGRATE_ROLES_CONFIRMATION_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            await ctx.send("❌ Migration cancelled — no confirmation received in time.")
            return

        await ctx.send("🔄 Migrating roles — this may take a while for a large server...")
        await log_to_discord(f"🧬 {ctx.author.display_name} confirmed and triggered a full year migration.")

        total_migrated_count = 0
        per_tier_summary_lines = []

        # Processed in the exact order YEAR_MIGRATION_CHAIN defines (highest
        # class year first) — see the comment on YEAR_MIGRATION_CHAIN in
        # config.py for why that order is required for correctness.
        for source_role_name, target_role_name in YEAR_MIGRATION_CHAIN:
            source_role = discord.utils.get(guild.roles, name=source_role_name)
            target_role = discord.utils.get(guild.roles, name=target_role_name)

            if not source_role or not target_role:
                await log_error_to_discord(
                    f"❌ Migration step '{source_role_name}' → '{target_role_name}' skipped: "
                    f"one or both roles not found on this server."
                )
                per_tier_summary_lines.append(
                    f"• {source_role_name} → {target_role_name}: ❌ role not found, skipped"
                )
                continue

            tier_migrated_count = 0
            for member in guild.members:
                if source_role in member.roles:
                    try:
                        await member.add_roles(target_role)
                        await member.remove_roles(source_role)
                        await log_to_discord(
                            f"🔁 Migrated **{member.display_name}**: {source_role.name} → {target_role.name}"
                        )
                        tier_migrated_count += 1
                        await asyncio.sleep(SWEEP_DELAY_BETWEEN_MEMBERS_SECONDS)
                    except Exception as error:
                        await log_error_to_discord(
                            f"❌ Failed to migrate {member.display_name} "
                            f"({source_role.name} → {target_role.name}): {error}"
                        )

            per_tier_summary_lines.append(f"• {source_role_name} → {target_role_name}: {tier_migrated_count} migrated")
            total_migrated_count += tier_migrated_count

        summary_text = "\n".join(per_tier_summary_lines)
        await ctx.send(f"✅ Migration complete. {total_migrated_count} total members migrated.\n{summary_text}")
        await log_to_discord(f"✅ Full year migration completed. {total_migrated_count} members updated.\n{summary_text}")

    @bot.command()
    @commands.has_permissions(administrator=True)
    async def status(ctx):
        await ctx.send("🔍 Checking status, one moment...")
        report = await build_status_report()
        await ctx.send(report)

    @bot.command()
    @commands.has_permissions(administrator=True)
    async def pending(ctx):
        await ctx.send("🔍 Gathering pending requests, one moment...")
        report = await build_pending_report()
        await ctx.send(report)