import datetime
import os
import discord
from discord.ext import commands

from tle import constants
from tle.util import codeforces_common as cf_common
from tle.util import table

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

class WeeklyGitgudders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_weekly_scores(self, guild_id, start_time, end_time):
        """Helper function to calculate scores for all users in a given week timeframe."""
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
                issue, finish, name, contest, index, delta, status = entry
                
                # Check if the problem was finished within the target week
                if finish and start_time <= finish < end_time:
                    pts = _calculateGitgudScoreForDelta(delta)
                    
                    # Double points check requires the MONTH boundaries of when it was solved
                    finish_dt = datetime.datetime.fromtimestamp(finish)
                    month_start, month_end = cf_common.get_start_and_end_of_month(finish_dt)
                    
                    if _check_more_points_active(finish, month_start, month_end):
                        pts *= 2
                    score += pts
                    
            if score > 0:
                user_scores.append((score, user_id, cf_user.handle))
                
        user_scores.sort(key=lambda x: x[0], reverse=True)
        return user_scores

    @commands.command(brief="View the Weekly Gitgudders leaderboard", aliases=["weeklygitgudders"])
    async def wgg(self, ctx):
        """Displays the Gitgudders leaderboard for the current week (Monday to Sunday)."""
        now = datetime.datetime.now()
        
        # Calculate start and end of the current week
        start_of_week = now - datetime.timedelta(days=now.weekday())
        start_time_dt = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time_dt = start_time_dt + datetime.timedelta(days=7)
        
        start_time = start_time_dt.timestamp()
        end_time = end_time_dt.timestamp()
        
        user_scores = self.get_weekly_scores(ctx.guild.id, start_time, end_time)
        
        if not user_scores:
            await ctx.send("No one has earned any points this week yet! Get to coding! 💻")
            return

        # Format the output as a clean table (matching the mgg style)
        _style = table.Style('{:>}  {:<}  {:>}')
        t = table.Table(_style)
        t += table.Header('#', 'Handle', 'Points')
        t += table.Line()
        
        for i, (score, user_id, handle) in enumerate(user_scores):
            t += table.Data(f"{i+1}", handle, str(score))
            
        week_num = start_time_dt.isocalendar()[1]
        end_of_week_display = end_time_dt - datetime.timedelta(days=1)
        title = f"Weekly Gitgudders - Week {week_num} ({start_time_dt.strftime('%b %d')} - {end_of_week_display.strftime('%b %d')})"
        
        # Send the table inside a discord code block
        msg = f"**{title}**\n```\n{t}\n```"
        await ctx.send(msg)

    @commands.command(hidden=True)
    @commands.has_any_role(constants.TLE_ADMIN, constants.TLE_MODERATOR)
    async def force_announce_wgg(self, ctx):
        """Admin command to manually trigger the Top 3 announcement for the CURRENT week."""
        now = datetime.datetime.now()
        
        start_of_week = now - datetime.timedelta(days=now.weekday())
        start_time_dt = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time_dt = start_time_dt + datetime.timedelta(days=7)
        
        start_time = start_time_dt.timestamp()
        end_time = end_time_dt.timestamp()
        
        week_num = start_time_dt.isocalendar()[1]
        end_of_week_display = end_time_dt - datetime.timedelta(days=1)
        week_name = f"Week {week_num} ({start_time_dt.strftime('%b %d')} - {end_of_week_display.strftime('%b %d')})"
        
        # Support either CHANNEL_IDS or CHANNEL_ID for backward compatibility
        channel_ids_str = os.environ.get("CHANNEL_IDS", os.environ.get("CHANNEL_ID"))
        if not channel_ids_str:
            return await ctx.send("No CHANNEL_IDS environment variable found.")
            
        channel_ids = [cid.strip() for cid in channel_ids_str.split(",") if cid.strip().isdigit()]
        
        announced = False
        for cid in channel_ids:
            channel = self.bot.get_channel(int(cid))
            if not channel:
                continue
                
            user_scores = self.get_weekly_scores(channel.guild.id, start_time, end_time)
            
            if not user_scores:
                embed = discord.Embed(
                    title=f"🗓️ Weekly Gitgudders Wrap-Up - {week_name} 🗓️",
                    description="No one earned any points this week! The leaderboard is wide open! 💻",
                    color=discord.Color.light_grey()
                )
                await channel.send(embed=embed)
                announced = True
                continue
                
            top_3 = user_scores[:3]
            medals = ["🥇", "🥈", "🥉"]
            desc = f"🔥 **The grind never stops! Here are the top performers for {week_name}:** 🔥\n\n"
            
            for i, (score, user_id, handle) in enumerate(top_3):
                member = channel.guild.get_member(user_id)
                mention = member.mention if member else f"`{handle}`"
                desc += f"{medals[i]} {mention} — **{score}** points\n"
                
            desc += "\n*Points will reset on Monday. Keep up the great work!*"
            
            embed = discord.Embed(
                title="🗓️ Weekly Gitgudders Wrap-Up 🗓️", 
                description=desc, 
                color=discord.Color.blue()  # Using Blue for weekly to differentiate from the Gold monthly
            )
            
            await channel.send(embed=embed)
            announced = True

        if announced:
            await ctx.message.add_reaction("✅")
        else:
            await ctx.send("Could not find the configured channels to announce in.")

async def setup(bot):
    await bot.add_cog(WeeklyGitgudders(bot))
