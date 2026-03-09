import random
import datetime
import discord
from discord.ext import commands
import io
import html
import cairo
import gi
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo

from tle import constants
from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

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
    draw_row('#', 'Name', 'Handle', 'Solved / Points', SMOKE_WHITE, y, bold=True)
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
            solved_count = 0
            for entry in data:
                # gitlog typically: issue, finish, name, contest, index, delta, status
                finish = entry[1]
                delta = entry[5]
                
                # Count points for challenges completed in the exact timeframe.
                if finish and start_time <= finish < end_time:
                    score += _calculateFairScoreForDelta(delta)
                    solved_count += 1
                    
            if score > 0 or solved_count > 0:
                user_scores.append((score, solved_count, user_id, cf_user.handle, cf_user.rating))
                
        # Sort by highest score first
        user_scores.sort(key=lambda x: x[0], reverse=True)
        return user_scores

    async def _send_fair_leaderboard(self, ctx, title, user_scores):
        """Helper to build and send the fair leaderboards image."""
        if not user_scores:
            embed = discord.Embed(
                title=title,
                description="No one has earned any fair points in this timeframe yet! Get to grinding! 💻",
                color=discord.Color.light_grey()
            )
            await ctx.send(embed=embed)
            return
            
        rankings = []
        for i, (score, solved_count, user_id, handle, rating) in enumerate(user_scores[:20]):
            member = ctx.guild.get_member(user_id)
            discord_handle = member.display_name if member else ""
            
            # Format the score string as "Solved / Points"
            if isinstance(score, float):
                score_str = f"{solved_count} / {score:.2f}"
            else:
                score_str = f"{solved_count} / {score}"
                
            rankings.append((i, discord_handle, handle, rating, score_str))
            
        image_bytes = get_fair_leaderboard_image(rankings)
        discord_file = discord.File(io.BytesIO(image_bytes), filename='fair_leaderboard.png')
        
        embed = discord.Embed(title=title, color=discord.Color.gold())
        embed.set_image(url="attachment://fair_leaderboard.png")
        await ctx.send(embed=embed, file=discord_file)

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
        await self._send_fair_leaderboard(ctx, f"🗓️ Daily Fair Leaderboard - {start_time_dt.strftime('%b %d')}", user_scores)

    @commands.hybrid_command(description="View the Weekly Fair Leaderboard", aliases=["wfair", "wsp"])
    async def weeklyfair(self, ctx):
        """Displays the Weekly Fair leaderboard (top points earned this week)."""
        now = datetime.datetime.now()
        start_of_week = now - datetime.timedelta(days=now.weekday())
        start_time_dt = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time_dt = start_time_dt + datetime.timedelta(days=7)
        
        user_scores = self._get_fair_leaderboard(ctx.guild.id, start_time_dt.timestamp(), end_time_dt.timestamp())
        await self._send_fair_leaderboard(ctx, f"🏆 Weekly Fair Leaderboard (Week {start_time_dt.isocalendar()[1]})", user_scores)

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
        await self._send_fair_leaderboard(ctx, f"🏆 Monthly Fair Leaderboard - {start_time_dt.strftime('%B %Y')}", user_scores)

async def setup(bot):
    await bot.add_cog(Fair(bot))
