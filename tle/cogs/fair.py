import discord
from discord.ext import commands
import time
import logging
import asyncio
from datetime import datetime, timedelta

# Directly import codeforces_common and codeforces_api from tle.util
from tle.util import codeforces_common as cf_common
from tle.util import codeforces_api as cf

logger = logging.getLogger(__name__)

class FairLeaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Cache to store leaderboards: (guild_id, days) -> (timestamp, embed)
        self.leaderboard_cache = {}
        # Cache duration in seconds (30 minutes)
        self.CACHE_DURATION = 1800 

    def calculate_points(self, user_rating: int, problem_rating: int) -> float:
        """
        Calculates fair points based on the Elo expected probability curve.
        """
        # Default unrated users and unrated problems to 800 rating
        u_rating = max(800, user_rating or 800)
        p_rating = problem_rating or 800
        
        # Base points: 1 point per 100 rating
        base_points = p_rating / 100.0
        
        # Exponential multiplier: Doubles for every 400 rating difference
        multiplier = 2.0 ** ((p_rating - u_rating) / 400.0)
        
        return round(base_points * multiplier, 2)

    async def _generate_leaderboard(self, ctx, days: int, title: str):
        now = datetime.utcnow()
        start_time = now - timedelta(days=days)
        start_timestamp = start_time.timestamp()

        # Check cache first to respond instantly if recently requested
        cache_key = (ctx.guild.id, days)
        if cache_key in self.leaderboard_cache:
            cache_time, cached_embed = self.leaderboard_cache[cache_key]
            if time.time() - cache_time < self.CACHE_DURATION:
                return cached_embed

        # Sanity check: Ensure the database is actually loaded before proceeding
        if getattr(cf_common, 'user_db', None) is None:
            return discord.Embed(
                title=title, 
                description="⏳ The Codeforces database is still initializing. Please try again in a moment!", 
                color=discord.Color.orange()
            )

        # ------------------------------------------------------------------
        # INTEGRATION POINT: Fetching users and submissions.
        # This uses concurrent API fetching for maximum speed.
        # ------------------------------------------------------------------
        try:
            # 1. Get all handles linked in this Discord server
            handles = cf_common.user_db.get_handles_for_guild(ctx.guild.id)
            if not handles:
                return discord.Embed(title=title, description="No handles registered in this server.", color=discord.Color.red())
            
            # Extract just the string handles from the DB tuples
            handle_strings = [handle for _, handle in handles]
            
            # 2. Fetch the Codeforces User objects directly from the API to get current ratings
            cf_users = await cf.user.info(handles=handle_strings)
            user_ratings = {u.handle: u.rating for u in cf_users}
            
            leaderboard = []
            
            # 3. Fetch all submissions CONCURRENTLY. This is massively faster than doing it one by one.
            async def get_subs(handle):
                try:
                    # TLE's wrapper automatically handles Codeforces rate limits efficiently
                    return handle, await cf.user.status(handle=handle)
                except Exception as e:
                    logger.warning(f"Failed to fetch subs for {handle}: {e}")
                    return handle, []

            # Gather all requests at once
            tasks = [get_subs(handle) for handle in handle_strings]
            results = await asyncio.gather(*tasks)
            subs_by_handle = dict(results)
            
            # 4. Iterate through each registered user and calculate scores
            for _, handle in handles:
                rating = user_ratings.get(handle, 800)
                subs = subs_by_handle.get(handle, [])
                
                if not subs:
                    continue
                
                solved_problems = set()
                total_points = 0.0
                
                for sub in subs:
                    # Filter by the time window and ensure the verdict is 'OK'
                    if sub.creationTimeSeconds >= start_timestamp and sub.verdict == 'OK':
                        # Create a unique problem identifier (e.g., '1352A')
                        prob_id = f"{sub.problem.contestId}{sub.problem.index}"
                        
                        # Only count the problem if it hasn't been solved already this period
                        if prob_id not in solved_problems:
                            solved_problems.add(prob_id)
                            
                            # Add fair points
                            pts = self.calculate_points(rating, sub.problem.rating)
                            total_points += pts
                            
                # Only add users who actually solved something to the board
                if solved_problems:
                    leaderboard.append({
                        'handle': handle,
                        'solved_count': len(solved_problems),
                        'points': total_points
                    })
                    
        except Exception as e:
            logger.exception("Error generating fair leaderboard")
            return discord.Embed(
                title="Error Generating Leaderboard", 
                description=f"An error occurred accessing the API: `{e}`\nPlease check your server console for the traceback.", 
                color=discord.Color.red()
            )

        # ------------------------------------------------------------------
        # Formatting the Output
        # ------------------------------------------------------------------
        # Sort users primarily by points (descending)
        leaderboard.sort(key=lambda x: x['points'], reverse=True)
        
        desc = ""
        # Display the Top 20 Users
        for i, entry in enumerate(leaderboard[:20], 1):
            desc += f"**{i}. {entry['handle']}**\n"
            desc += f"└ Solved: `{entry['solved_count']}` | Points: `{entry['points']:.2f}`\n\n"
            
        if not desc:
            desc = "No one has solved any problems in this time period. Time to get to work!"
            
        embed = discord.Embed(title=title, description=desc, color=discord.Color.gold())
        embed.set_footer(text=f"Points reward solving harder problems based on rating! (Updates every 30m)")
        
        # Save to cache
        self.leaderboard_cache[cache_key] = (time.time(), embed)
        
        return embed

    @commands.command(name='weekly_solve', aliases=['fwgg', 'wsp'])
    async def weekly_solve(self, ctx):
        """Shows the number of questions solved this week with a fair point system."""
        async with ctx.typing():
            embed = await self._generate_leaderboard(ctx, days=7, title="🏆 Weekly Fair Leaderboard")
            await ctx.send(embed=embed)

    @commands.command(name='monthly_solve', aliases=['fmgg', 'msp'])
    async def monthly_solve(self, ctx):
        """Shows the number of questions solved this month with a fair point system."""
        async with ctx.typing():
            embed = await self._generate_leaderboard(ctx, days=30, title="🏆 Monthly Fair Leaderboard")
            await ctx.send(embed=embed)

# This setup function is required for discord.ext.commands to load the Cog
async def setup(bot):
    await bot.add_cog(FairLeaderboard(bot))
