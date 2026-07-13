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
        self._setup_directories()
        self._setup_database()
        self.session = aiohttp.ClientSession()

    def _setup_directories(self):
        """Creates the cp31 directory and dummy files if they don't exist."""
        if not os.path.exists(CP31_DIR):
            os.makedirs(CP31_DIR)
            # Create a sample 800.txt to prevent crashing on first run
            with open(os.path.join(CP31_DIR, "800.txt"), "w") as f:
                f.write("https://codeforces.com/problemset/problem/1900/A\n")
                f.write("https://codeforces.com/problemset/problem/1899/A\n")

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
        self.conn.commit()

    def cog_unload(self):
        """Cleanup when the cog is unloaded."""
        self.conn.close()
        self.bot.loop.create_task(self.session.close())

    def _generate_ranklist_image(self, users_data, current_handle):
        """Generates a PIL image for the leaderboard similar to TLE."""
        if not HAS_PIL:
            return None
            
        row_height = 35
        header_height = 40
        width = 650
        height = header_height + (len(users_data) * row_height)
        
        img = Image.new('RGB', (width, height), color='#FFFFFF')
        draw = ImageDraw.Draw(img)
        
        # Fallback fonts for multiple platforms
        try:
            font = ImageFont.truetype("arial.ttf", 16)
            font_bold = ImageFont.truetype("arialbd.ttf", 16)
        except OSError:
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", 16)
                font_bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
            except OSError:
                font = ImageFont.load_default()
                font_bold = font

        # Draw Header
        draw.rectangle([0, 0, width, header_height], fill='#36393F')
        draw.text((20, 10), "#", fill='#FFFFFF', font=font_bold)
        draw.text((80, 10), "Name", fill='#FFFFFF', font=font_bold)
        draw.text((300, 10), "Handle", fill='#FFFFFF', font=font_bold)
        draw.text((550, 10), "Points", fill='#FFFFFF', font=font_bold)
        
        # Draw Rows
        y = header_height
        for i, (disc_id, handle, points) in enumerate(users_data, start=1):
            bg_color = '#FFFFFF' if i % 2 != 0 else '#F2F2F2'
            draw.rectangle([0, y, width, y + row_height], fill=bg_color)
            
            text_color = '#2ECC71' if handle == current_handle else '#333333'
            
            user_obj = self.bot.get_user(disc_id)
            name = user_obj.display_name if user_obj else f"User {disc_id}"
            
            # Left accent for the user who just got points (Teal triangle)
            if handle == current_handle:
                draw.polygon([(0, y), (12, y + row_height//2), (0, y + row_height)], fill='#1ABC9C')
                
            draw.text((20, y + 8), str(i), fill=text_color, font=font)
            draw.text((80, y + 8), name[:22], fill=text_color, font=font)
            draw.text((300, y + 8), handle, fill=text_color, font=font)
            draw.text((550, y + 8), str(points), fill=text_color, font=font)
            
            y += row_height
            
        # Draw border
        draw.rectangle([0, 0, width-1, height-1], outline='#2F3136', width=2)
        
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf

    def _parse_cf_url(self, url: str):
        """Extracts contestId and index from a Codeforces URL."""
        match = CF_URL_REGEX.search(url)
        if match:
            # Group 1/2 are for contest format, 3/4 are for problemset format
            contest_id = match.group(1) or match.group(3)
            index = match.group(2) or match.group(4)
            return str(contest_id), str(index).upper()
        return None, None

    async def _get_solved_problems(self, handle: str):
        """Fetches the set of (contestId, index) that a user has solved."""
        url = f"https://codeforces.com/api/user.status?handle={handle}"
        async with self.session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if data.get("status") != "OK":
                return None
            
            solved = set()
            for submission in data.get("result", []):
                if submission.get("verdict") == "OK":
                    prob = submission.get("problem", {})
                    c_id = str(prob.get("contestId", ""))
                    idx = str(prob.get("index", "")).upper()
                    if c_id and idx:
                        solved.add((c_id, idx))
            return solved

    def _get_problems_by_rating(self, ratings: list):
        """Loads all problem URLs from the matching cp31 rating txt files."""
        problems = []
        for r in ratings:
            filepath = os.path.join(CP31_DIR, f"{r}.txt")
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            problems.append((line, r))
        return problems

    @commands.group(invoke_without_command=True)
    async def tle_handle(self, ctx):
        """Manage your Codeforces handle for TLE challenges."""
        await ctx.send("Usage: `;tle_handle set <codeforces_handle>`")

    @tle_handle.command(name="set")
    async def handle_set(self, ctx, handle: str):
        """Links your Discord account to a Codeforces handle."""
        # Verify handle exists
        solved = await self._get_solved_problems(handle)
        if solved is None:
            return await ctx.send(f"❌ Could not find Codeforces handle: `{handle}`")
        
        self.cursor.execute('''
            INSERT INTO users (discord_id, handle, points) 
            VALUES (?, ?, 0)
            ON CONFLICT(discord_id) DO UPDATE SET handle=excluded.handle
        ''', (ctx.author.id, handle))
        self.conn.commit()
        
        embed = discord.Embed(title="Handle Set!", description=f"Your handle is now linked to **{handle}**.", color=0x00FF00)
        await ctx.send(embed=embed)

    @commands.group(name="tle", invoke_without_command=True)
    async def tle_challenge(self, ctx, rating_input: str = None):
        """Request a problem. Format: ;tle 800 OR ;tle 800-1200"""
        if rating_input is None:
            return await ctx.send("Usage: `;tle <rating>` or `;tle <rating1>-<rating2>`\nSubcommands: `;tle done`, `;tle skip`")

        self.cursor.execute('SELECT handle FROM users WHERE discord_id = ?', (ctx.author.id,))
        row = self.cursor.fetchone()
        if not row:
            return await ctx.send("❌ You haven't set your handle yet! Use `;tle_handle set <handle>` first.")
        handle = row[0]

        # Check if user already has an active challenge
        self.cursor.execute('SELECT problem_url FROM active_challenges WHERE discord_id = ?', (ctx.author.id,))
        if self.cursor.fetchone():
            return await ctx.send("❌ You already have an active challenge! Finish it with `;tle_gotgud` or cancel it with `;tle_nogotgud`.")

        ratings = []
        try:
            if '-' in rating_input:
                start, end = map(int, rating_input.split('-'))
                ratings = [r for r in range(start, end + 1, 100)]
            else:
                ratings = [int(rating_input)]
        except ValueError:
            return await ctx.send("❌ Invalid rating format. Use a single number (e.g., `800`) or a range (e.g., `800-1200`).")

        all_problems = self._get_problems_by_rating(ratings)
        if not all_problems:
            return await ctx.send(f"❌ No problems found for rating(s): {', '.join(map(str, ratings))}. (Are the txt files missing in the `{CP31_DIR}` folder?)")

        # Fetch solved problems to filter them out
        solved_set = await self._get_solved_problems(handle)
        if solved_set is None:
            return await ctx.send("❌ Failed to reach Codeforces API. Please try again later.")

        unsolved = []
        for url, rating in all_problems:
            c_id, idx = self._parse_cf_url(url)
            if c_id and idx and (c_id, idx) not in solved_set:
                unsolved.append((url, rating))

        if not unsolved:
            return await ctx.send("🏆 You have already solved all problems in the `cp31` lists for this rating range!")

        chosen_url, chosen_rating = random.choice(unsolved)
        points_to_gain = chosen_rating // 100

        self.cursor.execute('''
            INSERT INTO active_challenges (discord_id, problem_url, rating, issue_time)
            VALUES (?, ?, ?, ?)
        ''', (ctx.author.id, chosen_url, chosen_rating, int(time.time())))
        self.conn.commit()

        embed = discord.Embed(
            title="🎯 New CP31 Challenge Issued!",
            description=f"**Handle:** [{handle}](https://codeforces.com/profile/{handle})\n"
                        f"**Problem:** [Click here to open the problem]({chosen_url})",
            color=0x3498DB # Blue
        )
        embed.add_field(name="Rating", value=f"{chosen_rating}", inline=True)
        embed.add_field(name="Points at Stake", value=f"{points_to_gain}", inline=True)
        embed.set_footer(text="Solve this problem and use ;tle done to claim your points!")
        
        await ctx.send(embed=embed)

    @tle_challenge.command(name="done")
    async def tle_done(self, ctx):
        """Checks if you solved your active challenge and awards points."""
        self.cursor.execute('''
            SELECT a.problem_url, a.rating, a.issue_time, u.handle 
            FROM active_challenges a
            JOIN users u ON a.discord_id = u.discord_id
            WHERE a.discord_id = ?
        ''', (ctx.author.id,))
        
        row = self.cursor.fetchone()
        if not row:
            return await ctx.send("You don't have an active challenge! Start one with `;tle <rating>`.")
        
        prob_url, rating, issue_time, handle = row
        c_id, idx = self._parse_cf_url(prob_url)

        # Verify completion
        solved_set = await self._get_solved_problems(handle)
        if solved_set is None:
            return await ctx.send("Failed to reach Codeforces API. Please try again later.")

        if (c_id, idx) in solved_set:
            points_gained = rating // 100
            
            # Calculate time taken
            time_taken_seconds = int(time.time()) - issue_time
            minutes = time_taken_seconds // 60
            
            self.cursor.execute('UPDATE users SET points = points + ? WHERE discord_id = ?', (points_gained, ctx.author.id))
            self.cursor.execute('DELETE FROM active_challenges WHERE discord_id = ?', (ctx.author.id,))
            self.conn.commit()

            # Fetch top users for the ranklist simulation
            self.cursor.execute('''
                SELECT discord_id, handle, points
                FROM users 
                WHERE points > 0 
                ORDER BY points DESC 
                LIMIT 10
            ''')
            top_users_data = self.cursor.fetchall()
            
            # Mimic the TLE bot output from the screenshot
            response_msg = f"Challenge completed in {minutes} minutes. {handle} gained {points_gained} alltime ranklist points and {points_gained} monthly ranklist points."
            
            image_buffer = self._generate_ranklist_image(top_users_data, handle)
            
            if image_buffer:
                file = discord.File(image_buffer, filename="ranklist.png")
                await ctx.send(response_msg, file=file)
            else:
                # Fallback text if PIL is not installed
                table = "```ansi\n"
                table += f"{'#':<3} {'Name':<15} {'Handle':<25} {'Points':<6}\n"
                table += "-" * 51 + "\n"
                
                for i, user_row in enumerate(top_users_data, start=1):
                    disc_id, h, p = user_row
                    user_obj = self.bot.get_user(disc_id)
                    name = user_obj.display_name if user_obj else "User"
                    if h == handle:
                         table += f"\u001b[0;32m{i:<3} {name[:15]:<15} {h:<25} {p:<6}\u001b[0m\n"
                    else:
                         table += f"{i:<3} {name[:15]:<15} {h:<25} {p:<6}\n"
                
                table += "```"
                await ctx.send(response_msg + "\n" + table)
        else:
            await ctx.send(f"Codeforces doesn't show an 'OK' verdict for this problem yet. Make sure you solved it on the handle `{handle}`.")

    @tle_challenge.command(name="skip")
    async def tle_skip(self, ctx):
        """Cancels your current active challenge."""
        self.cursor.execute('SELECT * FROM active_challenges WHERE discord_id = ?', (ctx.author.id,))
        if not self.cursor.fetchone():
            return await ctx.send("You don't have an active challenge.")
            
        self.cursor.execute('DELETE FROM active_challenges WHERE discord_id = ?', (ctx.author.id,))
        self.conn.commit()
        await ctx.send("Challenge skipped.")

    @commands.command(name="tle_lb")
    async def tle_lb(self, ctx):
        """Shows the top 10 users on the CP31 leaderboard."""
        self.cursor.execute('SELECT discord_id, handle, points FROM users WHERE points > 0 ORDER BY points DESC LIMIT 10')
        top_users = self.cursor.fetchall()

        if not top_users:
            return await ctx.send("The leaderboard is currently empty! Be the first to earn points using `;tle`.")

        image_buffer = self._generate_ranklist_image(top_users, None)
        
        if image_buffer:
            file = discord.File(image_buffer, filename="leaderboard.png")
            await ctx.send("🏆 **CP31 Leaderboard**", file=file)
        else:
            embed = discord.Embed(title="🏆 CP31 Leaderboard", color=0xF1C40F) # Gold
            
            lb_text = ""
            for i, (disc_id, handle, points) in enumerate(top_users, start=1):
                user_obj = self.bot.get_user(disc_id)
                name = user_obj.display_name if user_obj else "User"
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                lb_text += f"{medal} **{name}** ({handle}) — {points} pts\n"
                
            embed.description = lb_text
            await ctx.send(embed=embed)


async def setup(bot):
    """Function to load the cog automatically by discord.ext.commands"""
    await bot.add_cog(CP31(bot))

# ==============================================================================
# The following block is optional but allows you to run this specific file 
# directly to test it without injecting it into the main bot immediately.
# Replace 'YOUR_DISCORD_BOT_TOKEN' if you want to run it standalone.
# ==============================================================================
if __name__ == "__main__":
    bot = commands.Bot(command_prefix=";", intents=discord.Intents.all())
    
    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user.name}")
        await bot.add_cog(CP31(bot))
        print("CP31 Cog Loaded Successfully.")
        
