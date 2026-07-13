import os
import re
import json
import time
import random
import sqlite3
import io
import aiohttp
import discord
from discord.ext import commands

# Corrected imports for standard TLE bot and its forks
try:
    from tle.util import codeforces_common as cf_common
    HAS_CF_COMMON = True
except ImportError:
    HAS_CF_COMMON = False

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

CP31_DIR = "cp31"
DB_FILE = "cp31_tle.db"
CACHE_TTL = 43200 # 12 hours

# Matches both /contest/123/problem/A and /problemset/problem/123/A
CF_URL_REGEX = re.compile(
    r'codeforces\.com/(?:contest/(\d+)/problem/([A-Za-z0-9]+)|problemset/problem/(\d+)/([A-Za-z0-9]+))'
)

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
        
        # We keep the users table to track leaderboard points and locally cache their current handle
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

    def _generate_ranklist_image(self, users_data, current_handle):
        """Generates a PIL image for the leaderboard."""
        if not HAS_PIL: return None
        row_height, header_height, width = 35, 40, 650
        height = header_height + (len(users_data) * row_height)
        img = Image.new('RGB', (width, height), color='#FFFFFF')
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        
        draw.rectangle([0, 0, width, header_height], fill='#36393F')
        y = header_height
        for i, (disc_id, handle, points) in enumerate(users_data, start=1):
            bg_color = '#FFFFFF' if i % 2 != 0 else '#F2F2F2'
            draw.rectangle([0, y, width, y + row_height], fill=bg_color)
            text_color = '#2ECC71' if handle == current_handle else '#333333'
            draw.text((20, y + 8), str(i), fill=text_color, font=font)
            draw.text((80, y + 8), handle[:22], fill=text_color, font=font)
            draw.text((550, y + 8), str(points), fill=text_color, font=font)
            y += row_height
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf

    def _parse_cf_url(self, url: str):
        match = CF_URL_REGEX.search(url)
        if match:
            contest_id = match.group(1) or match.group(3)
            index = match.group(2) or match.group(4)
            return str(contest_id), str(index).upper()
        return None, None

    async def _get_solved_problems(self, handle: str, force_update: bool = False):
        """Fetches solved problems from Codeforces API with a persistent SQLite cache mechanism."""
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

    @commands.command(name="tle_handle")
    async def tle_handle(self, ctx, *args):
        """View CP31 progress. Usage: ;tle_handle [handle or @user]"""
        if HAS_CF_COMMON:
            try:
                if not args:
                    # If no arguments provided, directly fetch the author's handle from TLE's db
                    handle = cf_common.user_db.get_handle(ctx.author.id, "Global")
                    if not handle:
                        return await ctx.send("❌ Could not resolve handle. Have you set it using the bot's identify command?")
                else:
                    # Dynamically resolve @mentions or straight handle strings
                    handles = await cf_common.resolve_handles(ctx, self.converter, args)
                    handle = handles[0]
            except Exception as e:
                msg = str(e) or "Could not resolve handle. Have you set it using the bot's identify command?"
                return await ctx.send(f"❌ {msg}")
        else:
            # Fallback if the bot is missing TLE's utils
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

    @commands.group(name="tle", invoke_without_command=True)
    async def tle_challenge(self, ctx, rating: int = None):
        """Request a problem. Usage: ;tle <rating>"""
        if not rating: return await ctx.send("Usage: `;tle <rating>`")
        
        if HAS_CF_COMMON:
            # Fetch handle directly from DB instead of using resolve_handles to avoid min/max arguments error
            handle = cf_common.user_db.get_handle(ctx.author.id, "Global")
            if not handle:
                return await ctx.send("❌ Set your handle first via the bot's identify command.")
        else:
            return await ctx.send("❌ Cannot resolve handle because standard TLE dependencies are missing.")

        # Database checks before making API calls
        self.cursor.execute('SELECT problem_url FROM active_challenges WHERE discord_id = ?', (ctx.author.id,))
        if self.cursor.fetchone(): 
            return await ctx.send("❌ You already have an active challenge!")

        # Update local DB handle map so the leaderboard still knows this discord_id maps to this handle
        self.cursor.execute('INSERT OR IGNORE INTO users (discord_id, handle, points) VALUES (?, ?, 0)', (ctx.author.id, handle))
        self.cursor.execute('UPDATE users SET handle = ? WHERE discord_id = ?', (handle, ctx.author.id))
        self.conn.commit()

        wait_msg = await ctx.send("⏳ Searching for a suitable unsolved problem...")

        all_problems = self._get_problems_by_rating([rating])
        solved_set = await self._get_solved_problems(handle)
        
        if solved_set is None:
             return await wait_msg.edit(content=f"❌ Failed to reach Codeforces API for user `{handle}`.")

        unsolved = [p for p in all_problems if self._parse_cf_url(p[0]) not in solved_set]

        if not unsolved: 
            return await wait_msg.edit(content="🏆 No unsolved problems found for this rating.")
            
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
        
        # force_update=True ensures they don't get punished by the cache if they literally just solved it
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
        """
        Shows the CP31 leaderboard.
        
        Points are awarded based on the difficulty of the problem solved.
        Formula: Points = Rating / 100
        For example: An 800-rated problem gives 8 points, a 1500 gives 15 points, etc.
        """
        self.cursor.execute('SELECT discord_id, handle, points FROM users WHERE points > 0 ORDER BY points DESC LIMIT ?', (limit,))
        users_data = self.cursor.fetchall()
        
        if not users_data:
            return await ctx.send("🏆 The leaderboard is currently empty! Use `;tle <rating>` to start earning points.")
            
        current_handle = None
        if HAS_CF_COMMON:
            current_handle = cf_common.user_db.get_handle(ctx.author.id, "Global")
        else:
            self.cursor.execute('SELECT handle FROM users WHERE discord_id = ?', (ctx.author.id,))
            row = self.cursor.fetchone()
            if row: current_handle = row[0]
            
        if HAS_PIL:
            buf = self._generate_ranklist_image(users_data, current_handle)
            if buf:
                return await ctx.send(file=discord.File(buf, filename="leaderboard.png"))
                
        embed = discord.Embed(title="🏆 CP31 Leaderboard", color=0xFFD700)
        desc = ""
        for i, (disc_id, handle, points) in enumerate(users_data, start=1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"`{i}.`"
            prefix = "**" if handle == current_handle else ""
            desc += f"{medal} {prefix}{handle}{prefix}: {points} pts\n"
        embed.description = desc
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CP31(bot))
