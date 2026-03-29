import asyncio
import logging
import time

import discord
from discord.ext import commands, tasks

from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

class UpsolveNudges(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Start the background checker
        self.nudge_task.start()

    def cog_unload(self):
        self.nudge_task.cancel()

    @tasks.loop(hours=12)
    async def nudge_task(self):
        """Runs twice a day to check users' recent failed submissions and remind them to upsolve."""
        self.logger.info("Starting background upsolve nudge check based on submission history...")
        
        # 1. Get registered users who haven't opted out
        users = cf_common.user_db.conn.execute(
            "SELECT DISTINCT user_id, handle FROM user_handle"
        ).fetchall()
        
        optout_rows = cf_common.user_db.conn.execute("SELECT user_id FROM upsolve_optout").fetchall()
        optouts = {r[0] for r in optout_rows}
        active_users = [(uid, handle) for uid, handle in users if str(uid) not in optouts]

        if not active_users:
            self.logger.info("No active users to nudge.")
            return

        # 2. Check recent submissions for each active user
        for user_id, handle in active_users:
            try:
                # Fetch recent 200 submissions
                subs = await cf.user.status(handle=handle, count=200)
            except Exception as e:
                self.logger.warning(f"Failed to fetch standings/status for handle {handle}: {e}")
                continue
                
            solved = set()
            attempted_unsolved = {}
            
            for s in subs:
                # Skip problems without a standard contestId (like some gym problems)
                if not s.problem.contestId:
                    continue
                    
                p_id = f"{s.problem.contestId}-{s.problem.index}"
                
                if s.verdict == 'OK':
                    solved.add(p_id)
                elif s.verdict != 'TESTING':
                    # Record the problem object if we haven't seen it yet
                    if p_id not in attempted_unsolved:
                        attempted_unsolved[p_id] = s.problem
                        
            # Remove any problems the user eventually solved
            for p_id in solved:
                if p_id in attempted_unsolved:
                    del attempted_unsolved[p_id]
                    
            if not attempted_unsolved:
                continue
                
            # 3. Filter out problems we've already nudged them about
            already_nudged_rows = cf_common.user_db.conn.execute(
                "SELECT problem_id FROM upsolve_problem_nudges WHERE user_id = ?",
                (str(user_id),)
            ).fetchall()
            already_nudged = {r[0] for r in already_nudged_rows}
            
            candidates = [p for pid, p in attempted_unsolved.items() if pid not in already_nudged]
            
            if not candidates:
                continue
                
            # 4. Pick the easiest unsolved problem based on rating (fallback to 9999 if no rating)
            candidates.sort(key=lambda p: getattr(p, 'rating', 9999))
            missed_problem = candidates[0]
            missed_p_id = f"{missed_problem.contestId}-{missed_problem.index}"
            
            # 5. Send the DM Reminder
            user_obj = self.bot.get_user(int(user_id))
            if user_obj:
                try:
                    embed = discord.Embed(
                        title=f"🧠 Upsolve Reminder: Finish What You Started!",
                        description=(
                            f"Hey **{handle}**!\n\n"
                            f"I noticed you attempted **Problem {missed_problem.index} - {missed_problem.name}** "
                            f"but haven't gotten it 'Accepted' yet. "
                            f"Reviewing problems you struggled with is the fastest way to gain rating. Time to finish it!"
                        ),
                        color=discord.Color.blue()
                    )
                    embed.add_field(
                        name="Problem Link", 
                        value=f"https://codeforces.com/contest/{missed_problem.contestId}/problem/{missed_problem.index}"
                    )
                    embed.set_footer(text="Use `;upsolve toggle` in the server to disable these automated DMs.")
                    
                    await user_obj.send(embed=embed)
                    
                    # Record that we successfully nudged them
                    cf_common.user_db.conn.execute(
                        "INSERT INTO upsolve_problem_nudges (user_id, problem_id) VALUES (?, ?)",
                        (str(user_id), missed_p_id)
                    )
                    cf_common.user_db.conn.commit()
                    
                except discord.Forbidden:
                    # The bot cannot DM this user (privacy settings). Opt them out automatically.
                    self.logger.info(f"Cannot DM {handle}. Auto-opting out.")
                    cf_common.user_db.conn.execute(
                        "INSERT OR IGNORE INTO upsolve_optout (user_id) VALUES (?)",
                        (str(user_id),)
                    )
                    cf_common.user_db.conn.commit()
                    
            await asyncio.sleep(1) # Be nice to the API rate limits

        self.logger.info("Upsolve nudge check complete.")

    @nudge_task.before_loop
    async def before_nudge_task(self):
        await self.bot.wait_until_ready()
        
        # Safely initialize the tracking tables in the SQLite DB
        # upsolve_problem_nudges prevents us from spamming the user multiple times for the same problem
        cf_common.user_db.conn.execute('''
            CREATE TABLE IF NOT EXISTS upsolve_problem_nudges (
                user_id TEXT,
                problem_id TEXT,
                PRIMARY KEY (user_id, problem_id)
            )
        ''')
        # upsolve_optout allows users to disable the feature for themselves
        cf_common.user_db.conn.execute('''
            CREATE TABLE IF NOT EXISTS upsolve_optout (
                user_id TEXT PRIMARY KEY
            )
        ''')
        cf_common.user_db.conn.commit()

    @commands.group(brief='Automated upsolve reminders', invoke_without_command=True)
    async def upsolve(self, ctx):
        """Commands related to the automated upsolving reminders."""
        await ctx.send_help(ctx.command)

    @upsolve.command(name='toggle', brief='Enable or disable upsolve DMs')
    async def upsolve_toggle(self, ctx):
        """Toggles whether the bot will send you DMs reminding you to upsolve missed problems."""
        user_id_str = str(ctx.author.id)
        
        is_opted_out = cf_common.user_db.conn.execute(
            "SELECT 1 FROM upsolve_optout WHERE user_id = ?", 
            (user_id_str,)
        ).fetchone()

        if is_opted_out:
            cf_common.user_db.conn.execute(
                "DELETE FROM upsolve_optout WHERE user_id = ?", 
                (user_id_str,)
            )
            cf_common.user_db.conn.commit()
            await ctx.send(f"✅ {ctx.author.mention}, you will now receive upsolve reminders via DM!")
        else:
            cf_common.user_db.conn.execute(
                "INSERT INTO upsolve_optout (user_id) VALUES (?)", 
                (user_id_str,)
            )
            cf_common.user_db.conn.commit()
            await ctx.send(f"🛑 {ctx.author.mention}, you have opted out of upsolve reminders.")

async def setup(bot):
    await bot.add_cog(UpsolveNudges(bot))
