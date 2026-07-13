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

try:
    from utils import cf_common
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

    async def _get_solved_problems(self, handle: str):
        url = f"https://codeforces.com/api/user.status?handle={handle}"
        async with self.session.get(url) as resp:
            if resp.status != 200: return None
            data = await resp.json()
            if data.get("status") != "OK": return None
            solved = set()
            for submission in data.get("result", []):
                if submission.get("verdict") == "OK":
                    prob = submission.get("problem", {})
                    c_id = str(prob.get("contestId", ""))
                    idx = str(prob.get("index", "")).upper()
                    if c_id and idx: solved.add((c_id, idx))
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
                # cf_common dynamically resolves @mentions or straight handle strings
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
        
        solved = await self._get_solved_problems(handle)
        if solved is None: return await ctx.send(f"❌ Could not find Codeforces handle: `{handle}`")
        
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
        await ctx.send(embed=embed)

    @commands.group(name="tle", invoke_without_command=True)
    async def tle_challenge(self, ctx, rating: int = None):
        """Request a problem. Usage: ;tle <rating>"""
        if not rating: return await ctx.send("Usage: `;tle <rating>`")
        
        if HAS_CF_COMMON:
            try:
                # Passing an empty tuple to resolve_handles tells TLE to fetch the author's saved handle
                handles = await cf_common.resolve_handles(ctx, self.converter, tuple())
                handle = handles[0]
            except Exception as e:
                msg = str(e) or "Set your handle first via the bot's identity commands."
                return await ctx.send(f"❌ {msg}")
        else:
            return await ctx.send("❌ Cannot resolve handle because standard TLE dependencies are missing.")

        # Update local DB handle map so the leaderboard still knows this discord_id maps to this handle
        self.cursor.execute('INSERT OR IGNORE INTO users (discord_id, handle, points) VALUES (?, ?, 0)', (ctx.author.id, handle))
        self.cursor.execute('UPDATE users SET handle = ? WHERE discord_id = ?', (handle, ctx.author.id))
        self.conn.commit()

        self.cursor.execute('SELECT problem_url FROM active_challenges WHERE discord_id = ?', (ctx.author.id,))
        if self.cursor.fetchone(): return await ctx.send("❌ You already have an active challenge!")

        all_problems = self._get_problems_by_rating([rating])
        solved_set = await self._get_solved_problems(handle)
        unsolved = [p for p in all_problems if self._parse_cf_url(p[0]) not in solved_set]

        if not unsolved: return await ctx.send("🏆 No unsolved problems found for this rating.")
        chosen_url, r = random.choice(unsolved)
        
        self.cursor.execute('INSERT INTO active_challenges VALUES (?, ?, ?, ?)', (ctx.author.id, chosen_url, r, int(time.time())))
        self.conn.commit()
        await ctx.send(f"🎯 **New Challenge ({r}) for {handle}:** {chosen_url}")

    @tle_challenge.command(name="done")
    async def tle_done(self, ctx):
        # Handle will exist here properly because the main command upserts it into the 'users' table
        self.cursor.execute('SELECT problem_url, rating, handle FROM active_challenges JOIN users USING(discord_id) WHERE discord_id = ?', (ctx.author.id,))
        row = self.cursor.fetchone()
        if not row: return await ctx.send("No active challenge.")
        
        url, rating, handle = row
        c_id, idx = self._parse_cf_url(url)
        solved = await self._get_solved_problems(handle)
        
        if (c_id, idx) in solved:
            self.cursor.execute('UPDATE users SET points = points + ? WHERE discord_id = ?', (rating // 100, ctx.author.id))
            self.cursor.execute('DELETE FROM active_challenges WHERE discord_id = ?', (ctx.author.id,))
            self.conn.commit()
            await ctx.send("✅ Challenge completed! Points awarded.")
        else:
            await ctx.send("❌ Problem not marked as solved on Codeforces yet.")

async def setup(bot):
    await bot.add_cog(CP31(bot))
