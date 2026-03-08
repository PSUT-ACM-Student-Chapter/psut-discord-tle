import discord
from discord.ext import commands
import math
import time
from collections import defaultdict
import datetime

# Import standard TLE utilities based on your bot's structure
from tle.util import codeforces_common as cf_common
from tle.util import codeforces_api as cf

class Slacker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Cache to prevent spamming the Codeforces API
        self.submission_cache = {}
        # Cache Time-To-Live in seconds (3600 seconds = 1 hour)
        self.cache_ttl = 3600

    async def _get_ac_submissions(self, handle):
        now = time.time()
        # 1. Check if we have valid cached data
        if handle in self.submission_cache:
            cache_time, ac_subs = self.submission_cache[handle]
            if now - cache_time < self.cache_ttl:
                return ac_subs

        # 2. If no valid cache, fetch from Codeforces API
        submissions = await cf.user.status(handle=handle)
        
        # This explicitly guarantees only Accepted ('OK') questions are considered
        ac_subs = [sub for sub in submissions if sub.verdict == 'OK']
        
        # 3. Save to cache with the current timestamp
        self.submission_cache[handle] = (now, ac_subs)
        return ac_subs

    def _calculate_slacker_metrics(self, history_counts, current_count, z_threshold=-1.0, grace_minimum=5):
        """
        Mathematical logic to determine if someone is slacking.
        :param history_counts: List of integers (problems solved in previous weeks).
        :param current_count: Int (problems solved in the current week).
        :param z_threshold: Float (How many standard deviations below the mean makes them a slacker).
        :param grace_minimum: Int (Absolute minimum problems to be safe from slacking).
        """
        # 1. Grace condition: If they solved enough to meet the absolute minimum, they are safe.
        if current_count >= grace_minimum:
            return False, 0.0, 0.0, 0.0

        # 2. No history: Assume they are slacking if they haven't met the grace minimum.
        if not history_counts:
            return True, 0.0, 0.0, -99.9

        # 3. Calculate Mean (μ)
        n = len(history_counts)
        mu = sum(history_counts) / n

        # 4. Calculate Standard Deviation (σ)
        variance = sum((x - mu) ** 2 for x in history_counts) / n
        sigma = math.sqrt(variance)

        # 5. Calculate Z-Score (The Curve)
        if sigma == 0:
            # If they are perfectly consistent (σ=0), they slack if they fall below their exact mean.
            # CRITICAL FIX: If their mean is exactly 0 (a dead account) and they solved 0, they are slacking!
            if mu == 0 and current_count == 0:
                z_score = -99.9
                is_slacking = True
            else:
                z_score = -99.9 if current_count < mu else 0.0
                is_slacking = current_count < mu
        else:
            z_score = (current_count - mu) / sigma
            # In a normal distribution curve, a z-score <= threshold flags them
            is_slacking = z_score <= z_threshold

        return is_slacking, mu, sigma, z_score

    @commands.command(brief="Mathematically calculates who is slacking in training", usage="[weeks_history] [z_threshold] [grace_minimum]")
    async def slackers(self, ctx, weeks_history: int = 10, z_threshold: float = -0.5, grace_minimum: int = 2):
        """
        Finds out who is slacking based on a standard deviation curve of their own past performance.
        
        weeks_history: How many past weeks to analyze to build the curve (default 10).
        z_threshold: How many standard dev below mean triggers 'slacking' (closer to 0.0 is stricter, default -0.5).
        grace_minimum: Absolute minimum problems to be completely safe from slacking (default 2).
        """
        # Notify user that the heavy mathematical lifting is starting
        calculating_msg = await ctx.send("📊 Crunching the historical data and building performance curves...")

        # 1. Get all handles registered in this Discord server from TLE's database
        try:
            # Using get_handles_for_guild based on your codeforces_common.py
            handles = [handle for discord_id, handle in cf_common.user_db.get_handles_for_guild(ctx.guild.id)]
        except Exception as e:
            return await ctx.send(f"❌ Error fetching users from database: {str(e)}")

        if not handles:
            return await ctx.send("No Codeforces handles are registered in this server.")

        now = time.time()
        one_week_sec = 7 * 24 * 60 * 60
        
        slackers_found = []

        # 2. Iterate through each handle and fetch their submissions
        for handle in handles:
            try:
                # Use our cached helper instead of hitting the API directly every time
                ac_submissions = await self._get_ac_submissions(handle)
            except Exception:
                continue # Skip if API fails for a user (e.g., handle changed/deleted)

            # Group submissions into weeks relative to right now
            weekly_solves = defaultdict(set) # Using a set to count unique problems solved

            for sub in ac_submissions:
                time_diff = now - sub.creationTimeSeconds
                weeks_ago = int(time_diff // one_week_sec)
                
                # We only care about the current week (0) and the historical weeks up to `weeks_history`
                if 0 <= weeks_ago <= weeks_history:
                    # Storing problem names in a set prevents double-counting if they solved the same problem twice
                    problem_id = f"{sub.problem.contestId}{sub.problem.index}"
                    weekly_solves[weeks_ago].add(problem_id)

            # 3. Separate current week vs historical weeks
            current_week_count = len(weekly_solves[0])
            historical_counts = [len(weekly_solves[w]) for w in range(1, weeks_history + 1)]

            # 4. Apply our mathematical curve
            is_slacking, mu, sigma, z_score = self._calculate_slacker_metrics(
                history_counts=historical_counts, 
                current_count=current_week_count,
                z_threshold=z_threshold,
                grace_minimum=grace_minimum  # Now uses the command parameter!
            )

            if is_slacking:
                slackers_found.append({
                    'handle': handle,
                    'current': current_week_count,
                    'mu': mu,
                    'sigma': sigma,
                    'z_score': z_score
                })

        # 5. Format the output in a nice Discord Embed
        embed = discord.Embed(
            title="📉 Slacker Report (Z-Score Analysis)", 
            description=f"Based on personal performance curves over the last `{weeks_history} weeks`.\n"
                        f"*Threshold: Z-Score ≤ `{z_threshold}`.* \n"
                        f"*Grace minimum: `{grace_minimum}` problems.*",
            color=discord.Color.red()
        )

        if not slackers_found:
            embed.description += "\n\n**Amazing! Nobody is mathematically slacking right now!** 🏆"
        else:
            # Sort slackers by worst Z-score (the biggest dropoff from their usual performance)
            slackers_found.sort(key=lambda x: x['z_score'])

            for s in slackers_found:
                handle_str = f"**{s['handle']}**"
                stats_str = (f"Solved this week: **{s['current']}**\n"
                             f"Their Average: **{s['mu']:.1f}** *(±{s['sigma']:.1f})*\n"
                             f"Z-Score: `{s['z_score']:.2f}`")
                
                embed.add_field(name=handle_str, value=stats_str, inline=False)

        await calculating_msg.delete()
        await ctx.send(embed=embed)

# Updated to use async def setup as required by newer discord.py versions
async def setup(bot):
    await bot.add_cog(Slacker(bot))
