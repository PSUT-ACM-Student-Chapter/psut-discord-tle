import asyncio
import datetime
import logging

import discord
from discord.ext import commands, tasks

from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

class Streaks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Safely initialize the new table inside the existing SQLite DB
        cf_common.user_db.conn.execute('''
            CREATE TABLE IF NOT EXISTS user_streak (
                user_id TEXT PRIMARY KEY,
                current_streak INTEGER DEFAULT 0,
                max_streak INTEGER DEFAULT 0,
                last_ac_date TEXT
            )
        ''')
        cf_common.user_db.conn.commit()

        # Start the background checker
        self.update_streaks_task.start()

    def cog_unload(self):
        self.update_streaks_task.cancel()

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc))
    async def update_streaks_task(self):
        """Runs daily at midnight UTC to process streaks for all registered users."""
        self.logger.info("Starting daily streak background update...")
        try:
            users = cf_common.user_db.conn.execute(
                "SELECT DISTINCT user_id, handle FROM user_handle"
            ).fetchall()
        except Exception as e:
            self.logger.error(f"Failed to fetch users from DB: {e}")
            return

        for user_id_int, handle in users:
            await self._update_user_streak(user_id_int, handle)
            await asyncio.sleep(0.5) # Prevent rate-limiting from Codeforces API

        self.logger.info("Daily streak update completed successfully.")

    @update_streaks_task.before_loop
    async def before_update_streaks_task(self):
        await self.bot.wait_until_ready()

    async def _update_user_streak(self, user_id_int, handle):
        """Core logic to fetch submissions, check dates, and update the streak."""
        user_id_str = str(user_id_int)
        
        row = cf_common.user_db.conn.execute(
            "SELECT current_streak, max_streak, last_ac_date FROM user_streak WHERE user_id = ?",
            (user_id_str,)
        ).fetchone()

        current_streak = row[0] if row else 0
        max_streak = row[1] if row else 0
        last_ac_date = row[2] if row else None

        try:
            # Fetch recent submissions
            subs = await cf.user.status(handle=handle, count=50)
        except Exception as e:
            self.logger.warning(f"Failed to fetch CF status for {handle}: {e}")
            return current_streak, max_streak, False

        # Work in UTC since Codeforces API timestamps are global
        today_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
        yesterday_str = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')

        ac_dates = set()
        for s in subs:
            if s.verdict == 'OK':
                date_str = datetime.datetime.fromtimestamp(s.creationTimeSeconds, datetime.timezone.utc).strftime('%Y-%m-%d')
                ac_dates.add(date_str)

        today_ac = today_str in ac_dates
        yesterday_ac = yesterday_str in ac_dates

        # Calculate state machine
        if today_ac:
            if last_ac_date == yesterday_str:
                current_streak += 1
                last_ac_date = today_str
            elif last_ac_date != today_str:
                # Started a fresh streak today
                current_streak = 1
                last_ac_date = today_str
            max_streak = max(max_streak, current_streak)
        elif yesterday_ac:
            if last_ac_date != yesterday_str and last_ac_date != today_str:
                # Catching up a missed midnight sync
                current_streak = 1 if current_streak == 0 else current_streak + 1
                last_ac_date = yesterday_str
                max_streak = max(max_streak, current_streak)
        else:
            if last_ac_date != today_str and last_ac_date != yesterday_str:
                # No AC yesterday or today. Streak broken.
                current_streak = 0

        # Upsert the new values into the DB
        cf_common.user_db.conn.execute('''
            INSERT INTO user_streak (user_id, current_streak, max_streak, last_ac_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
            current_streak=excluded.current_streak,
            max_streak=excluded.max_streak,
            last_ac_date=excluded.last_ac_date
        ''', (user_id_str, current_streak, max_streak, last_ac_date))
        cf_common.user_db.conn.commit()

        return current_streak, max_streak, today_ac

    async def _assign_streak_roles(self, member, streak):
        """Automatically assigns reward roles based on streak thresholds."""
        guild = member.guild
        role_map = {
            7: "7-Day Streak",     # Create these roles in your Discord Server!
            30: "30-Day Streak",
            100: "100-Day Streak"
        }
        
        highest_role = None
        for threshold, role_name in sorted(role_map.items(), reverse=True):
            if streak >= threshold:
                # Looks for exact role name match in the server
                highest_role = discord.utils.get(guild.roles, name=role_name)
                break

        if highest_role and highest_role not in member.roles:
            try:
                await member.add_roles(highest_role)
            except discord.Forbidden:
                pass # Bot lacks permission to assign roles, ignore silently

    @commands.group(brief='Daily AC Streak commands', invoke_without_command=True)
    async def streak(self, ctx, member: discord.Member = None):
        """Shows your current consecutive days of solving Codeforces problems."""
        member = member or ctx.author
        
        # Use TLE's built-in DB lookup to get the handle
        handle = cf_common.user_db.get_handle(member.id, ctx.guild.id)
        if not handle:
            return await ctx.send(f"{member.display_name} has not identified their Codeforces handle. Use `;handle set`.")

        # Real-time check so users get immediate feedback upon getting an AC!
        current_streak, max_streak, today_ac = await self._update_user_streak(member.id, handle)

        # Attempt to award roles
        await self._assign_streak_roles(member, current_streak)

        # Build the Embed UI
        embed = discord.Embed(
            title=f"🔥 Streak for {handle} 🔥",
            color=discord.Color.orange() if current_streak > 0 else discord.Color.default()
        )
        
        streak_text = f"**{current_streak}** days" if current_streak > 0 else "0 days 😢"
        embed.add_field(name="Current Streak", value=streak_text, inline=True)
        embed.add_field(name="Max Streak", value=f"**{max_streak}** days", inline=True)

        if today_ac:
            embed.set_footer(text="✅ You have already submitted an AC today! Keep it up!")
        elif current_streak > 0:
            embed.set_footer(text="⚠️ You haven't got an AC today! Go solve a problem to keep the streak alive!")
        else:
            embed.set_footer(text="Get an AC today to start your streak!")

        await ctx.send(embed=embed)

    @streak.command(name='top', aliases=['leaderboard', 'lb'])
    async def streak_top(self, ctx):
        """Shows the server leaderboard for Daily AC Streaks."""
        rows = cf_common.user_db.conn.execute('''
            SELECT user_id, current_streak, max_streak
            FROM user_streak
            WHERE current_streak > 0
            ORDER BY current_streak DESC
        ''').fetchall()

        # Map to actual members currently in this Discord server
        guild_member_ids = {str(m.id): m for m in ctx.guild.members}
        
        board = []
        for user_id_str, cur, mx in rows:
            if user_id_str in guild_member_ids:
                board.append((guild_member_ids[user_id_str].display_name, cur, mx))

        if not board:
            return await ctx.send("No active streaks found for members of this server! 😢")

        board = board[:10] # Top 10

        embed = discord.Embed(title="🔥 Server Streak Leaderboard 🔥", color=discord.Color.red())
        desc = ""
        for i, (name, cur, mx) in enumerate(board, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🏅"
            desc += f"{medal} **{name}** - {cur} days (Max: {mx})\n"
            
        embed.description = desc
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Streaks(bot))
