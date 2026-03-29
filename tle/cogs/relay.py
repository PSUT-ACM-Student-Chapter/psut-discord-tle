import asyncio
import logging
import random
import time

import discord
from discord.ext import commands, tasks

from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

class RelayMatch:
    def __init__(self, ctx, size, base_rating):
        self.ctx = ctx
        self.size = size
        self.base_rating = base_rating
        
        self.team1 = [] # Discord User Objects
        self.team2 = []
        self.team1_handles = []
        self.team2_handles = []
        
        self.problems = [] # List of Problem objects
        self.active = False
        self.t1_progress = 0 # Index of the current problem/player
        self.t2_progress = 0
        self.start_time = 0

class TeamRelay(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        self.matches = {} # Mapping from channel ID to RelayMatch
        self.relay_check_task.start()

    def cog_unload(self):
        self.relay_check_task.cancel()

    @commands.group(brief='Team Relay Duel commands', invoke_without_command=True)
    async def relay(self, ctx):
        """Commands to start and manage Team Relay races."""
        await ctx.send_help(ctx.command)

    @relay.command(name='challenge', aliases=['create'])
    async def relay_challenge(self, ctx, size: int, base_rating: int):
        """Creates a Relay Race lobby. e.g., ;relay challenge 2 1200
        Size must be 2 or 3.
        Problems will increment by 300 rating (e.g., 1200, 1500, 1800).
        """
        if size not in [2, 3]:
            return await ctx.send("Relay size must be 2 or 3 (for 2v2 or 3v3 races).")
        if base_rating % 100 != 0 or base_rating < 800 or base_rating > 3000:
            return await ctx.send("Base rating must be a multiple of 100 between 800 and 3000.")
            
        if ctx.channel.id in self.matches:
            return await ctx.send("A relay match is already active or forming in this channel.")

        self.matches[ctx.channel.id] = RelayMatch(ctx, size, base_rating)
        
        embed = discord.Embed(
            title=f"🏁 {size}v{size} Team Relay Race!",
            description=(
                f"**Base Rating:** {base_rating}\n"
                f"**Problems:** {', '.join(str(base_rating + i * 300) for i in range(size))}\n\n"
                f"Use `;relay join 1` or `;relay join 2` to enter the lobby.\n"
                f"The creator can use `;relay start` when teams are full."
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @relay.command(name='join')
    async def relay_join(self, ctx, team: int):
        """Joins Team 1 or Team 2 in the current channel's relay lobby."""
        if ctx.channel.id not in self.matches:
            return await ctx.send("There is no active relay lobby in this channel.")
            
        match = self.matches[ctx.channel.id]
        if match.active:
            return await ctx.send("This relay race has already started!")
            
        if team not in [1, 2]:
            return await ctx.send("Please specify team 1 or team 2.")
            
        handle = cf_common.user_db.get_handle(ctx.author.id, ctx.guild.id)
        if not handle:
            return await ctx.send("You must set your Codeforces handle first! (`;handle set`)")

        # Check if already in a team
        if ctx.author in match.team1 or ctx.author in match.team2:
            return await ctx.send("You are already in this relay.")

        target_team = match.team1 if team == 1 else match.team2
        target_handles = match.team1_handles if team == 1 else match.team2_handles
        
        if len(target_team) >= match.size:
            return await ctx.send(f"Team {team} is already full!")
            
        target_team.append(ctx.author)
        target_handles.append(handle)
        
        await ctx.send(f"✅ {ctx.author.mention} joined **Team {team}** as Player {len(target_team)}!")

    @relay.command(name='start')
    async def relay_start(self, ctx):
        """Starts the relay race once teams are full."""
        if ctx.channel.id not in self.matches:
            return await ctx.send("There is no active relay lobby in this channel.")
            
        match = self.matches[ctx.channel.id]
        if match.active:
            return await ctx.send("The match has already started!")
            
        if len(match.team1) < match.size or len(match.team2) < match.size:
            return await ctx.send(f"Both teams must have exactly {match.size} players to start.")

        msg = await ctx.send("⏳ Searching for optimal problems that nobody has solved...")
        
        # Gather all solved problems from all participants
        all_handles = match.team1_handles + match.team2_handles
        solved = set()
        
        try:
            for handle in all_handles:
                subs = await cf.user.status(handle=handle)
                for s in subs:
                    if s.verdict == 'OK':
                        solved.add(s.problem.name)
        except Exception as e:
            self.logger.error(f"Error fetching API during relay start: {e}")
            return await msg.edit(content="❌ Failed to connect to Codeforces API. Try again later.")

        # Find problems
        for i in range(match.size):
            target_rating = match.base_rating + (i * 300)
            candidates = [
                p for p in cf_common.cache2.problem_cache.problems 
                if p.rating == target_rating and p.name not in solved and "tags" in dir(p)
            ]
            if not candidates:
                self.matches.pop(ctx.channel.id, None)
                return await msg.edit(content=f"❌ Could not find enough unsolved problems for rating {target_rating}. Relay cancelled.")
                
            match.problems.append(random.choice(candidates))

        match.active = True
        match.start_time = time.time()
        
        # Build the starting embed
        embed = discord.Embed(title="🏃‍♂️ THE RELAY HAS STARTED! 🏃‍♀️", color=discord.Color.red())
        
        for i, p in enumerate(match.problems):
            player1 = match.team1[i].display_name
            player2 = match.team2[i].display_name
            link = f"https://codeforces.com/contest/{p.contestId}/problem/{p.index}"
            
            # The first problem is unlocked immediately. Others are hidden for now.
            if i == 0:
                val = f"**Problem:** [{p.name}]({link})\n**P1:** {player1} ⚔️ **P2:** {player2}"
            else:
                val = f"🔒 *Problem Unlocks when Player {i} finishes!*\n**P1:** {player1} ⚔️ **P2:** {player2}"
                
            embed.add_field(name=f"Leg {i+1} ({p.rating})", value=val, inline=False)
            
        await msg.edit(content=None, embed=embed)
        await ctx.send(f"Leg 1 begins! {match.team1[0].mention} and {match.team2[0].mention}, you are up!")

    @relay.command(name='status')
    async def relay_status(self, ctx):
        """Shows the current status of the relay."""
        if ctx.channel.id not in self.matches:
            return await ctx.send("No relay active in this channel.")
            
        match = self.matches[ctx.channel.id]
        if not match.active:
            return await ctx.send("The relay is still forming in the lobby.")
            
        embed = discord.Embed(title="⏱️ Relay Status", color=discord.Color.blue())
        
        t1_str = f"Currently on Leg {match.t1_progress + 1} ({match.team1[match.t1_progress].display_name} is solving)"
        t2_str = f"Currently on Leg {match.t2_progress + 1} ({match.team2[match.t2_progress].display_name} is solving)"
        
        embed.add_field(name="Team 1", value=t1_str, inline=False)
        embed.add_field(name="Team 2", value=t2_str, inline=False)
        
        await ctx.send(embed=embed)

    @relay.command(name='cancel')
    async def relay_cancel(self, ctx):
        """Cancels an active relay or lobby."""
        if ctx.channel.id in self.matches:
            del self.matches[ctx.channel.id]
            await ctx.send("Relay cancelled.")
        else:
            await ctx.send("No relay active in this channel.")

    @tasks.loop(seconds=15.0)
    async def relay_check_task(self):
        """Background task checking if active players got an AC on their assigned problem."""
        for channel_id, match in list(self.matches.items()):
            if not match.active:
                continue

            # Check Team 1
            if match.t1_progress < match.size:
                await self._check_team_progress(match, 1, channel_id)
                
            # Check Team 2
            if match.t2_progress < match.size:
                await self._check_team_progress(match, 2, channel_id)

    async def _check_team_progress(self, match, team_num, channel_id):
        progress = match.t1_progress if team_num == 1 else match.t2_progress
        handles = match.team1_handles if team_num == 1 else match.team2_handles
        team_users = match.team1 if team_num == 1 else match.team2
        
        active_handle = handles[progress]
        target_problem = match.problems[progress]
        
        try:
            # We only need to check recent submissions for the active player
            subs = await cf.user.status(handle=active_handle, count=10)
        except Exception:
            return # Ignore API fails temporarily

        for s in subs:
            # Check if this specific submission matches the target problem and was accepted after relay start
            if (s.verdict == 'OK' and 
                s.problem.name == target_problem.name and 
                s.creationTimeSeconds > match.start_time):
                
                channel = self.bot.get_channel(channel_id)
                
                if team_num == 1:
                    match.t1_progress += 1
                    new_progress = match.t1_progress
                else:
                    match.t2_progress += 1
                    new_progress = match.t2_progress

                # Did they win?
                if new_progress >= match.size:
                    if channel:
                        win_embed = discord.Embed(
                            title=f"🏆 TEAM {team_num} WINS THE RELAY! 🏆",
                            description=f"Congratulations to {' and '.join(u.mention for u in team_users)}!",
                            color=discord.Color.gold()
                        )
                        await channel.send(embed=win_embed)
                    self.matches.pop(channel_id, None)
                    return

                # Or did they just pass the baton?
                if channel:
                    next_player = team_users[new_progress]
                    next_problem = match.problems[new_progress]
                    link = f"https://codeforces.com/contest/{next_problem.contestId}/problem/{next_problem.index}"
                    
                    pass_embed = discord.Embed(
                        title=f"🔄 Baton Passed for Team {team_num}!",
                        description=(
                            f"**{active_handle}** solved Leg {progress+1}!\n"
                            f"**Next up:** {next_player.mention} on Leg {new_progress+1} ({next_problem.rating})\n\n"
                            f"[**Click here for the problem!**]({link})"
                        ),
                        color=discord.Color.green()
                    )
                    await channel.send(content=next_player.mention, embed=pass_embed)
                return

    @relay_check_task.before_loop
    async def before_relay_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(TeamRelay(bot))
