import discord
import random
import time
from discord.ext import commands

class Pxl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='pxl', help='The ultimate "Yes, I am here" command.')
    async def pxl(self, ctx):
        # A list of funny, persona-driven greetings
        greetings = [
            "Yes? How can I help you? (Unless you're here to complain about a TLE, then I'm 'busy'.)",
            "At your service! What's the plan? Ready to turn some red circles into green checkmarks?",
            "I'm here! I was just busy simulating a 24-hour marathon, but for you, I'll take a break.",
            "You rang? I hope it's about a `;gitgud` and not about why your O(N^3) solution failed on N=10^5.",
            "Beep boop. I'm awake. Barely. What's on your mind, legendary coder?",
            "Yes, mortal? How can I assist your quest for the legendary 'Accepted' verdict today?"
        ]

        # A list of "Fun Facts" or "Bot Wisdom" derived from its features
        fun_facts = [
            "Fun Fact: My favorite food is raw Python scripts and Codeforces API responses.",
            "Did you know? Using `;gitgud` doesn't technically guarantee a rating increase, but it definitely increases your 'cool' factor by 15%.",
            "I was born from the TLE bot repository, but I've been upgraded with PSUT ACM spirit!",
            "If you're feeling brave, try `;duel` to settle who the real grandmaster is.",
            "I can track your progress with `;stalk`, but don't worry, I promise it's the friendly kind of stalking.",
            "I spend 90% of my time waiting for the Codeforces API and the other 10% judging your variable names."
        ]

        # Select random elements
        greeting = random.choice(greetings)
        fun_fact = random.choice(fun_facts)

        # Check latency to help debug those heartbeat issues you saw in the logs
        latency = round(self.bot.latency * 1000)
        status_color = discord.Color.green() if latency < 200 else discord.Color.gold()
        if latency > 500: status_color = discord.Color.red()

        # Construct the embed
        embed = discord.Embed(
            title="PXL Reporting for Duty! 🤖", 
            description=f"**{greeting}**",
            color=status_color
        )
        
        embed.add_field(
            name="✨ How to use me", 
            value="• Use `;help` to see my massive list of CP superpowers.\n"
                  "• Haven't registered? Use `;handle identify <your_handle>`!",
            inline=False
        )
        
        embed.add_field(
            name="💡 Bot Wisdom", 
            value=f"*{fun_fact}*",
            inline=False
        )

        embed.set_footer(text=f"Heartbeat Latency: {latency}ms | PSUT ACM Edition")

        await ctx.send(embed=embed)

# This setup function is required for discord.ext.commands to load the Cog
async def setup(bot):
    await bot.add_cog(Pxl(bot))
