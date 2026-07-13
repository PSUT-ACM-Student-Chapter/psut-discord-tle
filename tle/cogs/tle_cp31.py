import os
import re
import json
import time
import random
import sqlite3
import io
import html
import asyncio
import aiohttp

import cairo
import gi
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo

import discord
from discord.ext import commands

try:
    from tle.util import codeforces_common as cf_common
    HAS_CF_COMMON = True
except ImportError:
    HAS_CF_COMMON = False

CP31_DIR = "cp31"
DB_FILE = "cp31_tle.db"
CACHE_TTL = 43200 # 12 hours

# Matches both /contest/123/problem/A and /problemset/problem/123/A
CF_URL_REGEX = re.compile(
    r'codeforces\.com/(?:contest/(\d+)/problem/([A-Za-z0-9]+)|problemset/problem/(\d+)/([A-Za-z0-9]+))'
)

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

def get_cp31_leaderboard_image(rankings):
    """return io.BytesIO image buffer for rankings matching MGG visual style"""
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
        
        # Main row background
        context.move_to(BORDER_MARGIN, y)
        context.line_to(WIDTH - BORDER_MARGIN, y)
        context.line_to(WIDTH - BORDER_MARGIN, nxty)
        context.line_to(BORDER_MARGIN, nxty)
        context.set_source_rgb(*ROW_COLORS[color_index])
        context.fill()

        # Added slanted background for the rank number mimicking the screenshot
        slant_width = 15
        context.move_to(BORDER_MARGIN, y)
        context.line_to(BORDER_MARGIN + WIDTH_RANK, y)
        context.line_to(BORDER_MARGIN + WIDTH_RANK - slant_width, nxty)
        context.line_to(BORDER_MARGIN, nxty)
        # Slightly darker shade of the row background for the slant
        context.set_source_rgb(*[ROW_COLORS[color_index][0] - 0.04]*3)
        context.fill()

    def draw_row(pos, username, handle, rating, color, y, bold=False):
        context.set_source_rgb(*[x/255.0 for x in color])
        context.move_to(BORDER_MARGIN, y)

        def draw(text, width=-1):
            text = html.escape(text)
            if bold:
                text = f'<b>{text}</b>'
            layout.set_width(int((width - COLUMN_MARGIN)*1000))
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
        draw_row(str(pos+1), f'{name}', f'{handle}', str(score), color, y)
        
        # Grandmaster+ initial rendering quirk (black letter overlay)
        if rating and rating >= 3000:
            draw_row('', name[0] if name else "", handle[0] if handle else "", '', BLACK, y)
        y += LINE_HEIGHT

    image_data = io.BytesIO()
    surface.write_to_png(image_data)
    image_data.seek(0)
    return image_data


