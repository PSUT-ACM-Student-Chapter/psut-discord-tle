import random
import datetime
import asyncio
import logging
import discord
from discord.ext import commands
import io
import html
import cairo
import gi
import sqlite3
import json
import time
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo

from tle import constants
from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

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

class Fair(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.CACHE_DURATION = 1800  # 30 minutes
        self.converter = commands.MemberConverter()
        
        self.db_conn = sqlite3.connect('fair_cache.db')
        # Bumped to cache_v3 to avoid OperationalError with existing days vs timeframe column schema
        self.db_conn.execute('''
            CREATE TABLE IF NOT EXISTS cache_v3 (
                guild_id INTEGER,
                timeframe TEXT,
                timestamp REAL,
                embed_dict TEXT,
                image_bytes BLOB,
                PRIMARY KEY (guild_id, timeframe)
            )
        ''')
        self.db_conn.commit()

    def cog_unload(self):
        self.db_conn.close()

    def calculate_points(self, user_rating: int, problem_rating: int) -> float:
        """
        Calculates fair points based on the Elo expected probability curve.
        """
        u_rating = max(800, user_rating or 800)
        p_rating = problem_rating or 800
        
        base_points = p_rating / 100.0
        multiplier = 2.0 ** ((p_rating - u_rating) / 400.0)
        
        return round(base_points * multiplier, 2)

    async def _generate_leaderboard(self, ctx, start_timestamp: float, title: str, timeframe: str):
        """Fetches live data from API, saves to cache, and generates the leaderboard image."""
        # 0. Check Cache
        cached_row = self.db_conn.execute(
            'SELECT timestamp, embed_dict, image_bytes FROM cache_v3 WHERE guild_id = ? AND timeframe = ?', 
            (ctx.guild.id, timeframe)
        ).fetchone()

        if cached_row:
            cache_time, cached_embed_dict, cached_image_bytes = cached_row
            if time.time() - cache_time < self.CACHE_DURATION:
                embed = discord.Embed.from_dict(json.loads(cached_embed_dict))
                discord_file = discord.File(io.BytesIO(cached_image_bytes), filename='fair_leaderboard.png') if cached_image_bytes else None
                return embed, discord_file

        users = cf_common.user_db.get_cf_users_for_guild(ctx.guild.id)
        if not users:
            embed = discord.Embed(title=title, description="No handles registered in this server.", color=discord.Color.red())
            return embed, None

        # 1. Gather handle mapping
        handles = [user.handle for _, user in users]
        handle_to_user_id = {user.handle: user_id for user_id, user in users}
        
        try:
            # 2. Fetch fresh user objects & ratings directly from CF API
            fresh_users = []
            chunk_size = 300
            for i in range(0, len(handles), chunk_size):
                chunk = handles[i:i + chunk_size]
                fresh_users.extend(await cf.user.info(handles=chunk))
            
            # 3. Update the local user_db cache with the freshly fetched data 
            # This ensures that it is reflected in mgg, wgg, and dgg databases too
            if hasattr(cf_common.user_db, 'cache_cf_users'):
                cf_common.user_db.cache_cf_users(fresh_users)
            else:
                for user in fresh_users:
                    if hasattr(cf_common.user_db, 'cache_cf_user'):
                        cf_common.user_db.cache_cf_user(user)
                    elif hasattr(cf_common.user_db, 'save_cf_user'):
                        cf_common.user_db.save_cf_user(user)
                    
            user_ratings = {u.handle: u.rating for u in fresh_users}
            
            # 4. Fetch submissions concurrently
            async def get_subs(handle):
                try:
                    return handle, await cf.user.status(handle=handle)
                except Exception as e:
                    logger.warning(f"Failed to fetch subs for {handle}: {e}")
                    return handle, []

            tasks = [get_subs(handle) for handle in handles]
            results = await asyncio.gather(*tasks)
            subs_by_handle = dict(results)
            
            # 5. Calculate Points
            leaderboard = []
            for handle, subs in subs_by_handle.items():
                if not subs: continue
                
                rating = user_ratings.get(handle, 800)
                solved_problems = set()
                total_points = 0.0
                
                for sub in subs:
                    # Filter by the time window and ensure the verdict is 'OK'
                    if sub.creationTimeSeconds >= start_timestamp and sub.verdict == 'OK':
                        prob_id = f"{sub.problem.contestId}{sub.problem.index}"
                        
                        # Only count the problem if it hasn't been solved already this period
                        if prob_id not in solved_problems:
                            solved_problems.add(prob_id)
                            pts = self.calculate_points(rating, sub.problem.rating)
                            total_points += pts
                            
                # Only add users who actually solved something to the board
                if solved_problems:
                    user_id = handle_to_user_id[handle]
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

        # 6. Sort and Render
        leaderboard.sort(key=lambda x: x['points'], reverse=True)
        
        if not leaderboard:
            embed = discord.Embed(title=title, description="No one has solved any problems in this time period. Time to get to work!", color=discord.Color.gold())
            self.db_conn.execute(
                'INSERT OR REPLACE INTO cache_v3 (guild_id, timeframe, timestamp, embed_dict, image_bytes) VALUES (?, ?, ?, ?, ?)',
                (ctx.guild.id, timeframe, time.time(), json.dumps(embed.to_dict()), None)
            )
            self.db_conn.commit()
            return embed, None
            
        rankings = []
        for i, entry in enumerate(leaderboard[:20]):
            member = ctx.guild.get_member(entry['user_id'])
            discord_handle = member.display_name if member else ""
            score_str = f"{entry['solved_count']} / {entry['points']:.2f}"
            rankings.append((i, discord_handle, entry['handle'], entry['rating'], score_str))
            
        image_bytes = get_fair_leaderboard_image(rankings)
        discord_file = discord.File(io.BytesIO(image_bytes), filename='fair_leaderboard.png')
            
        embed = discord.Embed(title=title, color=discord.Color.gold())
        embed.set_image(url="attachment://fair_leaderboard.png")
        embed.set_footer(text=f"Points reward solving harder problems based on rating! (Updates every 30m)")
        
        self.db_conn.execute(
            'INSERT OR REPLACE INTO cache_v3 (guild_id, timeframe, timestamp, embed_dict, image_bytes) VALUES (?, ?, ?, ?, ?)',
            (ctx.guild.id, timeframe, time.time(), json.dumps(embed.to_dict()), image_bytes)
        )
        self.db_conn.commit()
        
        return embed, discord_file

    @commands.hybrid_command(description="Update user ratings and cache to ensure they are fresh", aliases=["updateratings", "refreshfair"])
    @commands.has_any_role(constants.TLE_ADMIN, constants.TLE_MODERATOR)
    async def update_fair_cache(self, ctx):
        """Fetches the latest ratings for all guild members and updates the cache/DB."""
        await ctx.send("🔄 Fetching fresh ratings from Codeforces. This might take a moment...")
        
        users = cf_common.user_db.get_cf_users_for_guild(ctx.guild.id)
        if not users:
            await ctx.send("❌ No users registered in this server.")
            return
        
        handles = list(set([user.handle for user_id, user in users]))
        
        try:
            fresh_users = []
            chunk_size = 300
            for i in range(0, len(handles), chunk_size):
                chunk = handles[i:i + chunk_size]
                fresh_users.extend(await cf.user.info(handles=chunk))
            
            # Properly update the database tables used by mgg/wgg/dgg
            if hasattr(cf_common.user_db, 'cache_cf_users'):
                cf_common.user_db.cache_cf_users(fresh_users)
            else:
                for user in fresh_users:
                    if hasattr(cf_common.user_db, 'cache_cf_user'):
                        cf_common.user_db.cache_cf_user(user)
                    elif hasattr(cf_common.user_db, 'save_cf_user'):
                        cf_common.user_db.save_cf_user(user)

            await ctx.send(f"✅ Successfully updated the cache and DB for **{len(fresh_users)}** users!")
        except Exception as e:
            await ctx.send(f"❌ Error updating cache: {e}")

    @commands.hybrid_command(description="Recommend a fair duel between active DGG/WGG/MGG participants", usage="[handle]")
    async def fair_duel(self, ctx, *args: str):
        """Recommends a fair duel between active Gitgud participants. Provide a handle to find an opponent for them."""
        guild_id = ctx.guild.id
        res = cf_common.user_db.get_cf_users_for_guild(guild_id)
        if not res:
            await ctx.send("❌ No registered users found in this server.")
            return

        active_users = []
        now = datetime.datetime.now().timestamp()
        
        # MGG / WGG / DGG activity check (checking local gitlog)
        thirty_days_ago = now - (30 * 24 * 60 * 60)

        for user_id, cf_user in res:
            data = cf_common.user_db.gitlog(user_id)
            if not data:
                continue
            
            has_recent = False
            for entry in data:
                finish = entry[1]
                if finish and finish >= thirty_days_ago:
                    has_recent = True
                    break
            
            if has_recent and cf_user.rating is not None:
                active_users.append((user_id, cf_user))

        # Check if user provided arguments
        if not args:
            # === NO HANDLE PROVIDED: NORMAL BEHAVIOR (ANY TWO ACTIVE USERS) ===
            if len(active_users) < 2:
                await ctx.send("❌ Not enough active participants in the recent gitgud challenges to recommend a duel.")
                return

            active_users.sort(key=lambda x: x[1].rating)
            
            fair_pairs = []
            best_pair = None
            min_diff = float('inf')

            for i in range(len(active_users)):
                for j in range(i + 1, len(active_users)):
                    diff = abs(active_users[i][1].rating - active_users[j][1].rating)
                    if diff <= 100:
                        fair_pairs.append((active_users[i], active_users[j], diff))
                    
                    if diff < min_diff:
                        min_diff = diff
                        best_pair = (active_users[i], active_users[j], diff)

            if fair_pairs:
                chosen_pair = random.choice(fair_pairs)
            else:
                chosen_pair = best_pair

            user1, user2, diff = chosen_pair
        else:
            # === HANDLE PROVIDED: FIND BEST DUEL FOR SPECIFIC USER ===
            try:
                resolved_users = await cf_common.resolve_handles(ctx, self.converter, args)
                target_cf_user = resolved_users[0]
            except Exception as e:
                await ctx.send(f"❌ Failed to resolve handle: {e}")
                return
                
            target_handle = target_cf_user.handle
            target_rating = target_cf_user.rating or 1500
            
            # Find the target user's Discord ID if they are registered in the server
            target_user_id = None
            for u_id, c_user in res:
                if c_user.handle.lower() == target_handle.lower():
                    target_user_id = u_id
                    break
                    
            user1 = (target_user_id, target_cf_user)
            
            # Find the best opponent from the active users list
            fair_opponents = []
            best_opponent = None
            min_diff = float('inf')

            for u_id, c_user in active_users:
                # Prevent dueling yourself
                if c_user.handle.lower() == target_handle.lower():
                    continue
                    
                diff = abs(target_rating - c_user.rating)
                if diff <= 100:
                    fair_opponents.append(( (u_id, c_user), diff ))
                
                if diff < min_diff:
                    min_diff = diff
                    best_opponent = ( (u_id, c_user), diff )

            if fair_opponents:
                chosen_opp_data = random.choice(fair_opponents)
            else:
                chosen_opp_data = best_opponent

            if not chosen_opp_data:
                await ctx.send("❌ Not enough active participants to find an opponent.")
                return

            user2, diff = chosen_opp_data
            
        # Display the result
        member1 = ctx.guild.get_member(user1[0]) if user1[0] else None
        member2 = ctx.guild.get_member(user2[0]) if user2[0] else None
        
        mention1 = member1.mention if member1 else f"`{user1[1].handle}`"
        mention2 = member2.mention if member2 else f"`{user2[1].handle}`"
        
        rating1 = user1[1].rating if user1[1].rating is not None else "Unrated"
        rating2 = user2[1].rating if user2[1].rating is not None else "Unrated"

        embed = discord.Embed(
            title="⚔️ Fair Duel Recommendation ⚔️",
            description=f"Based on recent active participation in the Gitgudders (DGG/WGG/MGG), we recommend a duel between:\n\n"
                        f"🔴 {mention1} (Rating: **{rating1}**)\n"
                        f"🔵 {mention2} (Rating: **{rating2}**)\n\n"
                        f"**Rating Difference:** {diff} points",
            color=discord.Color.dark_teal()
        )
        embed.set_footer(text=f"Pro-tip: Type ';duel challenge {user2[1].handle}' to start the duel!")
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="View the Daily Fair Leaderboard", aliases=["dfair", "dsp"])
    async def dailyfair(self, ctx):
        """Displays the Daily Fair leaderboard (top points earned today)."""
        async with ctx.typing():
            now = datetime.datetime.now()
            start_time_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            embed, discord_file = await self._generate_leaderboard(ctx, start_time_dt.timestamp(), f"🗓️ Daily Fair Leaderboard - {start_time_dt.strftime('%b %d')}", 'daily')
            
            if discord_file:
                await ctx.send(embed=embed, file=discord_file)
            else:
                await ctx.send(embed=embed)

    @commands.hybrid_command(description="View the Weekly Fair Leaderboard", aliases=["wfair", "wsp"])
    async def weeklyfair(self, ctx):
        """Displays the Weekly Fair leaderboard (top points earned this week)."""
        async with ctx.typing():
            now = datetime.datetime.now()
            start_of_week = now - datetime.timedelta(days=now.weekday())
            start_time_dt = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
            
            embed, discord_file = await self._generate_leaderboard(ctx, start_time_dt.timestamp(), f"🏆 Weekly Fair Leaderboard (Week {start_time_dt.isocalendar()[1]})", 'weekly')
            
            if discord_file:
                await ctx.send(embed=embed, file=discord_file)
            else:
                await ctx.send(embed=embed)

    @commands.hybrid_command(description="View the Monthly Fair Leaderboard", aliases=["mfair", "msp"])
    async def monthlyfair(self, ctx):
        """Displays the Monthly Fair leaderboard (top points earned this month)."""
        async with ctx.typing():
            now = datetime.datetime.now()
            start_time_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            embed, discord_file = await self._generate_leaderboard(ctx, start_time_dt.timestamp(), f"🏆 Monthly Fair Leaderboard - {start_time_dt.strftime('%B %Y')}", 'monthly')
            
            if discord_file:
                await ctx.send(embed=embed, file=discord_file)
            else:
                await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Fair(bot))
