import datetime
import os
import io
import html
import cairo
import gi
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo

import discord
from discord.ext import commands, tasks

from tle import constants
from tle.util import codeforces_common as cf_common

# Using the exact score configurations from the Codeforces cog
_GITGUD_SCORE_DISTRIB = (1, 2, 3, 5, 8, 12, 17, 23)
_GITGUD_SCORE_DISTRIB_MIN = -400
_GITGUD_SCORE_DISTRIB_MAX =  300
_ONE_WEEK_DURATION = 7 * 24 * 60 * 60
_GITGUD_MORE_POINTS_START_TIME = 1680300000

_DIVISION_RATING_LOW  = (2100, 1600, -1000)
_DIVISION_RATING_HIGH = (9999, 2099,  1599)

FONTS = [
    'Noto Sans',
    'Noto Sans CJK JP',
    'Noto Sans CJK SC',
    'Noto Sans CJK TC',
    'Noto Sans CJK HK',
    'Noto Sans CJK KR',
]

def rating_to_color(rating):
    """returns (r, g, b) pixels values corresponding to rating"""
    BLACK = (10, 10, 10)
    RED = (255, 20, 20)
    BLUE = (0, 0, 200)
    GREEN = (0, 140, 0)
    ORANGE = (250, 140, 30)
    PURPLE = (160, 0, 120)
    CYAN = (0, 165, 170)
    GREY = (70, 70, 70)
    if rating is None or rating == 'N/A':
        return BLACK
    if rating < 1200:
        return GREY
    if rating < 1400:
        return GREEN
    if rating < 1600:
        return CYAN
    if rating < 1900:
        return BLUE
    if rating < 2100:
        return PURPLE
    if rating < 2400:
        return ORANGE
    return RED

def get_gudgitters_image(rankings):
    """return PIL image for rankings"""
    SMOKE_WHITE = (250, 250, 250)
    BLACK = (0, 0, 0)
    DISCORD_GRAY = (.212, .244, .247)
    ROW_COLORS = ((0.95, 0.95, 0.95), (0.9, 0.9, 0.9))

    WIDTH = 900
    BORDER_MARGIN = 20
    COLUMN_MARGIN = 10
    HEADER_SPACING = 1.25
    WIDTH_RANK = 0.08*WIDTH
    WIDTH_NAME = 0.38*WIDTH
    LINE_HEIGHT = 40
    HEIGHT = int((len(rankings) + HEADER_SPACING) * LINE_HEIGHT + 2*BORDER_MARGIN)
    
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
    context = cairo.Context(surface)
    context.set_line_width(1)
    context.set_source_rgb(*DISCORD_GRAY)
    context.rectangle(0, 0, WIDTH, HEIGHT)
    context.fill()
    layout = PangoCairo.create_layout(context)
    layout.set_font_description(Pango.font_description_from_string(','.join(FONTS) + ' 20'))
    layout.set_ellipsize(Pango.EllipsizeMode.END)

    def draw_bg(y, color_index):
        nxty = y + LINE_HEIGHT
        context.move_to(BORDER_MARGIN, y)
        context.line_to(WIDTH, y)
        context.line_to(WIDTH, nxty)
        context.line_to(0, nxty)
        context.set_source_rgb(*ROW_COLORS[color_index])
        context.fill()

    def draw_row(pos, username, handle, rating, color, y, bold=False):
        context.set_source_rgb(*[x/255.0 for x in color])
        context.move_to(BORDER_MARGIN, y)

        def draw(text, width=-1):
            text = html.escape(text)
            if bold:
                text = f'<b>{text}</b>'
            layout.set_width((width - COLUMN_MARGIN)*1000)
            layout.set_markup(text, -1)
            PangoCairo.show_layout(context, layout)
            context.rel_move_to(width, 0)

        draw(pos, WIDTH_RANK)
        draw(username, WIDTH_NAME)
        draw(handle, WIDTH_NAME)
        draw(rating)

    y = BORDER_MARGIN
    draw_row('#', 'Name', 'Handle', 'Points', SMOKE_WHITE, y, bold=True)
    y += LINE_HEIGHT*HEADER_SPACING

    for i, (pos, name, handle, rating, score) in enumerate(rankings):
        color = rating_to_color(rating)
        draw_bg(y, i%2)
        draw_row(str(pos+1), f'{name}', f'{handle} ({rating if rating else "N/A"})' , str(score), color, y)
        if rating and rating >= 3000:
            draw_row('', name[0], handle[0], '', BLACK, y)
        y += LINE_HEIGHT

    image_data = io.BytesIO()
    surface.write_to_png(image_data)
    image_data.seek(0)
    discord_file = discord.File(image_data, filename='mgg_leaderboard.png')
    return discord_file

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

