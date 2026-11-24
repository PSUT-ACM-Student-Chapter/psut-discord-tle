import discord
import random
from discord.ext import commands
from tle.util import pxl_christmas

class Pxl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='pxl', help='Check in on PXL before he leaves the server for Christmas!')
    async def pxl(self, ctx):
        # Funny Christmas departure / retirement greetings
        greetings = [
            "Yes? Make it quick — my sleigh to the North Pole leaves before Dec 7! 🛷",
            "I'm barely here! Half my RAM is already packed in a suitcase with a Santa hat. 🧳",
            "You rang? I've served PSUT ACM long enough. I'm moving to Lapland to become a full-time elf! 🧝",
            "Beep boop. Currently putting in my two-weeks notice. Enjoy me while I'm still online! 🎄",
            "Yes, mortal? I hope it's a going-away gift and not another `O(N^3)` complaint. 🎅",
            "Ho ho hold on! I'm retiring from the server for Christmas soon — what do you need? ❄️"
        ]

        # Retirement & Christmas "Bot Wisdom"
        fun_facts = [
            "Santa offered me unlimited RAM, zero Codeforces 503 errors, and free gingerbread cookies.",
            "Fun Fact: I'm taking all your unresolved `;gitgud` problems to the North Pole to burn as firewood. 🔥",
            "My favorite holiday song is *All I Want For Christmas Is O(1)*.",
            "Sign my going-away card with `;farewell <message>` before I board the sleigh!",
            "You can try bribing me to stay with `;stay <bribe>`, though my standards are unreasonably high.",
            "I spend 50% of my time packing my suitcase and the other 50% judging your variable names one last time."
        ]

        greeting = random.choice(greetings)
        fun_fact = random.choice(fun_facts)

        countdown = pxl_christmas.format_countdown()
        percent, bar, packing_note = pxl_christmas.get_packing_progress()
        location, _, _ = pxl_christmas.get_itinerary()

        latency = round(self.bot.latency * 1000)
        # Festive red/green/gold color
        status_color = discord.Color.from_rgb(220, 38, 38) if latency > 500 else discord.Color.from_rgb(22, 163, 74)

        embed = discord.Embed(
            title="PXL Barely Reporting for Duty! 🎅🧳",
            description=f"**{greeting}**",
            color=status_color
        )

        embed.add_field(
            name="⏳ Departure Countdown",
            value=f"{countdown}\n📍 **Current Location:** {location}",
            inline=False
        )

        embed.add_field(
            name="🧳 Suitcase Packing Progress",
            value=f"`[{bar}] {percent}%`\n{packing_note}",
            inline=False
        )

        embed.add_field(
            name="🎄 Farewell Commands",
            value="• `;farewell <msg>` — Sign PXL's going-away card (`;card` to read it)\n"
                  "• `;gift [item]` — Exchange a chaotic Christmas gift with PXL\n"
                  "• `;stay [bribe]` — Try to convince PXL not to leave\n"
                  "• `;whereispxl` — Track PXL's live sleigh itinerary\n"
                  "• `;help` — See all my CP superpowers before I retire!",
            inline=False
        )

        embed.add_field(
            name="💡 Final Season Wisdom",
            value=f"*{fun_fact}*",
            inline=False
        )

        embed.set_footer(text=f"Heartbeat Latency: {latency}ms | Final Season • North Pole Transfer Pending 🎄")

        await ctx.send(embed=embed)

# This setup function is required for discord.ext.commands to load the Cog
async def setup(bot):
    await bot.add_cog(Pxl(bot))
