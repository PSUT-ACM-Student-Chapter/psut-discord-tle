import os
import io
import asyncio
import sqlite3
import logging
import datetime
import typing
import discord
from discord.ext import commands
from collections import defaultdict

# Use the Agg backend to prevent threading issues with matplotlib in an async environment
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Import TLE's standard cf_common to use existing DB connections natively
from tle.util import codeforces_common as cf_common

class GitGudAnalytics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate_plot(self, member_name, time_spent_by_rating, rating_counts, solves_by_date, date_range_str):
        """Generates the plot synchronously (called in an executor to avoid blocking)."""
        plt.style.use('dark_background')
        
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 15))
        fig.suptitle(f"GitGud Analytics for {member_name}{date_range_str}", fontsize=18, fontweight='bold', color='white')

        # 1. Average Time Spent
        ratings1 = sorted(time_spent_by_rating.keys())
        if ratings1:
            avg_times = [sum(time_spent_by_rating[r]) / len(time_spent_by_rating[r]) for r in ratings1]
            
            # Scatter points for individual solves
            scatter_x = []
            scatter_y = []
            for r in ratings1:
                for t in time_spent_by_rating[r]:
                    scatter_x.append(str(r))
                    scatter_y.append(t)

            ax1.scatter(scatter_x, scatter_y, alpha=0.5, color='#ff7f50', zorder=2, label='Individual Solves')
            ax1.plot([str(r) for r in ratings1], avg_times, color='white', linewidth=2, marker='o', zorder=3, label='Average Time')
            
            ax1.set_title("Time Spent per Rating", fontsize=14)
            ax1.set_xlabel("Problem Rating")
            ax1.set_ylabel("Time (Hours)")
            ax1.tick_params(axis='x', rotation=45)
            ax1.grid(axis='y', linestyle='--', alpha=0.3, zorder=1)
            ax1.legend()

        # 2. Rating Distribution
        ratings2 = sorted(rating_counts.keys())
        if ratings2:
            counts2 = [rating_counts[r] for r in ratings2]
            ax2.bar([str(r) for r in ratings2], counts2, color='#87ceeb', edgecolor='white')
            ax2.set_title("Total Solved by Rating", fontsize=14)
            ax2.set_xlabel("Problem Rating")
            ax2.set_ylabel("Number of Solves")
            ax2.tick_params(axis='x', rotation=45)
            ax2.grid(axis='y', linestyle='--', alpha=0.3)

        # 3. Frequency per day
        dates = sorted(solves_by_date.keys())
        if dates:
            # Fill in empty days with 0 solves for a proper timeline
            min_date = min(dates)
            max_date = max(dates)
            all_dates = [min_date + datetime.timedelta(days=i) for i in range((max_date - min_date).days + 1)]
            counts3 = [solves_by_date[d] for d in all_dates]
            
            ax3.bar(all_dates, counts3, color='#3cb371', width=1.0)
            ax3.set_title("GitGud Solves Over Time", fontsize=14)
            ax3.set_xlabel("Date")
            ax3.set_ylabel("Solves per Day")
            ax3.xaxis.set_major_formatter(mdates.DateFormatter('%b %d, %Y'))
            ax3.tick_params(axis='x', rotation=45)
            ax3.grid(True, linestyle='--', alpha=0.3)

        plt.tight_layout(rect=[0, 0.03, 1, 0.95]) 

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', transparent=False)
        buf.seek(0)
        plt.close(fig)
        return buf

    @commands.command(aliases=['ggstats'])
    async def gitgudplot(self, ctx, member: typing.Optional[discord.Member] = None, start_date: str = None, end_date: str = None):
        """Plots GitGud analytics: Time spent, rating distribution, and solving frequency.
        Usage: ;gitgudplot [member] [start_date YYYY-MM-DD] [end_date YYYY-MM-DD]
        """
        member = member or ctx.author
        
        start_ts = 0
        end_ts = datetime.datetime.now().timestamp()
        date_range_str = ""

        # Parse date filters if provided
        try:
            if start_date:
                start_ts = datetime.datetime.strptime(start_date, "%Y-%m-%d").timestamp()
                date_range_str += f"\n(From {start_date}"
            if end_date:
                end_ts = datetime.datetime.strptime(end_date, "%Y-%m-%d").timestamp() + 86399
                date_range_str += f" to {end_date})" if start_date else f"\n(Until {end_date})"
            elif start_date:
                date_range_str += ")"
        except ValueError:
            return await ctx.send("❌ Invalid date format. Please use YYYY-MM-DD (e.g., 2023-01-01).")

        if not cf_common.user_db or not cf_common.user_db.conn:
            return await ctx.send("❌ Bot database not initialized yet.")

        # Using TLE's built-in sqlite3 connection
        conn = cf_common.user_db.conn
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='challenge'")
        if not cursor.fetchone():
            return await ctx.send("❌ 'challenge' table not found. Gitgud might not be initialized or active.")
        
        cursor.execute("PRAGMA table_info(challenge)")
        cols = [row[1] for row in cursor.fetchall()]
        
        if 'issue_time' not in cols or 'finish_time' not in cols:
            return await ctx.send("❌ Unsupported schema: Missing time columns in `challenge` table.")
        
        if 'guild_id' in cols:
            query = f"SELECT * FROM challenge WHERE user_id = ? AND guild_id = ? AND finish_time IS NOT NULL"
            params = (member.id, ctx.guild.id)
        else:
            query = f"SELECT * FROM challenge WHERE user_id = ? AND finish_time IS NOT NULL"
            params = (member.id,)
            
        cursor.execute(query, params)
        rows = cursor.fetchall()
        tasks = [dict(zip(cols, row)) for row in rows]

        if not tasks:
            return await ctx.send(f"📊 **{member.display_name}** hasn't completed any GitGud challenges yet.")

        time_spent_by_rating = defaultdict(list)
        rating_counts = defaultdict(int)
        solves_by_date = defaultdict(int)

        # Retrieve ratings directly from TLE's memory cache to avoid DB locking and path issues
        if not cf_common.cache2 or not cf_common.cache2.problem_cache:
            return await ctx.send("❌ Internal problem cache not initialized.")

        problems = cf_common.cache2.problem_cache.problems
        rating_by_cid_index = {(p.contestId, p.index): p.rating for p in problems if p.rating}
        rating_by_name = {p.name: p.rating for p in problems if p.rating}

        for t in tasks:
            c_id = t.get('contest_id') or t.get('contestId')
            idx = t.get('p_index') or t.get('problem_index') or t.get('index')
            # TLE stores the problem name inside the 'problem_id' column for challenges
            p_name = t.get('problem_id') or t.get('problem_name') or t.get('name')
            
            rating = None
            if c_id and idx:
                # Contest IDs are usually integers, indexes are strings (like 'A', 'B1')
                rating = rating_by_cid_index.get((int(c_id), str(idx)))
            
            if not rating and p_name:
                rating = rating_by_name.get(p_name)
                
            if rating:
                issue = t.get('issue_time')
                finish = t.get('finish_time')
                
                if finish and start_ts <= finish <= end_ts:
                    if issue and finish >= issue:
                        time_spent_hours = (finish - issue) / 3600.0
                        time_spent_by_rating[rating].append(time_spent_hours)
                    
                    rating_counts[rating] += 1
                    finish_date = datetime.datetime.fromtimestamp(finish).date()
                    solves_by_date[finish_date] += 1

        if not rating_counts:
            return await ctx.send("⚠️ Found your GitGud history, but couldn't map the ratings or no solves found in the given date range.")

        msg = await ctx.send("📊 Crunching the numbers and generating your plots...")

        loop = asyncio.get_running_loop()
        buf = await loop.run_in_executor(
            None, 
            self.generate_plot, 
            member.display_name, 
            time_spent_by_rating, 
            rating_counts, 
            solves_by_date,
            date_range_str
        )

        await msg.delete()
        await ctx.send(file=discord.File(buf, filename=f'ggstats_{member.id}.png'))

async def setup(bot):
    await bot.add_cog(GitGudAnalytics(bot))
