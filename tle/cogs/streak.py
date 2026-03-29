import asyncio
import datetime
import logging
import math

import discord
from discord.ext import commands, tasks

from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

def is_prime(n):
    """Efficient prime checker for Codeforces submission IDs."""
    if n <= 1:
        return False
    if n <= 3:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    for i in range(5, math.isqrt(n) + 1, 6):
        if n % i == 0 or n % (i + 2) == 0:
            return False
    return True

class Streaks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Safely initialize the new tables inside the existing SQLite DB
        cf_common.user_db.conn.execute('''
            CREATE TABLE IF NOT EXISTS user_streak (
                user_id TEXT PRIMARY KEY,
                current_streak INTEGER DEFAULT 0,
                max_streak INTEGER DEFAULT 0,
                last_ac_date TEXT
            )
        ''')
        
        cf_common.user_db.conn.execute('''
            CREATE TABLE IF NOT EXISTS user_badges (
                user_id TEXT,
                badge_name TEXT,
                awarded_date TEXT,
                PRIMARY KEY (user_id, badge_name)
            )
        ''')
        cf_common.user_db.conn.commit()

        # Start the background checker
        self.update_streaks_task.start()

    def cog_unload(self):
        self.update_streaks_task.cancel()

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc))
    async def update_streaks_task(self):
        """Runs daily at midnight UTC to process streaks and badges for all registered users."""
        self.logger.info("Starting daily streak & badge background update...")
        try:
            users = cf_common.user_db.conn.execute(
                "SELECT DISTINCT user_id, handle FROM user_handle"
            ).fetchall()
        except Exception as e:
            self.logger.error(f"Failed to fetch users from DB: {e}")
            return

        for user_id_int, handle in users:
            await self._update_user_streak(user_id_int, handle)
            await asyncio.sleep(0.5) # Prevent rate-limiting from Codeforces API

        self.logger.info("Daily streak & badge update completed successfully.")

    @update_streaks_task.before_loop
    async def before_update_streaks_task(self):
        await self.bot.wait_until_ready()

    async def _update_user_streak(self, user_id_int, handle):
        """Core logic to fetch submissions, check dates, update streaks, and award badges."""
        user_id_str = str(user_id_int)
        
        row = cf_common.user_db.conn.execute(
            "SELECT current_streak, max_streak, last_ac_date FROM user_streak WHERE user_id = ?",
            (user_id_str,)
        ).fetchone()

        current_streak = row[0] if row else 0
        max_streak = row[1] if row else 0
        last_ac_date = row[2] if row else None

        try:
            # Fetch recent submissions
            subs = await cf.user.status(handle=handle, count=50)
        except Exception as e:
            self.logger.warning(f"Failed to fetch CF status for {handle}: {e}")
            return current_streak, max_streak, False

        # Work in UTC since Codeforces API timestamps are global
        today_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
        yesterday_str = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')

        ac_dates = set()
        for s in subs:
            if s.verdict == 'OK':
                date_str = datetime.datetime.fromtimestamp(s.creationTimeSeconds, datetime.timezone.utc).strftime('%Y-%m-%d')
                ac_dates.add(date_str)

        today_ac = today_str in ac_dates
        yesterday_ac = yesterday_str in ac_dates

        # ==========================================
        # 1. STREAK STATE MACHINE
        # ==========================================
        if today_ac:
            if last_ac_date == yesterday_str:
                current_streak += 1
                last_ac_date = today_str
            elif last_ac_date != today_str:
                current_streak = 1
                last_ac_date = today_str
            max_streak = max(max_streak, current_streak)
        elif yesterday_ac:
            if last_ac_date != yesterday_str and last_ac_date != today_str:
                current_streak = 1 if current_streak == 0 else current_streak + 1
                last_ac_date = yesterday_str
                max_streak = max(max_streak, current_streak)
        else:
            if last_ac_date != today_str and last_ac_date != yesterday_str:
                current_streak = 0

        cf_common.user_db.conn.execute('''
            INSERT INTO user_streak (user_id, current_streak, max_streak, last_ac_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
            current_streak=excluded.current_streak,
            max_streak=excluded.max_streak,
            last_ac_date=excluded.last_ac_date
        ''', (user_id_str, current_streak, max_streak, last_ac_date))
        
        # ==========================================
        # 2. ACHIEVEMENT BADGES LOGIC
        # ==========================================
        existing_badges = {
            r[0] for r in cf_common.user_db.conn.execute(
                "SELECT badge_name FROM user_badges WHERE user_id = ?", (user_id_str,)
            ).fetchall()
        }
        new_badges = []
        
        # Process chronologically for sequential badges like "Sniper"
        subs_chronological = sorted(subs, key=lambda x: x.creationTimeSeconds)
        consecutive_acs = 0
        problem_fails = {}
        ac_languages = set()
        
        for s in subs_chronological:
            if s.verdict == 'TESTING': 
                continue
                
            problem_id = f"{s.problem.contestId}{s.problem.index}"
                
            if s.verdict == 'OK':
                consecutive_acs += 1
                dt = datetime.datetime.fromtimestamp(s.creationTimeSeconds, datetime.timezone.utc)
                
                # Track languages for Polyglot badge
                if getattr(s, 'programmingLanguage', None):
                    # Broaden language grouping to avoid C++14 vs C++17 counting as two
                    lang = s.programmingLanguage.lower()
                    if 'c++' in lang: ac_languages.add('c++')
                    elif 'python' in lang or 'pypy' in lang: ac_languages.add('python')
                    elif 'java' in lang and 'javascript' not in lang: ac_languages.add('java')
                    elif 'rust' in lang: ac_languages.add('rust')
                    elif 'c#' in lang: ac_languages.add('c#')
                    else: ac_languages.add(lang)
                
                # Badge: Night Owl 🦇 (AC between 2 AM and 5 AM UTC)
                if 'Night Owl 🦇' not in existing_badges and 2 <= dt.hour < 5:
                    new_badges.append('Night Owl 🦇')
                    existing_badges.add('Night Owl 🦇')
                
                # Badge: Speed Demon ⚡ (Solve 'A' problem in <= 5 mins during contest)
                if 'Speed Demon ⚡' not in existing_badges:
                    is_contestant = s.author.participantType == 'CONTESTANT'
                    relative_time = getattr(s, 'relativeTimeSeconds', 9999) # fallback if missing
                    if is_contestant and relative_time <= 300 and s.problem.index.startswith('A'):
                        new_badges.append('Speed Demon ⚡')
                        existing_badges.add('Speed Demon ⚡')
                        
                # Badge: Necromancer 🧟 (Solve a problem published > 5 years ago)
                if 'Necromancer 🧟' not in existing_badges and s.problem.contestId:
                    try:
                        contest = cf_common.cache2.contest_cache.get_contest(s.problem.contestId)
                        # 5 years ~= 157,680,000 seconds
                        if contest and s.creationTimeSeconds - contest.startTimeSeconds > 157680000:
                            new_badges.append('Necromancer 🧟')
                            existing_badges.add('Necromancer 🧟')
                    except Exception:
                        pass # Ignore if contest is not found in TLE cache
                
                # Badge: Sniper 🎯 (5 ACs in a row with 0 WAs)
                if 'Sniper 🎯' not in existing_badges and consecutive_acs >= 5:
                    new_badges.append('Sniper 🎯')
                    existing_badges.add('Sniper 🎯')
                    
                # Badge: Early Bird 🌅 (AC between 5 AM and 8 AM UTC)
                if 'Early Bird 🌅' not in existing_badges and 5 <= dt.hour < 8:
                    new_badges.append('Early Bird 🌅')
                    existing_badges.add('Early Bird 🌅')
                    
                # Badge: Persistent 😤 (AC after 5+ failures on the same problem)
                if 'Persistent 😤' not in existing_badges and problem_fails.get(problem_id, 0) >= 5:
                    new_badges.append('Persistent 😤')
                    existing_badges.add('Persistent 😤')
                    
                # Badge: Math Whiz 🧮 (Solve a math tagged problem)
                if 'Math Whiz 🧮' not in existing_badges and s.problem.tags and 'math' in s.problem.tags:
                    new_badges.append('Math Whiz 🧮')
                    existing_badges.add('Math Whiz 🧮')
                    
                # Badge: Graph Master 🕸️ (Solve a graph/tree tagged problem)
                if 'Graph Master 🕸️' not in existing_badges and s.problem.tags and ('graphs' in s.problem.tags or 'trees' in s.problem.tags):
                    new_badges.append('Graph Master 🕸️')
                    existing_badges.add('Graph Master 🕸️')
                    
                # Badge: Prime 🔢 (Submission ID is a prime number)
                if 'Prime 🔢' not in existing_badges and getattr(s, 'id', None) and is_prime(s.id):
                    new_badges.append('Prime 🔢')
                    existing_badges.add('Prime 🔢')
            else:
                consecutive_acs = 0 # Broke the AC streak
                problem_fails[problem_id] = problem_fails.get(problem_id, 0) + 1

        # Badge: Polyglot 🗣️ (ACs in 3+ distinct languages in the recent window)
        if 'Polyglot 🗣️' not in existing_badges and len(ac_languages) >= 3:
            new_badges.append('Polyglot 🗣️')
            existing_badges.add('Polyglot 🗣️')

        # Save any newly awarded badges
        award_date = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
        for badge in new_badges:
            cf_common.user_db.conn.execute(
                "INSERT OR IGNORE INTO user_badges (user_id, badge_name, awarded_date) VALUES (?, ?, ?)",
                (user_id_str, badge, award_date)
            )
            
        cf_common.user_db.conn.commit()
        return current_streak, max_streak, today_ac, new_badges

    async def _assign_streak_roles(self, member, streak):
        """Automatically assigns reward roles based on streak thresholds."""
        guild = member.guild
        role_map = {
            7: "7-Day Streak",     
            30: "30-Day Streak",
            100: "100-Day Streak"
        }
        
        highest_role = None
        for threshold, role_name in sorted(role_map.items(), reverse=True):
            if streak >= threshold:
                highest_role = discord.utils.get(guild.roles, name=role_name)
                break

        if highest_role and highest_role not in member.roles:
            try:
                await member.add_roles(highest_role)
            except discord.Forbidden:
                pass 

    @commands.group(brief='Daily AC Streak commands', invoke_without_command=True)
    async def streak(self, ctx, member: discord.Member = None):
        """Shows your current consecutive days of solving Codeforces problems."""
        member = member or ctx.author
        handle = cf_common.user_db.get_handle(member.id, ctx.guild.id)
        if not handle:
            return await ctx.send(f"{member.display_name} has not identified their Codeforces handle. Use `;handle set`.")

        current_streak, max_streak, today_ac, new_badges = await self._update_user_streak(member.id, handle)
        await self._assign_streak_roles(member, current_streak)

        embed = discord.Embed(
            title=f"🔥 Streak for {handle} 🔥",
            color=discord.Color.orange() if current_streak > 0 else discord.Color.default()
        )
        
        streak_text = f"**{current_streak}** days" if current_streak > 0 else "0 days 😢"
        embed.add_field(name="Current Streak", value=streak_text, inline=True)
        embed.add_field(name="Max Streak", value=f"**{max_streak}** days", inline=True)

        if today_ac:
            embed.set_footer(text="✅ You have already submitted an AC today! Keep it up!")
        elif current_streak > 0:
            embed.set_footer(text="⚠️ You haven't got an AC today! Go solve a problem to keep the streak alive!")
        else:
            embed.set_footer(text="Get an AC today to start your streak!")

        await ctx.send(embed=embed)
        
        # If they just unlocked a badge, let them know!
        if new_badges:
            badge_list = ", ".join(new_badges)
            await ctx.send(f"🎉 **Achievement Unlocked!** {member.mention} just earned: **{badge_list}**! Check `;badges`")

    @streak.command(name='top', aliases=['leaderboard', 'lb'])
    async def streak_top(self, ctx):
        """Shows the server leaderboard for Daily AC Streaks."""
        rows = cf_common.user_db.conn.execute('''
            SELECT user_id, current_streak, max_streak
            FROM user_streak
            WHERE current_streak > 0
            ORDER BY current_streak DESC
        ''').fetchall()

        guild_member_ids = {str(m.id): m for m in ctx.guild.members}
        
        board = []
        for user_id_str, cur, mx in rows:
            if user_id_str in guild_member_ids:
                board.append((guild_member_ids[user_id_str].display_name, cur, mx))

        if not board:
            return await ctx.send("No active streaks found for members of this server! 😢")

        board = board[:10] 

        embed = discord.Embed(title="🔥 Server Streak Leaderboard 🔥", color=discord.Color.red())
        desc = ""
        for i, (name, cur, mx) in enumerate(board, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🏅"
            desc += f"{medal} **{name}** - {cur} days (Max: {mx})\n"
            
        embed.description = desc
        await ctx.send(embed=embed)

    @commands.command(brief='View your earned CP badges')
    async def badges(self, ctx, member: discord.Member = None):
        """Displays the achievement badges you have earned by solving problems."""
        member = member or ctx.author
        handle = cf_common.user_db.get_handle(member.id, ctx.guild.id)
        if not handle:
            return await ctx.send(f"{member.display_name} has not identified their Codeforces handle.")
            
        # Trigger an update to make sure we don't miss any recent unlocks
        await self._update_user_streak(member.id, handle)
        
        rows = cf_common.user_db.conn.execute(
            "SELECT badge_name, awarded_date FROM user_badges WHERE user_id = ?",
            (str(member.id),)
        ).fetchall()
        
        embed = discord.Embed(title=f"🏅 Achievements for {handle}", color=discord.Color.gold())
        if not rows:
            embed.description = "No badges earned yet. Keep practicing to unlock them!"
        else:
            for badge, date in rows:
                embed.add_field(name=badge, value=f"Earned: *{date}*", inline=False)
                
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Streaks(bot))
