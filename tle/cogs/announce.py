import datetime
import os
import discord
from discord.ext import commands

from tle import constants
from tle.util import codeforces_common as cf_common

# Using the exact score configurations from the Codeforces cog
_GITGUD_SCORE_DISTRIB = (1, 2, 3, 5, 8, 12, 17, 23)
_GITGUD_SCORE_DISTRIB_MIN = -400
_GITGUD_SCORE_DISTRIB_MAX =  300
_ONE_WEEK_DURATION = 7 * 24 * 60 * 60
_GITGUD_MORE_POINTS_START_TIME = 1680300000

def _calculateGitgudScoreForDelta(delta):
    if (delta <= _GITGUD_SCORE_DISTRIB_MIN):
        return _GITGUD_SCORE_DISTRIB[0]
    if (delta >= _GITGUD_SCORE_DISTRIB_MAX):
        return _GITGUD_SCORE_DISTRIB[-1]
    index = (delta - _GITGUD_SCORE_DISTRIB_MIN)//100
    return _GITGUD_SCORE_DISTRIB[index]

def _check_more_points_active(now_time, start_time, end_time):
    morePointsActive = False
    morePointsTime = end_time - _ONE_WEEK_DURATION
    if start_time >= _GITGUD_MORE_POINTS_START_TIME and now_time >= morePointsTime: 
        morePointsActive = True
    return morePointsActive

class Announcer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def announce_winners(self, start_time, end_time, month_name):
        """Calculates the scores for the given timeframe and posts the Top 3."""
        # Support either CHANNEL_IDS or CHANNEL_ID for backward compatibility
        channel_ids_str = os.environ.get("CHANNEL_IDS", os.environ.get("CHANNEL_ID"))
        if not channel_ids_str:
            return
            
        # Split the string by commas and strip any spaces
        channel_ids = [cid.strip() for cid in channel_ids_str.split(",") if cid.strip().isdigit()]
        
        for cid in channel_ids:
            channel = self.bot.get_channel(int(cid))
            if not channel:
                continue
                
            guild = channel.guild
            res = cf_common.user_db.get_cf_users_for_guild(guild.id)
            if not res:
                continue
                
            user_scores = []
            
            # Iterate over all registered Codeforces users in this server
            for user_id, cf_user in res:
                data = cf_common.user_db.gitlog(user_id)
                if not data:
                    continue
                    
                score = 0
                for entry in data:
                    issue, finish, name, contest, index, delta, status = entry
                    
                    # Check if the problem was finished within the target month
                    if finish and start_time <= finish < end_time:
                        pts = _calculateGitgudScoreForDelta(delta)
                        if _check_more_points_active(finish, start_time, end_time):
                            pts *= 2
                        score += pts
                        
                if score > 0:
                    user_scores.append((score, user_id, cf_user.handle))
                    
            if not user_scores:
                # Nobody scored points last month
                embed = discord.Embed(
                    title=f"Monthly Gitgudders - {month_name}",
                    description="No one earned any points! Time to get coding! 💻",
                    color=discord.Color.light_grey()
                )
                await channel.send(embed=embed)
                continue
                
            # Sort by score descending
            user_scores.sort(key=lambda x: x[0], reverse=True)
            top_3 = user_scores[:3]
            
            medals = ["🥇", "🥈", "🥉"]
            desc = f"🏆 **The results for {month_name} are in!** 🏆\n\nHere are your Top 3 Gitgudders:\n\n"
            
            for i, (score, user_id, handle) in enumerate(top_3):
                member = guild.get_member(user_id)
                mention = member.mention if member else f"`{handle}`"
                desc += f"{medals[i]} {mention} — **{score}** points\n"
                
            desc += "\n*Keep up the great work!*"
            
            embed = discord.Embed(
                title="🌟 Monthly Gitgudders Winners 🌟", 
                description=desc, 
                color=discord.Color.gold()
            )
            
            await channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Announcer(bot))