class CP31(commands.Cog):
    """Commands for CP31 TLE challenges."""

    def __init__(self, bot):
        self.bot = bot
        self.converter = commands.MemberConverter()
        self._setup_directories()
        self._setup_database()
        self.session = aiohttp.ClientSession()

    def _setup_directories(self):
        """Creates the cp31 directory and dummy files if they don't exist."""
        if not os.path.exists(CP31_DIR):
            os.makedirs(CP31_DIR)
            with open(os.path.join(CP31_DIR, "800.txt"), "w") as f:
                f.write("https://codeforces.com/problemset/problem/1900/A\n")

    def _setup_database(self):
        """Initializes the SQLite database for users and active challenges."""
        self.conn = sqlite3.connect(DB_FILE)
        self.cursor = self.conn.cursor()
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                discord_id INTEGER PRIMARY KEY,
                handle TEXT NOT NULL,
                points INTEGER DEFAULT 0
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_challenges (
                discord_id INTEGER PRIMARY KEY,
                problem_url TEXT NOT NULL,
                rating INTEGER NOT NULL,
                issue_time INTEGER NOT NULL
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS solved_problems (
                handle TEXT NOT NULL,
                contest_id TEXT NOT NULL,
                index_id TEXT NOT NULL,
                PRIMARY KEY (handle, contest_id, index_id)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_cache (
                handle TEXT PRIMARY KEY,
                last_fetch INTEGER DEFAULT 0
            )
        ''')
        
        self.conn.commit()

    def cog_unload(self):
        """Cleanup when the cog is unloaded."""
        self.conn.close()
        self.bot.loop.create_task(self.session.close())

    def _parse_cf_url(self, url: str):
        match = CF_URL_REGEX.search(url)
        if match:
            contest_id = match.group(1) or match.group(3)
            index = match.group(2) or match.group(4)
            return str(contest_id), str(index).upper()
        return None, None

    async def _get_solved_problems(self, handle: str, force_update: bool = False):
        """Fetches solved problems from Codeforces API with persistent SQLite cache mechanism."""
        current_time = int(time.time())
        
        if not force_update:
            self.cursor.execute('SELECT last_fetch FROM user_cache WHERE handle = ?', (handle,))
            row = self.cursor.fetchone()
            if row and (current_time - row[0]) < CACHE_TTL:
                self.cursor.execute('SELECT contest_id, index_id FROM solved_problems WHERE handle = ?', (handle,))
                return set((r[0], r[1]) for r in self.cursor.fetchall())

        url = f"https://codeforces.com/api/user.status?handle={handle}"
        async with self.session.get(url) as resp:
            if resp.status != 200: 
                self.cursor.execute('SELECT contest_id, index_id FROM solved_problems WHERE handle = ?', (handle,))
                cached = self.cursor.fetchall()
                return set((r[0], r[1]) for r in cached) if cached else None
                
            data = await resp.json()
            if data.get("status") != "OK": return None
            
            solved = set()
            for submission in data.get("result", []):
                if submission.get("verdict") == "OK":
                    prob = submission.get("problem", {})
                    c_id = str(prob.get("contestId", ""))
                    idx = str(prob.get("index", "")).upper()
                    if c_id and idx: solved.add((c_id, idx))
            
            self.cursor.execute('INSERT OR REPLACE INTO user_cache (handle, last_fetch) VALUES (?, ?)', (handle, current_time))
            self.cursor.executemany(
                'INSERT OR IGNORE INTO solved_problems (handle, contest_id, index_id) VALUES (?, ?, ?)',
                [(handle, c, i) for c, i in solved]
            )
            self.conn.commit()
            return solved

    def _get_problems_by_rating(self, ratings: list):
        problems = []
        for r in ratings:
            filepath = os.path.join(CP31_DIR, f"{r}.txt")
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip(): problems.append((line.strip(), r))
        return problems

    @commands.group(name="tle", invoke_without_command=True)
    async def tle_challenge(self, ctx, rating: str = None):
        """Request a problem. Usage: ;tle <rating> or ;tle <min>-<max> (e.g. 1000-1500)"""
        if not rating: 
            return await ctx.send("Usage: `;tle <rating>` or `;tle <min>-<max>` (e.g., `1000-1500`)")
        
        if HAS_CF_COMMON:
            handle = cf_common.user_db.get_handle(ctx.author.id, "Global")
            if not handle:
                return await ctx.send("❌ Set your handle first via the bot's identify command.")
        else:
            return await ctx.send("❌ Cannot resolve handle because standard TLE dependencies are missing.")

        # Database checks before making API calls
        self.cursor.execute('SELECT problem_url FROM active_challenges WHERE discord_id = ?', (ctx.author.id,))
        if self.cursor.fetchone(): 
            return await ctx.send("❌ You already have an active challenge! Use `;tle done` to verify it.")

        # Parse the rating input (Handles single ratings and ranges like 1000-1500)
        target_ratings = []
        if '-' in rating:
            try:
                min_r, max_r = map(int, rating.split('-'))
                if min_r > max_r:
                    min_r, max_r = max_r, min_r
                # Ensure snap to boundaries (e.g. 100 increments)
                min_r = max(800, (min_r // 100) * 100)
                max_r = min(3500, (max_r // 100) * 100)
                target_ratings = list(range(min_r, max_r + 100, 100))
            except ValueError:
                return await ctx.send("❌ Invalid range format. Use e.g. `1000-1500`.")
        else:
            try:
                val = (int(rating) // 100) * 100
                target_ratings = [val]
            except ValueError:
                return await ctx.send("❌ Invalid rating format. Use a number like `1200`.")
        
        target_ratings = [r for r in target_ratings if 800 <= r <= 3500]
        if not target_ratings:
            return await ctx.send("❌ Ratings must be between 800 and 3500.")

        self.cursor.execute('INSERT OR IGNORE INTO users (discord_id, handle, points) VALUES (?, ?, 0)', (ctx.author.id, handle))
        self.cursor.execute('UPDATE users SET handle = ? WHERE discord_id = ?', (handle, ctx.author.id))
        self.conn.commit()

        wait_msg = await ctx.send("⏳ Searching for a suitable unsolved problem...")

        all_problems = self._get_problems_by_rating(target_ratings)
        solved_set = await self._get_solved_problems(handle)
        
        if solved_set is None:
             return await wait_msg.edit(content=f"❌ Failed to reach Codeforces API for user `{handle}`.")

        unsolved = [p for p in all_problems if self._parse_cf_url(p[0]) not in solved_set]

        if not unsolved: 
            return await wait_msg.edit(content="🏆 No unsolved problems found for the requested rating range.")
            
        chosen_url, r = random.choice(unsolved)
        
        self.cursor.execute('INSERT INTO active_challenges VALUES (?, ?, ?, ?)', (ctx.author.id, chosen_url, r, int(time.time())))
        self.conn.commit()
        
        await wait_msg.edit(content=f"🎯 **New Challenge ({r}) for {handle}:** {chosen_url}")

    @tle_challenge.command(name="done")
    async def tle_done(self, ctx):
        """Verifies if the current active challenge is solved."""
        self.cursor.execute('SELECT problem_url, rating, handle FROM active_challenges JOIN users USING(discord_id) WHERE discord_id = ?', (ctx.author.id,))
        row = self.cursor.fetchone()
        if not row: 
            return await ctx.send("❌ No active challenge.")
        
        url, rating, handle = row
        c_id, idx = self._parse_cf_url(url)
        
        wait_msg = await ctx.send(f"⏳ Verifying your submission for `{handle}` on Codeforces...")
        
        solved = await self._get_solved_problems(handle, force_update=True)
        
        if solved is None:
            return await wait_msg.edit(content="❌ Failed to connect to Codeforces API. Try again later.")
        
        if (c_id, idx) in solved:
            points_gained = rating // 100
            self.cursor.execute('UPDATE users SET points = points + ? WHERE discord_id = ?', (points_gained, ctx.author.id))
            self.cursor.execute('DELETE FROM active_challenges WHERE discord_id = ?', (ctx.author.id,))
            self.conn.commit()
            await wait_msg.edit(content=f"✅ Challenge completed! **+{points_gained} points** awarded.")
        else:
            await wait_msg.edit(content="❌ Problem not marked as solved on Codeforces yet. Make sure your submission is Accepted!")


    @commands.command(name="tle_leaderboard", aliases=["tle_lb"])
    async def tle_leaderboard(self, ctx, limit: int = 15):
        """Shows the CP31 leaderboard formatted using PangoCairo."""
        wait_msg = None
        handle_to_rating = {}
        
        if HAS_CF_COMMON:
            # Sync new users and grab rating data to colorize the PangoCairo Leaderboard
            tle_users = cf_common.user_db.get_cf_users_for_guild(ctx.guild.id)
            if tle_users:
                for uid, cf_user in tle_users:
                    handle_to_rating[cf_user.handle.lower()] = cf_user.rating
            
            # Fetch globally linked users
            global_users = cf_common.user_db.get_handles_for_guild("Global")
            
            self.cursor.execute('SELECT discord_id FROM users')
            existing_users = set(row[0] for row in self.cursor.fetchall())
            
            missing_users = [(disc_id, handle) for disc_id, handle in global_users if disc_id not in existing_users]
            
            if missing_users:
                wait_msg = await ctx.send(f"⏳ Syncing historical data for {len(missing_users)} new user(s)...")
                
                cp31_map = {}
                all_problems = self._get_problems_by_rating(range(800, 3200, 100))
                for url, rating in all_problems:
                    c_id, idx = self._parse_cf_url(url)
                    if c_id and idx:
                        cp31_map[(c_id, idx)] = rating
                
                for disc_id, handle in missing_users:
                    solved = await self._get_solved_problems(handle)
                    points = 0
                    if solved:
                        for c_id, idx in solved:
                            if (c_id, idx) in cp31_map:
                                points += cp31_map[(c_id, idx)] // 100
                    
                    self.cursor.execute('INSERT INTO users (discord_id, handle, points) VALUES (?, ?, ?)', (disc_id, handle, points))
                    self.conn.commit()
                    await asyncio.sleep(0.5)

        self.cursor.execute('SELECT discord_id, handle, points FROM users WHERE points > 0 ORDER BY points DESC LIMIT ?', (limit,))
        users_data = self.cursor.fetchall()
        
        if wait_msg:
            await wait_msg.delete()
            
        if not users_data:
            return await ctx.send("🏆 The leaderboard is currently empty! Use `;tle <rating>` to start earning points.")
            
        # Build rankings structure for get_cp31_leaderboard_image
        # Structure: (pos, name, handle, rating, score)
        rankings = []
        for i, (disc_id, handle, points) in enumerate(users_data):
            member = ctx.guild.get_member(disc_id)
            name = member.display_name if member else handle
            
            # Look up rating to apply Codeforces color mapping, or leave None to render black
            rating = handle_to_rating.get(handle.lower(), None)
            
            # Incorporate Discord Handle with CF Handle similar to mgg layout
            display_handle = f"{handle} ({rating if rating else 'N/A'})"
            
            rankings.append((i, name, display_handle, rating, points))
            
        try:
            buf = get_cp31_leaderboard_image(rankings)
            if buf:
                return await ctx.send(file=discord.File(buf, filename="cp31_leaderboard.png"))
        except Exception as e:
            # Fallback to Text Embed if Cairo isn't properly installed or fails
            embed = discord.Embed(title="🏆 CP31 Leaderboard (Text Fallback)", color=0xFFD700)
            desc = ""
            for i, (disc_id, handle, points) in enumerate(users_data, start=1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"`{i}.`"
                desc += f"{medal} **{handle}**: {points} pts\n"
            embed.description = desc
            await ctx.send(embed=embed)


    @commands.command(name="tle_handle")
    async def tle_handle(self, ctx, *args):
        """View CP31 progress. Usage: ;tle_handle [handle or @user]"""
        if HAS_CF_COMMON:
            try:
                if not args:
                    handle = cf_common.user_db.get_handle(ctx.author.id, "Global")
                    if not handle:
                        return await ctx.send("❌ Could not resolve handle. Have you set it using the bot's identify command?")
                else:
                    handles = await cf_common.resolve_handles(ctx, self.converter, args)
                    handle = handles[0]
            except Exception as e:
                msg = str(e) or "Could not resolve handle. Have you set it using the bot's identify command?"
                return await ctx.send(f"❌ {msg}")
        else:
            handle = args[0] if args else None
            if not handle:
                return await ctx.send("Usage: `;tle_handle <handle>`")
        
        wait_msg = await ctx.send(f"⏳ Fetching CP31 progress for `{handle}`, please wait...")
        
        solved = await self._get_solved_problems(handle)
        if solved is None: 
            return await wait_msg.edit(content=f"❌ Could not find Codeforces handle or API is down: `{handle}`")
        
        all_problems = self._get_problems_by_rating(range(800, 3200, 100))
        stats = {}
        for url, rating in all_problems:
            stats.setdefault(rating, [0, 0])
            stats[rating][1] += 1
            c_id, idx = self._parse_cf_url(url)
            if (c_id, idx) in solved: stats[rating][0] += 1
        
        embed = discord.Embed(title=f"Progress for {handle}", color=0x3498DB)
        for r in sorted(stats.keys()):
            done, total = stats[r]
            if total > 0: embed.add_field(name=f"{r}", value=f"{done}/{total} ({int(done/total*100)}%)", inline=True)
            
        await wait_msg.edit(content=None, embed=embed)


async def setup(bot):
    await bot.add_cog(CP31(bot))
