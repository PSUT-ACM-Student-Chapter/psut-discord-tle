import os
import io
import asyncio
import logging
import datetime
import aiosqlite
import discord
from discord.ext import commands
from collections import defaultdict

# Use the Agg backend to prevent threading issues with matplotlib in an async environment
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

class GitGudAnalytics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate_plot(self, member_name, time_spent_by_rating, rating_counts, solves_by_date):
        """Generates the plot synchronously (called in an executor to avoid blocking)."""
        # Set up a dark theme nicely suited for Discord
        plt.style.use('dark_background')
        
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 15))
        fig.suptitle(f"GitGud Analytics for {member_name}", fontsize=18, fontweight='bold', color='white')

        # 1. Average Time Spent
        ratings1 = sorted(time_spent_by_rating.keys())
        if ratings1:
            avg_times = [sum(time_spent_by_rating[r]) / len(time_spent_by_rating[r]) for r in ratings1]
            ax1.bar([str(r) for r in ratings1], avg_times, color='#ff7f50', edgecolor='white')
            ax1.set_title("Average Time Spent per Rating", fontsize=14)
            ax1.set_xlabel("Problem Rating")
            ax1.set_ylabel("Average Time (Hours)")
            ax1.tick_params(axis='x', rotation=45)
            ax1.grid(axis='y', linestyle='--', alpha=0.3)

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
            counts3 = [solves_by_date[d] for d in dates]
            ax3.plot(dates, counts3, marker='o', linestyle='-', color='#3cb371', linewidth=2, markersize=6)
            ax3.set_title("GitGud Solves Over Time", fontsize=14)
            ax3.set_xlabel("Date")
            ax3.set_ylabel("Solves per Day")
            ax3.xaxis.set_major_formatter(mdates.DateFormatter('%b %d, %Y'))
            ax3.tick_params(axis='x', rotation=45)
            ax3.grid(True, linestyle='--', alpha=0.3)

        plt.tight_layout(rect=[0, 0.03, 1, 0.95]) # Adjust for suptitle

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', transparent=False)
        buf.seek(0)
        plt.close(fig) # Prevent memory leaks
        return buf

    @commands.command(aliases=['ggstats', 'ggplot'])
    async def gitgudplot(self, ctx, member: discord.Member = None):
        """Plots GitGud analytics: Time spent, rating distribution, and solving frequency.
        Usage: ;gitgudplot [member]
        """
        member = member or ctx.author
        
        user_db_path = 'data/user.db'
        cache_db_path = 'data/cache.db'
        
        if not os.path.exists(user_db_path) or not os.path.exists(cache_db_path):
            return await ctx.send("❌ Internal databases not found.")

        tasks = []
        # Connect to user.db to fetch GitGud history
        async with aiosqlite.connect(user_db_path) as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gud'")
            if not await cursor.fetchone():
                return await ctx.send("❌ 'gud' table not found. Gitgud might not be initialized or active.")
            
            cursor = await db.execute("PRAGMA table_info(gud)")
            cols = [row[1] for row in await cursor.fetchall()]
            
            if 'issue_time' not in cols or 'finish_time' not in cols:
                return await ctx.send("❌ Unsupported schema: Missing time columns in `gud` table.")
            
            # Accommodate variations in table schemas across different TLE forks
            if 'guild_id' in cols:
                query = f"SELECT * FROM gud WHERE user_id = ? AND guild_id = ? AND finish_time IS NOT NULL"
                params = (member.id, ctx.guild.id)
            else:
                query = f"SELECT * FROM gud WHERE user_id = ? AND finish_time IS NOT NULL"
                params = (member.id,)
                
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            
            for row in rows:
                tasks.append(dict(zip(cols, row)))

        if not tasks:
            return await ctx.send(f"📊 **{member.display_name}** hasn't completed any GitGud challenges yet.")

        time_spent_by_rating = defaultdict(list)
        rating_counts = defaultdict(int)
        solves_by_date = defaultdict(int)

        # Cross-reference with cache.db to find the ratings of these problems
        async with aiosqlite.connect(cache_db_path) as cache_db:
            p_cur = await cache_db.execute("PRAGMA table_info(problem)")
            p_cols = [row[1] for row in await p_cur.fetchall()]
            
            cid_col = 'contestId' if 'contestId' in p_cols else 'contest_id'
            
            if 'rating' in p_cols:
                query = f'SELECT rating FROM problem WHERE {cid_col} = ? AND "index" = ?'
                
                for t in tasks:
                    c_id = t.get('contest_id') or t.get('contestId')
                    idx = t.get('problem_index') or t.get('index')
                    
                    if c_id and idx:
                        res_cur = await cache_db.execute(query, (c_id, idx))
                        res = await res_cur.fetchone()
                        
                        if res and res[0]:
                            rating = int(res[0])
                            issue = t['issue_time']
                            finish = t['finish_time']
                            
                            # Only count if times are valid
                            if finish >= issue:
                                time_spent_hours = (finish - issue) / 3600.0
                                time_spent_by_rating[rating].append(time_spent_hours)
                            
                            rating_counts[rating] += 1
                            finish_date = datetime.datetime.fromtimestamp(finish).date()
                            solves_by_date[finish_date] += 1

        if not rating_counts:
            return await ctx.send("⚠️ Found your GitGud history, but couldn't map the ratings. Cache might be empty.")

        msg = await ctx.send("📊 Crunching the numbers and generating your plots...")

        # Run the CPU-heavy plotting function in a non-blocking thread
        loop = asyncio.get_running_loop()
        buf = await loop.run_in_executor(
            None, 
            self.generate_plot, 
            member.display_name, 
            time_spent_by_rating, 
            rating_counts, 
            solves_by_date
        )

        await msg.delete()
        await ctx.send(file=discord.File(buf, filename=f'ggstats_{member.id}.png'))

def setup(bot):
    async def setup(bot):
        await bot.add_cog(GitGudAnalytics(bot))
