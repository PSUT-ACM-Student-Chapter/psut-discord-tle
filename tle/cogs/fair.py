import random
import datetime
import discord
from discord.ext import commands

from tle import constants
from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

class Fair(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

async def setup(bot):
    await bot.add_cog(Fair(bot))
