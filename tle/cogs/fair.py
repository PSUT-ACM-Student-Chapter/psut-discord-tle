import discord
from discord.ext import commands
import time
import logging
import asyncio
import io
import html
import cairo
import gi
from datetime import datetime, timedelta

gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo

# Directly import codeforces_common and codeforces_api from tle.util
from tle.util import codeforces_common as cf_common
from tle.util import codeforces_api as cf

logger = logging.getLogger(__name__)

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

def get_fair_leaderboard_image(rankings):
    """return PNG byte array for rankings"""
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
    
    # Cairo+Pango setup
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
            layout.set_width((width - COLUMN_MARGIN)*1000) # pixel = 1000 pango units
            layout.set_markup(text, -1)
            PangoCairo.show_layout(context, layout)
            context.rel_move_to(width, 0)

        draw(pos, WIDTH_RANK)
        draw(username, WIDTH_NAME)
        draw(handle, WIDTH_NAME)
        draw(rating)

    y = BORDER_MARGIN

    # draw header
    draw_row('#', 'Name', 'Handle', 'Points', SMOKE_WHITE, y, bold=True)
    y += LINE_HEIGHT*HEADER_SPACING

    for i, (pos, name, handle, rating, score) in enumerate(rankings):
        color = rating_to_color(rating)
        draw_bg(y, i%2)
        draw_row(str(pos+1), f'{name}', f'{handle} ({rating if rating else "N/A"})' , str(score), color, y)
        if rating and rating >= 3000:  # nutella
            draw_row('', name[0], handle[0], '', BLACK, y)
        y += LINE_HEIGHT

    image_data = io.BytesIO()
    surface.write_to_png(image_data)
    return image_data.getvalue()

class FairLeaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Cache to store leaderboards: (guild_id, days) -> (timestamp, embed_dict, image_bytes)
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
            cache_time, cached_embed_dict, cached_image_bytes = self.leaderboard_cache[cache_key]
            if time.time() - cache_time < self.CACHE_DURATION:
                embed = discord.Embed.from_dict(cached_embed_dict)
                discord_file = discord.File(io.BytesIO(cached_image_bytes), filename='fair_leaderboard.png') if cached_image_bytes else None
                return embed, discord_file

        # Sanity check: Ensure the database is actually loaded before proceeding
        if getattr(cf_common, 'user_db', None) is None:
            embed = discord.Embed(
                title=title, 
                description="⏳ The Codeforces database is still initializing. Please try again in a moment!", 
                color=discord.Color.orange()
            )
            return embed, None

        # ------------------------------------------------------------------
        # INTEGRATION POINT: Fetching users and submissions.
        # This uses concurrent API fetching for maximum speed.
        # ------------------------------------------------------------------
        try:
            # 1. Get all handles linked in this Discord server
            handles = cf_common.user_db.get_handles_for_guild(ctx.guild.id)
            if not handles:
                embed = discord.Embed(title=title, description="No handles registered in this server.", color=discord.Color.red())
                return embed, None
            
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
            for user_id, handle in handles:
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
                        'user_id': user_id,
                        'handle': handle,
                        'rating': rating,
                        'solved_count': len(solved_problems),
                        'points': total_points
                    })
                    
        except Exception as e:
            logger.exception("Error generating fair leaderboard")
            embed = discord.Embed(
                title="Error Generating Leaderboard", 
                description=f"An error occurred accessing the API: `{e}`\nPlease check your server console for the traceback.", 
                color=discord.Color.red()
            )
            return embed, None

        # ------------------------------------------------------------------
        # Formatting the Output
        # ------------------------------------------------------------------
        leaderboard.sort(key=lambda x: x['points'], reverse=True)
        
        if not leaderboard:
            embed = discord.Embed(title=title, description="No one has solved any problems in this time period. Time to get to work!", color=discord.Color.gold())
            # Save to cache with None for image_bytes
            self.leaderboard_cache[cache_key] = (time.time(), embed.to_dict(), None)
            return embed, None

        rankings = []
        for i, entry in enumerate(leaderboard[:20]):
            member = ctx.guild.get_member(entry['user_id'])
            discord_handle = member.display_name if member else ""
            # Format the score string to include the number of problems solved
            score_str = f"{entry['points']:.2f} pts ({entry['solved_count']} solved)"
            rankings.append((i, discord_handle, entry['handle'], entry['rating'], score_str))
            
        image_bytes = get_fair_leaderboard_image(rankings)
        discord_file = discord.File(io.BytesIO(image_bytes), filename='fair_leaderboard.png')
            
        embed = discord.Embed(title=title, color=discord.Color.gold())
        embed.set_image(url="attachment://fair_leaderboard.png")
        embed.set_footer(text=f"Points reward solving harder problems based on rating! (Updates every 30m)")
        
        # Save to cache
        self.leaderboard_cache[cache_key] = (time.time(), embed.to_dict(), image_bytes)
        
        return embed, discord_file

    @commands.command(name='weekly_solve', aliases=['fwgg', 'wsp'])
    async def weekly_solve(self, ctx):
        """Shows the number of questions solved this week with a fair point system."""
        async with ctx.typing():
            embed, discord_file = await self._generate_leaderboard(ctx, days=7, title="🏆 Weekly Fair Leaderboard")
            if discord_file:
                await ctx.send(embed=embed, file=discord_file)
            else:
                await ctx.send(embed=embed)

    @commands.command(name='monthly_solve', aliases=['fmgg', 'msp'])
    async def monthly_solve(self, ctx):
        """Shows the number of questions solved this month with a fair point system."""
        async with ctx.typing():
            embed, discord_file = await self._generate_leaderboard(ctx, days=30, title="🏆 Monthly Fair Leaderboard")
            if discord_file:
                await ctx.send(embed=embed, file=discord_file)
            else:
                await ctx.send(embed=embed)

# This setup function is required for discord.ext.commands to load the Cog
async def setup(bot):
    await bot.add_cog(FairLeaderboard(bot))
