import asyncio
import random

import discord
from discord.ext import commands

class Decision(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # The pool of possible Instagram-filter-style answers
        self.responses = [
            "Yes", 
            "No", 
            "Definitely", 
            "Hell no", 
            "Maybe", 
            "Perhaps", 
            "Absolutely", 
            "Nah", 
            "100%", 
            "Not in a million years",
            "I wouldn't bet on it",
            "Without a doubt"
        ]

    @commands.command(name='no', brief='Randomly answer yes or no')
    async def no(self, ctx):
        """Replies with either "Yes" or "No" randomly."""
        reply = random.choice(['Yes', 'No'])
        await ctx.send(reply)

    @commands.command(name='ask', brief='Ask the magic Instagram filter')
    async def no_command(self, ctx):
        """Simulates the Instagram filter that cycles through answers before giving you one!"""
        msg = await ctx.send("🎥 *Tapping the screen...*")
        
        # Simulate the rapid flashing of the Instagram filter using message edits
        for i in range(5):
            temp_choice = random.choice(self.responses)
            # Make the flashing look slightly different each time to avoid Discord caching it
            spinner = "🔄" if i % 2 == 0 else "🌀" 
            await msg.edit(content=f"{spinner} `{temp_choice}`")
            await asyncio.sleep(0.4) # Wait less than half a second to create a blur effect
            
        final_choice = random.choice(self.responses)
        
        # Color code the final result!
        positive = ["Yes", "Definitely", "Absolutely", "100%", "Without a doubt"]
        negative = ["No", "Hell no", "Nah", "Not in a million years", "I wouldn't bet on it"]
        
        if final_choice in positive:
            color = discord.Color.green()
        elif final_choice in negative:
            color = discord.Color.red()
        else:
            color = discord.Color.gold()
            
        embed = discord.Embed(
            title="✨ The Filter Has Spoken ✨",
            description=f"# {final_choice}",
            color=color
        )
        embed.set_footer(text=f"Asked by {ctx.author.display_name}")
        
        # Reveal the final answer
        await msg.edit(content=ctx.author.mention, embed=embed)

async def setup(bot):
    await bot.add_cog(Decision(bot))
