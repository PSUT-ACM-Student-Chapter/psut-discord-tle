import asyncio
import datetime
import logging
import math

import discord
from discord.ext import commands, tasks

from tle import constants
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
        """Safely creates and migrates tables for incremental updates."""
        cf_common.user_db.conn.execute('''
            CREATE TABLE IF NOT EXISTS user_streak (
                user_id TEXT PRIMARY KEY,
                current_streak INTEGER DEFAULT 0,
                max_streak INTEGER DEFAULT 0,
                last_ac_date TEXT,
                last_id INTEGER DEFAULT 0
            )
        ''')
        
        # Add last_id column if it doesn't exist (migration)
        try:
            cf_common.user_db.conn.execute('ALTER TABLE user_streak ADD COLUMN last_id INTEGER DEFAULT 0')
        except:
            pass

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
            # Incrementally sync everyone. Bootstraps entirely if they've never been scanned.
            await self._update_user_streak(user_id_int, handle)
            await asyncio.sleep(0.5) 

        self.logger.info("Daily streak & badge update completed successfully.")

    @update_streaks_task.before_loop
    async def before_update_streaks_task(self):
        await self.bot.wait_until_ready()

    async def _update_user_streak(self, user_id_int, handle, force_refresh=False):
        """
        Increments the saved streak by only processing new submissions.
        If no record exists (last_id=0), it fetches the FULL history to bootstrap exact stats.
        """
        self._ensure_tables()
        user_id_str = str(user_id_int)
        
        row = cf_common.user_db.conn.execute(
            "SELECT current_streak, max_streak, last_ac_date, last_id FROM user_streak WHERE user_id = ?",
            (user_id_str,)
        ).fetchone()

        curr_streak = row[0] if row else 0
        max_streak = row[1] if row else 0
        last_ac_date_str = row[2] if row else None
        last_processed_id = row[3] if row else 0
        
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        today = now_utc.date()
        yesterday = today - datetime.timedelta(days=1)

        # Optimization: If we already updated today and aren't forcing, skip API call
        if not force_refresh and last_ac_date_str == today.strftime('%Y-%m-%d'):
            return curr_streak, max_streak, True, []

        is_full_history = (last_processed_id == 0)

        try:
            if is_full_history:
                # Bootstrapping: Fetch the entire submission history (omitting count)
                subs = await cf.user.status(handle=handle)
            else:
                # Incremental Update: Fetch a recent slice
                subs = await cf.user.status(handle=handle, count=100)
        except Exception as e:
            self.logger.warning(f"Failed to fetch CF status for {handle}: {e}")
            return curr_streak, max_streak, (last_ac_date_str == today.strftime('%Y-%m-%d')), []

        # Filter for NEW submissions only
        new_subs = [s for s in subs if getattr(s, 'id', 0) > last_processed_id]

        if not new_subs and not is_full_history:
            # No new activity. Check if the existing streak is now dead.
            if last_ac_date_str:
                last_date = datetime.datetime.strptime(last_ac_date_str, '%Y-%m-%d').date()
                if today > last_date + datetime.timedelta(days=1):
                    curr_streak = 0
                    cf_common.user_db.conn.execute(
                        "UPDATE user_streak SET current_streak = 0 WHERE user_id = ?", (user_id_str,)
                    )
                    cf_common.user_db.conn.commit()
            return curr_streak, max_streak, False, []

        # Determine target submissions (entire history if fresh, or just new subs)
        subs_to_process = sorted(subs if is_full_history else new_subs, key=lambda x: x.creationTimeSeconds)

        # -------------------------------------------------------------
        # STREAK CALCULATION
        # -------------------------------------------------------------
        ac_dates = sorted(list(set(
            datetime.datetime.fromtimestamp(s.creationTimeSeconds, datetime.timezone.utc).date()
            for s in subs_to_process if s.verdict == 'OK'
        )))

        if is_full_history:
            # Complete recalculation from start of time
            calc_streak = 0
            calc_max_streak = 0
            last_date = None
            
            for d in ac_dates:
                if last_date is None:
                    calc_streak = 1
                elif d == last_date + datetime.timedelta(days=1):
                    calc_streak += 1
                elif d > last_date + datetime.timedelta(days=1):
                    calc_streak = 1
                    
                if calc_streak > calc_max_streak:
                    calc_max_streak = calc_streak
                last_date = d
                
            # If they haven't solved a problem since before yesterday, current streak is dead
            if last_date and last_date < yesterday:
                calc_streak = 0
                
            curr_streak = calc_streak
            max_streak = calc_max_streak
            if last_date:
                last_ac_date_str = last_date.strftime('%Y-%m-%d')
        else:
            # Incremental mapping atop the existing streak state
            last_date = datetime.datetime.strptime(last_ac_date_str, '%Y-%m-%d').date() if last_ac_date_str else None
            
            for d in ac_dates:
                if last_date is None:
                    curr_streak = 1
                elif d == last_date + datetime.timedelta(days=1):
                    curr_streak += 1
                elif d > last_date + datetime.timedelta(days=1):
                    curr_streak = 1
                # If d == last_date, do nothing (same day)
                    
                if curr_streak > max_streak:
                    max_streak = curr_streak
                last_date = d
                
            if last_date and last_date < yesterday:
                curr_streak = 0
                
            if last_date:
                last_ac_date_str = last_date.strftime('%Y-%m-%d')


        # -------------------------------------------------------------
        # BADGE CALCULATION 
        # -------------------------------------------------------------
        existing_badges = {
            r[0] for r in cf_common.user_db.conn.execute(
                "SELECT badge_name FROM user_badges WHERE user_id = ?", (user_id_str,)
            ).fetchall()
        }
        new_badges_awarded = []
        
        consecutive_acs = 0 
        problem_fails = {}
        ac_languages = set()

        for s in subs_to_process:
            if s.verdict == 'TESTING': continue
            
            p_id = f"{s.problem.contestId}{s.problem.index}"
            dt = datetime.datetime.fromtimestamp(s.creationTimeSeconds, datetime.timezone.utc)

            if s.verdict == 'OK':
                consecutive_acs += 1
                
                if getattr(s, 'programmingLanguage', None):
                    lang = s.programmingLanguage.lower()
                    if 'c++' in lang: ac_languages.add('c++')
                    elif 'python' in lang or 'pypy' in lang: ac_languages.add('python')
                    elif 'java' in lang and 'javascript' not in lang: ac_languages.add('java')
                    else: ac_languages.add(lang)

                # Badge Logic Execution
                if 'Night Owl 🦇' not in existing_badges and 2 <= dt.hour < 5:
                    new_badges_awarded.append('Night Owl 🦇'); existing_badges.add('Night Owl 🦇')
                if 'Early Bird 🌅' not in existing_badges and 5 <= dt.hour < 8:
                    new_badges_awarded.append('Early Bird 🌅'); existing_badges.add('Early Bird 🌅')
                if 'Speed Demon ⚡' not in existing_badges and s.author.participantType == 'CONTESTANT':
                    if getattr(s, 'relativeTimeSeconds', 9999) <= 300 and s.problem.index.startswith('A'):
                        new_badges_awarded.append('Speed Demon ⚡'); existing_badges.add('Speed Demon ⚡')
                if 'Sniper 🎯' not in existing_badges and consecutive_acs >= 5:
                    new_badges_awarded.append('Sniper 🎯'); existing_badges.add('Sniper 🎯')
                if 'Persistent 😤' not in existing_badges and problem_fails.get(p_id, 0) >= 5:
                    new_badges_awarded.append('Persistent 😤'); existing_badges.add('Persistent 😤')
                if 'Math Whiz 🧮' not in existing_badges and s.problem.tags and 'math' in s.problem.tags:
                    new_badges_awarded.append('Math Whiz 🧮'); existing_badges.add('Math Whiz 🧮')
                if 'Prime 🔢' not in existing_badges and getattr(s, 'id', None) and is_prime(s.id):
                    new_badges_awarded.append('Prime 🔢'); existing_badges.add('Prime 🔢')
            else:
                consecutive_acs = 0
                problem_fails[p_id] = problem_fails.get(p_id, 0) + 1

        # Calculate final state badges
        if 'Polyglot 🗣️' not in existing_badges and len(ac_languages) >= 3:
            new_badges_awarded.append('Polyglot 🗣️')
            existing_badges.add('Polyglot 🗣️')

        if max_streak > 0:
            highest_pow2 = 1 << (max_streak.bit_length() - 1)
            streak_badge_name = f"Streak 🔥: {highest_pow2} Days"
            if streak_badge_name not in existing_badges:
                cf_common.user_db.conn.execute("DELETE FROM user_badges WHERE user_id = ? AND badge_name LIKE 'Streak 🔥: %'", (user_id_str,))
                new_badges_awarded.append(streak_badge_name)

        # Update last_id cursor
        new_last_id = max([getattr(s, 'id', 0) for s in subs_to_process] + [last_processed_id]) if subs_to_process else last_processed_id

        # Database Commits
        cf_common.user_db.conn.execute('''
            INSERT INTO user_streak (user_id, current_streak, max_streak, last_ac_date, last_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
            current_streak=excluded.current_streak,
            max_streak=excluded.max_streak,
            last_ac_date=excluded.last_ac_date,
            last_id=excluded.last_id
        ''', (user_id_str, curr_streak, max_streak, last_ac_date_str, new_last_id))

        award_date = today.strftime('%Y-%m-%d')
        for b in new_badges_awarded:
            cf_common.user_db.conn.execute(
                "INSERT OR IGNORE INTO user_badges (user_id, badge_name, awarded_date) VALUES (?, ?, ?)",
                (user_id_str, b, award_date)
            )
        
        cf_common.user_db.conn.commit()
        
        today_ac = (last_ac_date_str == today.strftime('%Y-%m-%d'))
        return curr_streak, max_streak, today_ac, new_badges_awarded

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
    @commands.has_role(constants.TLE_ADMIN)
    async def streak_update(self, ctx):
        """Forces a hard reset and recalculates your streak from your complete history."""
        handle = cf_common.user_db.get_handle(ctx.author.id, ctx.guild.id)
        if not handle: return await ctx.send("Handle not set.")
        
        await ctx.send("🔄 Fetching your complete history and completely recalculating stats... This might take a moment!")
        
        # Reset last_id to force the script into `is_full_history` mode.
        cf_common.user_db.conn.execute("UPDATE user_streak SET last_id = 0 WHERE user_id = ?", (str(ctx.author.id),))
        cf_common.user_db.conn.commit()
        
        await self._update_user_streak(ctx.author.id, handle, force_refresh=True)
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
        """Displays achievement badges from the database."""
        self._ensure_tables()
        member = member or ctx.author
        handle = cf_common.user_db.get_handle(member.id, ctx.guild.id)
        if not handle: return await ctx.send(f"{member.display_name} has no handle set.")
            
        async with ctx.typing():
            # Quick sync to see if there are missing badges.
            _, _, _, new_badges = await self._update_user_streak(member.id, handle)
            if new_badges: await ctx.send(f"🎉 **Achievement Unlocked!** {member.mention} earned: **{', '.join(new_badges)}**!")

            rows = cf_common.user_db.conn.execute(
                "SELECT badge_name, awarded_date FROM user_badges WHERE user_id = ? ORDER BY awarded_date DESC", 
                (str(member.id),)
            ).fetchall()
            
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
