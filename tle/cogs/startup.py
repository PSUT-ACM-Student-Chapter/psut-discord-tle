import discord
import os
from discord.ext import commands

class Startup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        channel_id = int(os.environ.get("CHANNEL_ID"))
        channel = self.bot.get_channel(channel_id)
        
        if channel:
            await channel.send("Hello Hello people, I was restarting and taking a nap I am back now")
        else:
            print("Startup Cog: Could not find the channel to send the startup message.")

# Setup function to load the cog into the bot
async def setup(bot):
    await bot.add_cog(Startup(bot))
