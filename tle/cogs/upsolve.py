import logging

import discord
from discord.ext import commands

from tle.util import codeforces_api as cf
from tle.util import codeforces_common as cf_common

class UnfinishedBusiness(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)

    @commands.command(brief='Suggests attempted but unsolved problems', aliases=['finish', 'pending'])
    async def retry(self, ctx):
        """Finds up to 5 of the easiest problems you recently attempted but haven't solved yet."""
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
                # Record the problem object and the timestamp of this attempt
                # Since submissions are newest-first, this saves the most recent attempt time
                if p_id not in attempted_unsolved:
                    attempted_unsolved[p_id] = {
                        'problem': s.problem,
                        'time': s.creationTimeSeconds
                    }
                    
        # Remove any problems the user eventually solved
        for p_id in solved:
            if p_id in attempted_unsolved:
                del attempted_unsolved[p_id]
                
        if not attempted_unsolved:
            return await msg.edit(content=f"✅ {ctx.author.mention}, wow! You have successfully solved every problem you've attempted recently. Great job!")
            
        # Pick the easiest unsolved problems based on rating (fallback to 9999 if no rating or rating is None)
        candidates = list(attempted_unsolved.values())
        candidates.sort(key=lambda x: getattr(x['problem'], 'rating', None) or 9999)
        
        # Take the top 5 easiest problems
        top_candidates = candidates[:5]
        
        embed = discord.Embed(
            title=f"🧠 Unfinished Business!",
            description=(
                f"Hey **{handle}**!\n"
                f"Here are the easiest problems you attempted but haven't gotten 'Accepted' on yet.\n"
                f"Time to finish what you started!"
            ),
            color=discord.Color.blue()
        )
        
        for i, cand in enumerate(top_candidates, 1):
            prob = cand['problem']
            attempt_time = cand['time']
            
            link = f"https://codeforces.com/contest/{prob.contestId}/problem/{prob.index}"
            rating_str = f"[{prob.rating}]" if getattr(prob, 'rating', None) else "[Unrated]"
            
            # Use Discord's relative timestamp formatting
            time_str = f"<t:{attempt_time}:R>"
            
            embed.add_field(
                name=f"{i}. {prob.index} - {prob.name} {rating_str}", 
                value=f"[Click here to solve]({link})\n*Last attempted {time_str}*",
                inline=False
            )
        
        await msg.edit(content=ctx.author.mention, embed=embed)

async def setup(bot):
    await bot.add_cog(UnfinishedBusiness(bot))