class MonthlyGitgudders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.monthly_announcement_task.start()

    def cog_unload(self):
        self.monthly_announcement_task.cancel()

    def _get_announcement_channel(self, guild):
        """Fetches the exact channel TLE uses for Rating Changes (logging channel)."""
        channel_id = None
        if hasattr(cf_common.user_db, 'get_logging_channel'):
            channel_id = cf_common.user_db.get_logging_channel(guild.id)
        elif hasattr(cf_common.user_db, 'get_cf_logging_channel'):
            channel_id = cf_common.user_db.get_cf_logging_channel(guild.id)
            
        if not channel_id:
            channel_ids_str = os.environ.get("CHANNEL_IDS", os.environ.get("CHANNEL_ID"))
            if channel_ids_str:
                for cid in channel_ids_str.split(","):
                    if cid.strip().isdigit() and guild.get_channel(int(cid.strip())):
                        return int(cid.strip())
        return channel_id

    def get_monthly_scores(self, guild_id, start_time, end_time):
        res = cf_common.user_db.get_cf_users_for_guild(guild_id)
        if not res:
            return []
            
        user_scores = []
        for user_id, cf_user in res:
            data = cf_common.user_db.gitlog(user_id)
            if not data: continue
                
            score = 0
            for entry in data:
                issue, finish, name, contest, index, delta, status = entry
                if finish and start_time <= finish < end_time:
                    pts = _calculateGitgudScoreForDelta(delta)
                    
                    finish_dt = datetime.datetime.fromtimestamp(finish)
                    month_start, month_end = cf_common.get_start_and_end_of_month(finish_dt)
                    
                    if _check_more_points_active(finish, month_start, month_end): 
                        pts *= 2
                    score += pts
                    
            if score > 0: user_scores.append((score, user_id, cf_user.handle, cf_user.rating))
                
        user_scores.sort(key=lambda x: x[0], reverse=True)
        return user_scores

    async def _do_announcement(self, channel, ref_time: datetime.datetime) -> bool:
        start_time_dt = ref_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if start_time_dt.month == 12:
            end_time_dt = start_time_dt.replace(year=start_time_dt.year + 1, month=1)
        else:
            end_time_dt = start_time_dt.replace(month=start_time_dt.month + 1)
        
        start_time = start_time_dt.timestamp()
        end_time = end_time_dt.timestamp()
        
        month_name = start_time_dt.strftime('%B %Y')
        
        user_scores = self.get_monthly_scores(channel.guild.id, start_time, end_time)
        
        if not user_scores:
            embed = discord.Embed(
                title=f"🗓️ Monthly Gitgudders Wrap-Up - {month_name} 🗓️",
                description="No one earned any points this month! The leaderboard is wide open! 💻",
                color=discord.Color.light_grey()
            )
            await channel.send(embed=embed)
            return True
            
        top_3 = user_scores[:3]
        medals = ["🥇", "🥈", "🥉"]
        desc = f"🔥 **The grind never stops! Here are the top performers for {month_name}:** 🔥\n\n"
        
        for i, (score, user_id, handle, rating) in enumerate(top_3):
            member = channel.guild.get_member(user_id)
            mention = member.mention if member else f"`{handle}`"
            desc += f"{medals[i]} {mention} — **{score}** points\n"
            
        desc += "\n*Points have been reset. A new monthly grind begins!*"
        
        embed = discord.Embed(title="🗓️ Monthly Gitgudders Wrap-Up 🗓️", description=desc, color=discord.Color.blue())
        await channel.send(embed=embed)
        return True

    @tasks.loop(time=datetime.time(hour=0, minute=0, second=0))
    async def monthly_announcement_task(self):
        """Runs every day at 00:00 UTC+3. On the 1st, announces the previous month."""
        now = datetime.datetime.now(datetime.timezone.utc)
        
        if now.day == 1:
            for guild in self.bot.guilds:
                channel_id = self._get_announcement_channel(guild)
                if not channel_id: continue
                
                channel = guild.get_channel(channel_id)
                if not channel: continue

                # Subtract 1 day to ensure we calculate the month that just ended
                ref_time = now - datetime.timedelta(days=1)
                await self._do_announcement(channel, ref_time)

    @monthly_announcement_task.before_loop
    async def before_monthly_announcement(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(description="View the Monthly Gitgudders leaderboard", aliases=["monthlygitgudders", "monthlygg"], usage="[div1|div2|div3] [+all]")
    async def mgg(self, ctx, *args):
        division = None
        showall = False
        
        for arg in args:
            if arg[0:3] == 'div':
                try:
                    division = int(arg[3])
                    if division < 1 or division > 3: return await ctx.send('Division number must be within range [1-3]')
                except ValueError: return await ctx.send(f'{arg} is an invalid div argument')
            if arg == "+all": showall = True
                
        now = datetime.datetime.now()
        start_time_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if start_time_dt.month == 12:
            end_time_dt = start_time_dt.replace(year=start_time_dt.year + 1, month=1)
        else:
            end_time_dt = start_time_dt.replace(month=start_time_dt.month + 1)
        
        user_scores = self.get_monthly_scores(ctx.guild.id, start_time_dt.timestamp(), end_time_dt.timestamp())
        
        rankings = []
        index = 0
        for score, user_id, handle, rating in user_scores:
            member = ctx.guild.get_member(user_id)
            if not showall and member is None: continue
            discord_handle = member.display_name if member else ""
            if division is not None:
                if rating is None or rating < _DIVISION_RATING_LOW[division-1] or rating > _DIVISION_RATING_HIGH[division-1]: continue
                    
            rankings.append((index, discord_handle, handle, rating, score))
            index += 1
            if index == 20: break
        
        if not rankings: return await ctx.send("No one has earned any points this month yet! Get to coding! 💻")

        discord_file = get_gudgitters_image(rankings)
        await ctx.send(file=discord_file)

    @commands.hybrid_command(hidden=True)
    @commands.has_any_role(constants.TLE_ADMIN, constants.TLE_MODERATOR)
    async def force_announce_mgg(self, ctx):
        channel_id = self._get_announcement_channel(ctx.guild)
        if not channel_id: return await ctx.send("No announcement/logging channel configured for this server. Use `;logging set`.")
            
        channel = ctx.guild.get_channel(channel_id)
        if not channel: return await ctx.send("Configured logging channel not found.")

        if await self._do_announcement(channel, datetime.datetime.now()):
            await ctx.message.add_reaction("✅")

async def setup(bot):
    for cmd in ['mgg', 'monthlygg', 'monthlygitgudders', 'gitgudders']: bot.remove_command(cmd)
    if bot.get_cog('MonthlyGitgudders'): await bot.remove_cog('MonthlyGitgudders')
    await bot.add_cog(MonthlyGitgudders(bot))
