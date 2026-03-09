import random
import datetime
import discord
from discord.ext import commands

from tle import constants
from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

def _calculateFairScoreForDelta(delta):
    """Calculates fair points based on the delta of the solved problem."""
    distrib = (1, 2, 3, 5, 8, 12, 17, 23)
    if delta is None: return 0
    if delta <= -400: return distrib[0]
    if delta >= 300: return distrib[-1]
    return distrib[(delta - -400) // 100]

class Fair(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_fair_leaderboard(self, guild_id, start_time, end_time):
        """Helper to calculate scores for a fair leaderboard based on active gitguds."""
        res = cf_common.user_db.get_cf_users_for_guild(guild_id)
        if not res:
            return []
            
        user_scores = []
        for user_id, cf_user in res:
            data = cf_common.user_db.gitlog(user_id)
            if not data:
                continue
                
            score = 0
            for entry in data:
                # gitlog typically: issue, finish, name, contest, index, delta, status
                finish = entry[1]
                delta = entry[5]
                
                # Count points for challenges completed in the exact timeframe.
                if finish and start_time <= finish < end_time:
                    score += _calculateFairScoreForDelta(delta)
                    
            if score > 0:
                user_scores.append((score, user_id, cf_user.handle, cf_user.rating))
                
        # Sort by highest score first
        user_scores.sort(key=lambda x: x[0], reverse=True)
        return user_scores

    def _build_fair_embed(self, ctx, title, user_scores):
        """Helper to build a clean embed for the fair leaderboards."""
        if not user_scores:
            embed = discord.Embed(
                title=title,
                description="No one has earned any fair points in this timeframe yet! Get to grinding! 💻",
                color=discord.Color.light_grey()
            )
            return embed
            
        desc = ""
        medals = ["🥇", "🥈", "🥉"]
        for i, (score, user_id, handle, rating) in enumerate(user_scores[:10]):  # Top 10 limit for embed
            member = ctx.guild.get_member(user_id)
            mention = member.mention if member else f"`{handle}`"
            rank = medals[i] if i < 3 else f"**#{i+1}**"
            desc += f"{rank} {mention} — **{score}** Points\n"
            
        embed = discord.Embed(
            title=title,
            description=desc,
            color=discord.Color.green()
        )
        return embed

    @commands.hybrid_command(description="Update user ratings and cache to ensure they are fresh", aliases=["updateratings", "refreshfair"])
    @commands.has_any_role(constants.TLE_ADMIN, constants.TLE_MODERATOR)
    async def update_fair_cache(self, ctx):
        """Fetches the latest ratings for all guild members and updates the cache/DB."""
        await ctx.send("🔄 Fetching fresh ratings from Codeforces. This might take a moment...")
        
        users = cf_common.user_db.get_cf_users_for_guild(ctx.guild.id)
        if not users:
            await ctx.send("❌ No users registered in this server.")
            return
        
        # Extract unique handles
        handles = list(set([user.handle for user_id, user in users]))
        
        try:
            fresh_users = []
            # Fetch fresh users in chunks to be safe with CF API limits
            chunk_size = 300
            for i in range(0, len(handles), chunk_size):
                chunk = handles[i:i + chunk_size]
                fresh_users.extend(await cf.user.info(handles=chunk))
            
            # Update user_db with the fresh rating data
            for user in fresh_users:
                # Depending on the TLE fork, the method might be named slightly differently
                if hasattr(cf_common.user_db, 'cache_cf_user'):
                    cf_common.user_db.cache_cf_user(user)
                elif hasattr(cf_common.user_db, 'save_cf_user'):
                    cf_common.user_db.save_cf_user(user)

            await ctx.send(f"✅ Successfully updated the cache and DB for **{len(fresh_users)}** users!")
        except Exception as e:
            await ctx.send(f"❌ Error updating cache: {e}")

    @commands.hybrid_command(description="Recommend a fair duel between active DGG/WGG/MGG participants")
    async def fair_duel(self, ctx):
        """Recommends a fair duel between active Gitgud participants."""
        guild_id = ctx.guild.id
        res = cf_common.user_db.get_cf_users_for_guild(guild_id)
        if not res:
            await ctx.send("❌ No registered users found in this server.")
            return

        active_users = []
        now = datetime.datetime.now().timestamp()
        
        # MGG / WGG / DGG activity check: Anyone who completed a gitgud in the last 30 days
        thirty_days_ago = now - (30 * 24 * 60 * 60)

        for user_id, cf_user in res:
            data = cf_common.user_db.gitlog(user_id)
            if not data:
                continue
            
            # Check for recent gitgud activity
            has_recent = False
            for entry in data:
                # gitlog structure is typically: issue, finish, name, contest, index, delta, status
                finish = entry[1]
                if finish and finish >= thirty_days_ago:
                    has_recent = True
                    break
            
            if has_recent and cf_user.rating is not None:
                active_users.append((user_id, cf_user))

        if len(active_users) < 2:
            await ctx.send("❌ Not enough active participants in the recent gitgud challenges to recommend a duel.")
            return

        # Sort active users by rating to easily find fair matches
        active_users.sort(key=lambda x: x[1].rating)
        
        fair_pairs = []
        best_pair = None
        min_diff = float('inf')

        # We consider a duel "fair" if the rating difference is <= 100
        for i in range(len(active_users)):
            for j in range(i + 1, len(active_users)):
                diff = abs(active_users[i][1].rating - active_users[j][1].rating)
                if diff <= 100:
                    fair_pairs.append((active_users[i], active_users[j], diff))
                
                # Keep track of the absolute closest pair as a fallback
                if diff < min_diff:
                    min_diff = diff
                    best_pair = (active_users[i], active_users[j], diff)

        if fair_pairs:
            # Pick a random fair pair to keep recommendations varied over time
            chosen_pair = random.choice(fair_pairs)
        else:
            # Fallback to the absolute closest pair if no one is within 100 points
            chosen_pair = best_pair

        user1, user2, diff = chosen_pair
        
        member1 = ctx.guild.get_member(user1[0])
        member2 = ctx.guild.get_member(user2[0])
        
        mention1 = member1.mention if member1 else f"`{user1[1].handle}`"
        mention2 = member2.mention if member2 else f"`{user2[1].handle}`"

        embed = discord.Embed(
            title="⚔️ Fair Duel Recommendation ⚔️",
            description=f"Based on recent active participation in the Gitgudders (DGG/WGG/MGG), we recommend a duel between:\n\n"
                        f"🔴 {mention1} (Rating: **{user1[1].rating}**)\n"
                        f"🔵 {mention2} (Rating: **{user2[1].rating}**)\n\n"
                        f"**Rating Difference:** {diff} points",
            color=discord.Color.dark_teal()
        )
        embed.set_footer(text=f"Pro-tip: Type ';duel challenge {user2[1].handle}' to start the duel!")
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="View the Daily Fair Leaderboard", aliases=["dfair", "dsp"])
    async def dailyfair(self, ctx):
        """Displays the Daily Fair leaderboard (top points earned today)."""
        now = datetime.datetime.now()
        start_time_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time_dt = start_time_dt + datetime.timedelta(days=1)
        
        user_scores = self._get_fair_leaderboard(ctx.guild.id, start_time_dt.timestamp(), end_time_dt.timestamp())
        embed = self._build_fair_embed(ctx, f"🗓️ Daily Fair Leaderboard - {start_time_dt.strftime('%b %d')}", user_scores)
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="View the Weekly Fair Leaderboard", aliases=["wfair", "wsp"])
    async def weeklyfair(self, ctx):
        """Displays the Weekly Fair leaderboard (top points earned this week)."""
        now = datetime.datetime.now()
        start_of_week = now - datetime.timedelta(days=now.weekday())
        start_time_dt = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time_dt = start_time_dt + datetime.timedelta(days=7)
        
        user_scores = self._get_fair_leaderboard(ctx.guild.id, start_time_dt.timestamp(), end_time_dt.timestamp())
        embed = self._build_fair_embed(ctx, f"🗓️ Weekly Fair Leaderboard (Week {start_time_dt.isocalendar()[1]})", user_scores)
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="View the Monthly Fair Leaderboard", aliases=["mfair", "msp"])
    async def monthlyfair(self, ctx):
        """Displays the Monthly Fair leaderboard (top points earned this month)."""
        now = datetime.datetime.now()
        start_time_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Find start of next month
        if start_time_dt.month == 12:
            end_time_dt = start_time_dt.replace(year=start_time_dt.year + 1, month=1)
        else:
            end_time_dt = start_time_dt.replace(month=start_time_dt.month + 1)
            
        user_scores = self._get_fair_leaderboard(ctx.guild.id, start_time_dt.timestamp(), end_time_dt.timestamp())
        embed = self._build_fair_embed(ctx, f"🗓️ Monthly Fair Leaderboard - {start_time_dt.strftime('%B %Y')}", user_scores)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Fair(bot))
