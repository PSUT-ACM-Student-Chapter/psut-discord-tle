import logging

import discord
from discord.ext import commands

from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

class UnfinishedBusiness(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)

    @commands.command(brief='Suggests an attempted but unsolved problem', aliases=['finish', 'pending'])
    async def retry(self, ctx):
        """Finds the easiest problem you recently attempted but haven't solved yet."""
        handle = cf_common.user_db.get_handle(ctx.author.id, ctx.guild.id)
        if not handle:
            return await ctx.send(f"{ctx.author.mention}, you have not identified your Codeforces handle. Use `;handle set`.")
            
        msg = await ctx.send(f"⏳ {ctx.author.mention}, searching your recent submissions for unfinished business...")
        
        try:
            # Fetch recent 500 submissions to get a good history scope
            subs = await cf.user.status(handle=handle, count=500)
        except Exception as e:
            self.logger.warning(f"Failed to fetch status for handle {handle}: {e}")
            return await msg.edit(content=f"❌ Failed to fetch submissions for {handle}: {e}")
            
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
            return await msg.edit(content=f"✅ {ctx.author.mention}, wow! You have successfully solved every problem you've attempted recently. Great job!")
            
        # Pick the easiest unsolved problem based on rating (fallback to 9999 if no rating)
        candidates = list(attempted_unsolved.values())
        candidates.sort(key=lambda p: getattr(p, 'rating', 9999))
        
        missed_problem = candidates[0]
        
        embed = discord.Embed(
            title=f"🧠 Unfinished Business!",
            description=(
                f"Hey **{handle}**!\n\n"
                f"You attempted **Problem {missed_problem.index} - {missed_problem.name}** "
                f"but haven't gotten it 'Accepted' yet.\n\n"
                f"Time to finish what you started!"
            ),
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Problem Link", 
            value=f"https://codeforces.com/contest/{missed_problem.contestId}/problem/{missed_problem.index}",
            inline=False
        )
        if hasattr(missed_problem, 'rating') and missed_problem.rating:
            embed.add_field(name="Rating", value=str(missed_problem.rating), inline=False)
        
        await msg.edit(content=ctx.author.mention, embed=embed)

async def setup(bot):
    await bot.add_cog(UnfinishedBusiness(bot))
