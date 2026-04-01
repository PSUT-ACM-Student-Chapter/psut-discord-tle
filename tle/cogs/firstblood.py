import asyncio
import logging
import re

import discord
from discord.ext import commands, tasks

from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

class FirstBlood(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        self.db_ready = asyncio.Event()
        
        # Start the background checker
        self.monitor_task.start()

    async def cog_before_invoke(self, ctx):
        # Prevent any commands in this cog from running until tables are created
        await self.db_ready.wait()

    def _create_tables(self):
        # Table to store which channels are tracking which contests
        cf_common.user_db.conn.execute('''
            CREATE TABLE IF NOT EXISTS first_blood_monitors (
                channel_id TEXT,
                contest_id INTEGER,
                PRIMARY KEY (channel_id, contest_id)
            )
        ''')
        # Table to store the known first bloods so we don't repeat them on bot restarts
        cf_common.user_db.conn.execute('''
            CREATE TABLE IF NOT EXISTS first_blood_winners (
                contest_id INTEGER,
                problem_index TEXT,
                handle TEXT,
                PRIMARY KEY (contest_id, problem_index)
            )
        ''')
        cf_common.user_db.conn.commit()

    def cog_unload(self):
        self.monitor_task.cancel()

    @commands.group(brief='First Blood Broadcast commands', invoke_without_command=True)
    async def firstblood(self, ctx):
        """Commands to manage live First Blood announcements for contests and mashups."""
        await ctx.send_help(ctx.command)

    @firstblood.command(name='track', aliases=['start', 'monitor'])
    async def fb_track(self, ctx, contest_query: str):
        """Starts monitoring a Codeforces contest. You can provide the ID or a full gym/group link."""
        channel_id_str = str(ctx.channel.id)
        
        # Extract ID from URL (e.g. gym/123456 or contest/123456) or parse the number directly
        match = re.search(r'(?:contest|gym)/(\d+)', contest_query)
        if match:
            contest_id = int(match.group(1))
        elif contest_query.isdigit():
            contest_id = int(contest_query)
        else:
            return await ctx.send("❌ Invalid format. Please provide a valid Contest ID or link.")
            
        try:
            cf_common.user_db.conn.execute(
                "INSERT INTO first_blood_monitors (channel_id, contest_id) VALUES (?, ?)",
                (channel_id_str, contest_id)
            )
            cf_common.user_db.conn.commit()
            await ctx.send(f"✅ Now tracking First Bloods for contest `{contest_id}` in this channel.")
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                await ctx.send(f"⚠️ Already tracking contest `{contest_id}` in this channel.")
            else:
                self.logger.error(f"Database error in fb_track: {e}")
                await ctx.send("❌ An error occurred while adding to the database.")

    @firstblood.command(name='untrack', aliases=['stop'])
    async def fb_untrack(self, ctx, contest_query: str):
        """Stops monitoring a Codeforces contest."""
        channel_id_str = str(ctx.channel.id)
        
        match = re.search(r'(?:contest|gym)/(\d+)', contest_query)
        if match:
            contest_id = int(match.group(1))
        elif contest_query.isdigit():
            contest_id = int(contest_query)
        else:
            return await ctx.send("❌ Invalid format. Please provide a valid Contest ID or link.")
            
        res = cf_common.user_db.conn.execute(
            "DELETE FROM first_blood_monitors WHERE channel_id = ? AND contest_id = ?",
            (channel_id_str, contest_id)
        )
        cf_common.user_db.conn.commit()
        
        if res.rowcount > 0:
            await ctx.send(f"🛑 Stopped tracking First Bloods for contest `{contest_id}` in this channel.")
        else:
            await ctx.send(f"⚠️ Not currently tracking contest `{contest_id}` in this channel.")

    @firstblood.command(name='list')
    async def fb_list(self, ctx):
        """Lists all contests currently being monitored for First Bloods in this channel."""
        channel_id_str = str(ctx.channel.id)
        rows = cf_common.user_db.conn.execute(
            "SELECT contest_id FROM first_blood_monitors WHERE channel_id = ?",
            (channel_id_str,)
        ).fetchall()
        
        if not rows:
            return await ctx.send("Not tracking any contests in this channel.")
            
        contests = [str(r[0]) for r in rows]
        await ctx.send(f"📊 Currently tracking First Bloods for contests: {', '.join(contests)}")

    @tasks.loop(seconds=30.0)
    async def monitor_task(self):
        # Fetch all active contest monitors
        rows = cf_common.user_db.conn.execute("SELECT channel_id, contest_id FROM first_blood_monitors").fetchall()
        if not rows:
            return
            
        # Group channels by contest_id to minimize API calls
        contests_to_check = {}
        for channel_id, contest_id in rows:
            if contest_id not in contests_to_check:
                contests_to_check[contest_id] = []
            contests_to_check[contest_id].append(int(channel_id))
            
        for contest_id, channels in contests_to_check.items():
            try:
                # Fetch status for the contest
                submissions = await cf.contest.status(contest_id=contest_id)
                
                # Filter for accepted submissions and sort by creation time
                accepted = [s for s in submissions if s.verdict == 'OK']
                accepted.sort(key=lambda s: s.creationTimeSeconds)
                
                for sub in accepted:
                    p_index = sub.problem.index
                    
                    # Members list can be empty in some rare API responses, safe fallback
                    if not sub.author.members:
                        continue
                    handle = sub.author.members[0].handle
                    
                    # Check if this problem already has a first blood recorded
                    res = cf_common.user_db.conn.execute(
                        "SELECT 1 FROM first_blood_winners WHERE contest_id = ? AND problem_index = ?",
                        (contest_id, p_index)
                    ).fetchone()
                    
                    if not res:
                        # We found a new first blood!
                        embed = discord.Embed(
                            title=f"🩸 First Blood in Contest {contest_id}!",
                            description=f"**{handle}** just solved problem **{p_index}** ({sub.problem.name})",
                            color=discord.Color.red()
                        )
                        embed.add_field(name="Submission", value=f"[Link](https://codeforces.com/contest/{contest_id}/submission/{sub.id})")
                        
                        for channel_id in channels:
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                asyncio.create_task(channel.send(embed=embed))
                                
                        # Save to DB so we don't announce it again
                        cf_common.user_db.conn.execute(
                            "INSERT INTO first_blood_winners (contest_id, problem_index, handle) VALUES (?, ?, ?)",
                            (contest_id, p_index, handle)
                        )
                        cf_common.user_db.conn.commit()
                        
            except cf.CodeforcesApiError as e:
                self.logger.warning(f"CF API Error checking contest {contest_id}: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error checking contest {contest_id}: {e}")
                
            await asyncio.sleep(1.0) # Respect API rate limits

    @monitor_task.before_loop
    async def before_monitor_task(self):
        await self.bot.wait_until_ready()
        # Initialize tables safely after the bot and database connections are ready
        self._create_tables()
        self.db_ready.set()

async def setup(bot):
    await bot.add_cog(FirstBlood(bot))
