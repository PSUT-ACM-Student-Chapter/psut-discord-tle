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
        
        # Start the background checker
        self.monitor_task.start()

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
            return await ctx.send("❌ Invalid format. Please provide a valid contest ID or Codeforces URL.")
        
        # Check if already tracking
        existing = cf_common.user_db.conn.execute(
            "SELECT 1 FROM first_blood_monitors WHERE channel_id = ? AND contest_id = ?", 
            (channel_id_str, contest_id)
        ).fetchone()
        
        if existing:
            return await ctx.send(f"⚠️ Already tracking contest {contest_id} in this channel!")

        unofficial = contest_id >= 100000 # Include unofficial participants for Mashups
        
        msg = await ctx.send(f"⏳ Verifying contest {contest_id}...")
        
        try:
            contest, problems, rows = await cf.contest.standings(contestId=contest_id, showUnofficial=unofficial)
            
            # Pre-populate already solved problems silently so we don't spam them
            best_times = {}
            for row in rows:
                if not row.party.members: continue
                handle = row.party.members[0].handle
                for i, result in enumerate(row.problemResults):
                    time = getattr(result, 'bestSubmissionTimeSeconds', None)
                    if time is not None:
                        p_index = problems[i].index
                        if p_index not in best_times or time < best_times[p_index][0]:
                            best_times[p_index] = (time, handle)
                            
            for p_index, (time, handle) in best_times.items():
                cf_common.user_db.conn.execute(
                    "INSERT OR IGNORE INTO first_blood_winners (contest_id, problem_index, handle) VALUES (?, ?, ?)",
                    (contest_id, p_index, handle)
                )

        except Exception as e:
            error_msg = str(e).lower()
            if "not started" in error_msg or "hasn't started" in error_msg:
                pass # This is fine! We can queue tracking before the contest begins.
            elif "forbidden" in error_msg or "not found" in error_msg:
                return await msg.edit(
                    content=f"❌ Failed to fetch contest {contest_id}.\n"
                            f"**Note for Private Mashups/Gyms:** The Codeforces account used by this bot's API Key **MUST** be invited as a member/manager to the private Codeforces group for the bot to see the standings!"
                )
            else:
                return await msg.edit(content=f"❌ Failed to fetch contest {contest_id}: {e}")

        # Add to tracking monitors
        cf_common.user_db.conn.execute(
            "INSERT INTO first_blood_monitors (channel_id, contest_id) VALUES (?, ?)", 
            (channel_id_str, contest_id)
        )
        cf_common.user_db.conn.commit()
        
        embed = discord.Embed(
            title="🩸 First Blood Tracking Started! 🩸",
            description=f"Now monitoring **Contest {contest_id}**.\nWhenever someone is the first to solve a problem, it will be announced here!",
            color=discord.Color.red()
        )
        await msg.edit(content=None, embed=embed)

    @firstblood.command(name='untrack', aliases=['stop'])
    async def fb_untrack(self, ctx, contest_id: int):
        """Stops monitoring a contest in the current channel."""
        channel_id_str = str(ctx.channel.id)
        deleted = cf_common.user_db.conn.execute(
            "DELETE FROM first_blood_monitors WHERE channel_id = ? AND contest_id = ?", 
            (channel_id_str, contest_id)
        ).rowcount
        cf_common.user_db.conn.commit()
        
        if deleted:
            await ctx.send(f"🛑 Stopped tracking contest {contest_id} in this channel.")
        else:
            await ctx.send(f"⚠️ Not currently tracking contest {contest_id} here.")

    @firstblood.command(name='list')
    async def fb_list(self, ctx):
        """Lists all contests currently being monitored in this channel."""
        channel_id_str = str(ctx.channel.id)
        rows = cf_common.user_db.conn.execute(
            "SELECT contest_id FROM first_blood_monitors WHERE channel_id = ?", 
            (channel_id_str,)
        ).fetchall()
        
        if not rows:
            return await ctx.send("Not currently tracking any contests in this channel.")
            
        contests = ", ".join([str(r[0]) for r in rows])
        await ctx.send(f"📡 Currently tracking First Bloods for contests: **{contests}**")

    @tasks.loop(seconds=60.0)
    async def monitor_task(self):
        """Background task checking standings for newly solved problems."""
        # Gather all active monitors
        try:
            monitors = cf_common.user_db.conn.execute("SELECT channel_id, contest_id FROM first_blood_monitors").fetchall()
        except Exception:
            return
            
        if not monitors:
            return

        # Group by contest_id to minimize CF API calls
        contest_to_channels = {}
        for ch_id, c_id in monitors:
            contest_to_channels.setdefault(c_id, []).append(int(ch_id))

        for contest_id, channels in contest_to_channels.items():
            unofficial = contest_id >= 100000
            
            try:
                contest, problems, rows = await cf.contest.standings(contestId=contest_id, showUnofficial=unofficial)
            except Exception as e:
                self.logger.warning(f"FirstBlood monitor failed for {contest_id}: {e}")
                continue
                
            # If contest is finished, auto-untrack it to save API limits
            if contest.phase == 'FINISHED':
                cf_common.user_db.conn.execute("DELETE FROM first_blood_monitors WHERE contest_id = ?", (contest_id,))
                cf_common.user_db.conn.commit()
                self.logger.info(f"Contest {contest_id} finished. Untracked from all channels.")
                continue

            # Calculate current best times
            best_times = {}
            for row in rows:
                if not row.party.members: continue
                handle = row.party.members[0].handle
                for i, result in enumerate(row.problemResults):
                    time = getattr(result, 'bestSubmissionTimeSeconds', None)
                    if time is not None:
                        p_index = problems[i].index
                        p_name = problems[i].name
                        if p_index not in best_times or time < best_times[p_index]['time']:
                            best_times[p_index] = {'time': time, 'handle': handle, 'name': p_name}

            # Fetch existing recorded winners from DB
            existing_rows = cf_common.user_db.conn.execute(
                "SELECT problem_index FROM first_blood_winners WHERE contest_id = ?", 
                (contest_id,)
            ).fetchall()
            existing_indexes = {r[0] for r in existing_rows}

            # Determine if this is the very first solve of the entire contest
            first_overall_index = None
            if len(existing_indexes) == 0 and best_times:
                # Find the problem index with the absolute minimum solving time
                first_overall_index = min(best_times, key=lambda k: best_times[k]['time'])

            # Broadcast new first bloods!
            for p_index, data in best_times.items():
                if p_index not in existing_indexes:
                    handle = data['handle']
                    p_name = data['name']
                    
                    # Try to map the handle to a Discord User ID to ping them
                    user_row = cf_common.user_db.conn.execute(
                        "SELECT user_id FROM user_handle WHERE handle = ? COLLATE NOCASE", 
                        (handle,)
                    ).fetchone()
                    
                    display_name = f"<@{user_row[0]}>" if user_row else f"**{handle}**"
                    
                    # ICPC Balloon Logic
                    if p_index == first_overall_index:
                        balloons = "🎈🎈🎈"
                        title_prefix = "OVERALL FIRST BLOOD"
                    else:
                        balloons = "🎈🎈"
                        title_prefix = "FIRST BLOOD"
                    
                    embed = discord.Embed(
                        title=f"{balloons} {title_prefix}: Problem {p_index} {balloons}",
                        description=f"{display_name} just drew First Blood on **[{p_index}] {p_name}**!\n\n*(Contest {contest_id})*",
                        color=discord.Color.red()
                    )
                    
                    for ch_id in channels:
                        channel = self.bot.get_channel(ch_id)
                        if channel:
                            asyncio.create_task(channel.send(embed=embed))
                            
                    # Save to DB so we don't announce it again
                    cf_common.user_db.conn.execute(
                        "INSERT INTO first_blood_winners (contest_id, problem_index, handle) VALUES (?, ?, ?)",
                        (contest_id, p_index, handle)
                    )
                    cf_common.user_db.conn.commit()
                    
            await asyncio.sleep(1.0) # Respect API rate limits

    @monitor_task.before_loop
    async def before_monitor_task(self):
        await self.bot.wait_until_ready()
        
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

async def setup(bot):
    await bot.add_cog(FirstBlood(bot))
