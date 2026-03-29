import asyncio
import datetime
import logging
import time

import discord
from discord.ext import commands, tasks

from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

class WeeklyWrapUp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Table to store which channel the wrap-up should be posted in for each guild
        cf_common.user_db.conn.execute('''
            CREATE TABLE IF NOT EXISTS wrapup_channels (
                guild_id TEXT PRIMARY KEY,
                channel_id TEXT
            )
        ''')
        cf_common.user_db.conn.commit()

        # Runs every day at 23:00 UTC (We will filter for Sunday inside the loop)
        self.weekly_report_task.start()

    def cog_unload(self):
        self.weekly_report_task.cancel()

    @commands.group(brief='Weekly Chapter Wrap-Up commands', invoke_without_command=True)
    async def wrapup(self, ctx):
        """Commands to manage the Weekly Chapter Wrap-Up."""
        await ctx.send_help(ctx.command)

    @wrapup.command(name='setchannel', brief='Set the channel for weekly reports')
    @commands.has_permissions(administrator=True)
    async def wrapup_setchannel(self, ctx):
        """Sets the current channel as the destination for Sunday Weekly Wrap-Ups."""
        guild_id_str = str(ctx.guild.id)
        channel_id_str = str(ctx.channel.id)
        
        cf_common.user_db.conn.execute(
            "INSERT INTO wrapup_channels (guild_id, channel_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
            (guild_id_str, channel_id_str)
        )
        cf_common.user_db.conn.commit()
        await ctx.send(f"✅ The Weekly Chapter Wrap-Up will now be posted in {ctx.channel.mention} every Sunday night!")

    @wrapup.command(name='trigger', brief='Manually trigger the report (Admin only)')
    @commands.has_permissions(administrator=True)
    async def wrapup_trigger(self, ctx):
        """Manually generates and posts the weekly wrap-up immediately."""
        await ctx.send("⏳ Generating the Weekly Wrap-Up... this might take a minute depending on the number of members.")
        await self._generate_and_post_report(ctx.guild.id, ctx.channel.id)

    @tasks.loop(time=datetime.time(hour=23, minute=0, tzinfo=datetime.timezone.utc))
    async def weekly_report_task(self):
        """Background task that checks if it's Sunday and posts the reports."""
        # 6 represents Sunday in Python's datetime.weekday()
        if datetime.datetime.now(datetime.timezone.utc).weekday() != 6:
            return
            
        self.logger.info("It is Sunday night. Starting weekly wrap-up generation...")
        
        configs = cf_common.user_db.conn.execute("SELECT guild_id, channel_id FROM wrapup_channels").fetchall()
        for guild_id_str, channel_id_str in configs:
            await self._generate_and_post_report(int(guild_id_str), int(channel_id_str))

    @weekly_report_task.before_loop
    async def before_weekly_report_task(self):
        await self.bot.wait_until_ready()

    async def _generate_and_post_report(self, guild_id, channel_id):
        guild = self.bot.get_guild(guild_id)
        channel = self.bot.get_channel(channel_id)
        if not guild or not channel:
            return

        one_week_ago = time.time() - (7 * 24 * 3600)
        
        # Get all registered users in this guild
        users = cf_common.user_db.get_users_for_guild(guild.id)
        if not users:
            return
            
        guild_members = {user.user_id: guild.get_member(user.user_id) for user in users}
        active_handles = [user.handle for user in users if guild_members.get(user.user_id)]
        
        if not active_handles:
            return

        # Fetch current ratings for the "Quality Solves" threshold
        user_ratings = {}
        try:
            # Chunking to respect API limits
            for i in range(0, len(active_handles), 300):
                chunk = active_handles[i:i+300]
                info = await cf.user.info(handles=chunk)
                for u in info:
                    user_ratings[u.handle] = u.rating or 1200 # Default to 1200 if unrated
        except Exception as e:
            self.logger.warning(f"Failed to fetch user info for wrap-up: {e}")

        # Leaderboard Tracking Dicts
        stats_rating_gain = []
        stats_quality_solves = []
        stats_highest_rated = []
        
        for user in users:
            member = guild_members.get(user.user_id)
            if not member:
                continue
                
            handle = user.handle
            base_rating = user_ratings.get(handle, 1200)
            
            # 1. Check Rating Gains this week
            try:
                rating_history = await cf.user.rating(handle=handle)
                weekly_gain = 0
                for contest in rating_history:
                    if contest.ratingUpdateTimeSeconds >= one_week_ago:
                        weekly_gain += (contest.newRating - contest.oldRating)
                if weekly_gain > 0:
                    stats_rating_gain.append((member.display_name, weekly_gain))
            except Exception:
                pass # User might have no rated contests

            # 2. Check Recent Submissions for Quality & Highest Rated
            try:
                # 100 recent is usually enough for a week of activity
                subs = await cf.user.status(handle=handle, count=100)
                quality_solves = 0
                highest_solved = 0
                solved_problems = set()
                
                for s in subs:
                    if s.creationTimeSeconds < one_week_ago:
                        break # Subs are ordered newest first, so we can stop searching
                    if s.verdict == 'OK':
                        p_id = f"{s.problem.contestId}{s.problem.index}"
                        if p_id not in solved_problems:
                            solved_problems.add(p_id)
                            p_rating = getattr(s.problem, 'rating', 0)
                            
                            if p_rating:
                                highest_solved = max(highest_solved, p_rating)
                                # Quality solve: Rating must be >= User Rating - 100
                                if p_rating >= (base_rating - 100):
                                    quality_solves += 1
                                    
                if quality_solves > 0:
                    stats_quality_solves.append((member.display_name, quality_solves))
                if highest_solved > 0:
                    stats_highest_rated.append((member.display_name, highest_solved))
            except Exception:
                pass

            await asyncio.sleep(0.5) # Be gentle on Codeforces API!

        # 3. Check Active Streaks (Uses the table from the streaks cog)
        stats_streaks = []
        try:
            streak_rows = cf_common.user_db.conn.execute(
                "SELECT user_id, current_streak FROM user_streak WHERE current_streak > 0"
            ).fetchall()
            for uid_str, streak in streak_rows:
                mem = guild.get_member(int(uid_str))
                if mem:
                    stats_streaks.append((mem.display_name, streak))
        except Exception as e:
            self.logger.warning(f"Could not load streaks for wrap-up: {e}")

        # Sort all leaderboards
        stats_rating_gain.sort(key=lambda x: x[1], reverse=True)
        stats_quality_solves.sort(key=lambda x: x[1], reverse=True)
        stats_highest_rated.sort(key=lambda x: x[1], reverse=True)
        stats_streaks.sort(key=lambda x: x[1], reverse=True)

        # Build the Embed!
        embed = discord.Embed(
            title="📅 PSUT ACM Weekly Wrap-Up",
            description="Here is the week in review for our competitive programming chapter! Great work everyone!",
            color=discord.Color.purple(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )

        def format_top(lst, suffix=""):
            if not lst: return "> *No data this week!*"
            medals = ["🥇", "🥈", "🥉"]
            return "\n".join(f"{medals[i] if i < 3 else '🏅'} **{name}** - {val}{suffix}" for i, (name, val) in enumerate(lst[:3]))

        embed.add_field(
            name="📈 Top Rating Gainers", 
            value=f"*(Sum of official CF rating changes this week)*\n{format_top(stats_rating_gain, ' pt')}", 
            inline=False
        )
        embed.add_field(
            name="🧠 Deep Focus (Quality Solves)", 
            value=f"*(Problems solved this week with Rating ≥ Your Rating - 100)*\n{format_top(stats_quality_solves, ' ACs')}", 
            inline=False
        )
        embed.add_field(
            name="🏋️ The Iron Lifters", 
            value=f"*(Highest rated problem solved this week)*\n{format_top(stats_highest_rated)}", 
            inline=False
        )
        embed.add_field(
            name="🔥 Longest Active Streaks", 
            value=f"*(Consecutive days with at least 1 AC)*\n{format_top(stats_streaks, ' days')}", 
            inline=False
        )
        
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(text="Keep grinding! Next report is next Sunday.")

        await channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(WeeklyWrapUp(bot))
