import asyncio
import datetime
import logging
import math

import discord
from discord.ext import commands, tasks

from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

BADGE_DESCRIPTIONS = {
    'Night Owl 🦇': 'Submitted an Accepted solution between 2 AM and 5 AM UTC.',
    'Speed Demon ⚡': 'Solved problem A in under 5 minutes during a contest.',
    'Necromancer 🧟': 'Solved a problem published over 5 years ago.',
    'Sniper 🎯': 'Achieved 5 Accepted submissions in a row with no Wrong Answers.',
    'Early Bird 🌅': 'Submitted an Accepted solution between 5 AM and 8 AM UTC.',
    'Persistent 😤': 'Got an Accepted solution after 5+ failures on the same problem.',
    'Math Whiz 🧮': 'Solved a problem with the "math" tag.',
    'Graph Master 🕸️': 'Solved a problem with the "graphs" or "trees" tag.',
    'Prime 🔢': 'Got an Accepted solution on a prime numbered submission ID.',
    'Polyglot 🗣️': 'Got Accepted solutions in 3 or more different programming languages recently.'
}

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
        
        # Start the background checker
        self.update_streaks_task.start()

    def cog_unload(self):
        self.update_streaks_task.cancel()

    def _ensure_tables(self):
        """Safely creates tables if they don't exist yet right before they are needed."""
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

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc))
    async def update_streaks_task(self):
        """Runs daily at midnight UTC to process streaks and badges for all registered users."""
        self.logger.info("Starting daily streak & badge background update...")
        self._ensure_tables()
        try:
            users = cf_common.user_db.conn.execute(
                "SELECT DISTINCT user_id, handle FROM user_handle"
            ).fetchall()
        except Exception as e:
            self.logger.error(f"Failed to fetch users from DB: {e}")
            return

        for user_id_int, handle in users:
            await self._update_user_streak(user_id_int, handle, force_api_call=True)
            await asyncio.sleep(0.5) 

        self.logger.info("Daily streak & badge update completed successfully.")

    @update_streaks_task.before_loop
    async def before_update_streaks_task(self):
        await self.bot.wait_until_ready()

    async def _update_user_streak(self, user_id_int, handle, force_api_call=False):
        """Calculates streak by counting backwards through unique AC dates."""
        self._ensure_tables()
        user_id_str = str(user_id_int)
        
        row = cf_common.user_db.conn.execute(
            "SELECT current_streak, max_streak, last_ac_date FROM user_streak WHERE user_id = ?",
            (user_id_str,)
        ).fetchone()

        db_current_streak = row[0] if row else 0
        db_max_streak = row[1] if row else 0
        db_last_ac_date = row[2] if row else None
        
        now = datetime.datetime.now(datetime.timezone.utc)
        today_date = now.date()
        yesterday_date = today_date - datetime.timedelta(days=1)
        today_str = today_date.strftime('%Y-%m-%d')

        # Cache optimization
        if not force_api_call and db_last_ac_date == today_str:
            return db_current_streak, db_max_streak, True, []

        try:
            # We fetch more submissions (up to 1000) to accurately reconstruct long streaks
            subs = await cf.user.status(handle=handle, count=1000)
        except Exception as e:
            self.logger.warning(f"Failed to fetch CF status for {handle}: {e}")
            return db_current_streak, db_max_streak, (db_last_ac_date == today_str), []

        # Map unique AC dates
        ac_dates_set = set()
        for s in subs:
            if s.verdict == 'OK':
                dt = datetime.datetime.fromtimestamp(s.creationTimeSeconds, datetime.timezone.utc).date()
                ac_dates_set.add(dt)

        # 1. CALCULATE CURRENT STREAK BY COUNTING BACKWARDS
        calc_streak = 0
        check_date = today_date
        
        # If no AC today, check if the streak was alive yesterday
        if today_date not in ac_dates_set:
            if yesterday_date in ac_dates_set:
                check_date = yesterday_date
            else:
                calc_streak = 0 # Streak is dead
                check_date = None

        if check_date:
            while check_date in ac_dates_set:
                calc_streak += 1
                check_date -= datetime.timedelta(days=1)

        # Update last_ac_date based on found ACs
        new_last_ac_date = db_last_ac_date
        if today_date in ac_dates_set:
            new_last_ac_date = today_str
        elif yesterday_date in ac_dates_set and (db_last_ac_date != today_str):
            new_last_ac_date = yesterday_date.strftime('%Y-%m-%d')

        new_max_streak = max(db_max_streak, calc_streak)

        cf_common.user_db.conn.execute('''
            INSERT INTO user_streak (user_id, current_streak, max_streak, last_ac_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
            current_streak=excluded.current_streak,
            max_streak=excluded.max_streak,
            last_ac_date=excluded.last_ac_date
        ''', (user_id_str, calc_streak, new_max_streak, new_last_ac_date))
        
        # 2. BADGE LOGIC (Iterate submissions chronologically)
        existing_badges = {
            r[0] for r in cf_common.user_db.conn.execute(
                "SELECT badge_name FROM user_badges WHERE user_id = ?", (user_id_str,)
            ).fetchall()
        }
        new_badges = []
        
        subs_chronological = sorted(subs, key=lambda x: x.creationTimeSeconds)
        consecutive_acs = 0
        problem_fails = {}
        ac_languages = set()
        
        for s in subs_chronological:
            if s.verdict == 'TESTING': continue
            problem_id = f"{s.problem.contestId}{s.problem.index}"
            if s.verdict == 'OK':
                consecutive_acs += 1
                dt = datetime.datetime.fromtimestamp(s.creationTimeSeconds, datetime.timezone.utc)
                
                # Language tracking
                if getattr(s, 'programmingLanguage', None):
                    lang = s.programmingLanguage.lower()
                    if 'c++' in lang: ac_languages.add('c++')
                    elif 'python' in lang or 'pypy' in lang: ac_languages.add('python')
                    elif 'java' in lang and 'javascript' not in lang: ac_languages.add('java')
                    else: ac_languages.add(lang)
                
                # Time-based & complexity badges
                if 'Night Owl 🦇' not in existing_badges and 2 <= dt.hour < 5:
                    new_badges.append('Night Owl 🦇')
                    existing_badges.add('Night Owl 🦇')
                if 'Early Bird 🌅' not in existing_badges and 5 <= dt.hour < 8:
                    new_badges.append('Early Bird 🌅')
                    existing_badges.add('Early Bird 🌅')
                if 'Speed Demon ⚡' not in existing_badges and s.author.participantType == 'CONTESTANT':
                    if getattr(s, 'relativeTimeSeconds', 9999) <= 300 and s.problem.index.startswith('A'):
                        new_badges.append('Speed Demon ⚡')
                        existing_badges.add('Speed Demon ⚡')
                if 'Sniper 🎯' not in existing_badges and consecutive_acs >= 5:
                    new_badges.append('Sniper 🎯')
                    existing_badges.add('Sniper 🎯')
                if 'Persistent 😤' not in existing_badges and problem_fails.get(problem_id, 0) >= 5:
                    new_badges.append('Persistent 😤')
                    existing_badges.add('Persistent 😤')
                if 'Math Whiz 🧮' not in existing_badges and s.problem.tags and 'math' in s.problem.tags:
                    new_badges.append('Math Whiz 🧮')
                    existing_badges.add('Math Whiz 🧮')
                if 'Prime 🔢' not in existing_badges and getattr(s, 'id', None) and is_prime(s.id):
                    new_badges.append('Prime 🔢')
                    existing_badges.add('Prime 🔢')
            else:
                consecutive_acs = 0
                problem_fails[problem_id] = problem_fails.get(problem_id, 0) + 1

        if 'Polyglot 🗣️' not in existing_badges and len(ac_languages) >= 3:
            new_badges.append('Polyglot 🗣️')
            existing_badges.add('Polyglot 🗣️')

        # Powers of 2 Streak Badge
        if new_max_streak > 0:
            highest_pow2 = 1 << (new_max_streak.bit_length() - 1)
            streak_badge_name = f"Streak 🔥: {highest_pow2} Days"
            if streak_badge_name not in existing_badges:
                cf_common.user_db.conn.execute("DELETE FROM user_badges WHERE user_id = ? AND badge_name LIKE 'Streak 🔥: %'", (user_id_str,))
                new_badges.append(streak_badge_name)
                existing_badges.add(streak_badge_name)

        # Save new badges
        award_date = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
        for badge in new_badges:
            cf_common.user_db.conn.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_name, awarded_date) VALUES (?, ?, ?)", (user_id_str, badge, award_date))
        cf_common.user_db.conn.commit()

        return calc_streak, new_max_streak, (today_date in ac_dates_set), new_badges

    @commands.group(brief='Daily AC Streak commands', invoke_without_command=True)
    async def streak(self, ctx, member: discord.Member = None):
        """Shows your current consecutive days of solving Codeforces problems."""
        member = member or ctx.author
        handle = cf_common.user_db.get_handle(member.id, ctx.guild.id)
        if not handle:
            return await ctx.send(f"{member.display_name} has not identified their Codeforces handle. Use `;handle set`.")

        async with ctx.typing():
            current_streak, max_streak, today_ac, new_badges = await self._update_user_streak(member.id, handle)

        embed = discord.Embed(
            title=f"🔥 Streak for {handle} 🔥",
            color=discord.Color.orange() if current_streak > 0 else discord.Color.light_grey()
        )
        
        embed.add_field(name="Current Streak", value=f"**{current_streak}** days", inline=True)
        embed.add_field(name="Max Streak", value=f"**{max_streak}** days", inline=True)

        if today_ac:
            embed.set_footer(text="✅ AC submitted today! Keep it up!")
        elif current_streak > 0:
            embed.set_footer(text="⚠️ Solve a problem today to keep the streak alive!")
        else:
            embed.set_footer(text="Get an AC today to start your streak!")

        await ctx.send(embed=embed)
        if new_badges:
            await ctx.send(f"🎉 **Achievement Unlocked!** {member.mention} earned: **{', '.join(new_badges)}**!")

    @streak.command(name='update')
    async def streak_update(self, ctx):
        """Forces a full refresh from Codeforces."""
        handle = cf_common.user_db.get_handle(ctx.author.id, ctx.guild.id)
        if not handle: return await ctx.send("Handle not set.")
        await ctx.send("🔄 Re-calculating full history...")
        await self._update_user_streak(ctx.author.id, handle, force_api_call=True)
        await self.streak(ctx, ctx.author)

    @streak.command(name='top', aliases=['lb'])
    async def streak_top(self, ctx):
        """Leaderboard for current active streaks."""
        self._ensure_tables()
        rows = cf_common.user_db.conn.execute('SELECT user_id, current_streak, max_streak FROM user_streak WHERE current_streak > 0 ORDER BY current_streak DESC').fetchall()
        guild_member_ids = {str(m.id): m for m in ctx.guild.members}
        board = []
        for uid, cur, mx in rows:
            if uid in guild_member_ids:
                board.append((guild_member_ids[uid].display_name, cur, mx))

        if not board: return await ctx.send("No active streaks found.")
        embed = discord.Embed(title="🔥 Server Streak Leaderboard 🔥", color=discord.Color.red())
        embed.description = "\n".join([f"{'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else '🏅'} **{n}** - {c} days (Max: {m})" for i, (n, c, m) in enumerate(board[:10])])
        await ctx.send(embed=embed)

    @commands.command(brief='View your earned CP badges')
    async def badges(self, ctx, member: discord.Member = None):
        """Displays achievement badges with descriptions."""
        self._ensure_tables()
        member = member or ctx.author
        handle = cf_common.user_db.get_handle(member.id, ctx.guild.id)
        if not handle: return await ctx.send(f"{member.display_name} has no handle set.")
            
        async with ctx.typing():
            _, _, _, new_badges = await self._update_user_streak(member.id, handle, force_api_call=True)
            if new_badges: await ctx.send(f"🎉 **Achievement Unlocked!** {member.mention} earned: **{', '.join(new_badges)}**!")

            rows = cf_common.user_db.conn.execute("SELECT badge_name, awarded_date FROM user_badges WHERE user_id = ? ORDER BY awarded_date DESC", (str(member.id),)).fetchall()
            
        embed = discord.Embed(title=f"🏅 Achievements for {handle}", color=discord.Color.gold())
        if not rows:
            embed.description = "No badges earned yet."
        else:
            for badge, date in rows:
                desc = "Maintained a consistent daily AC streak." if badge.startswith("Streak") else BADGE_DESCRIPTIONS.get(badge, "Special achievement.")
                embed.add_field(name=badge, value=f"{desc}\n*Earned: {date}*", inline=False)
                
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Streaks(bot))
