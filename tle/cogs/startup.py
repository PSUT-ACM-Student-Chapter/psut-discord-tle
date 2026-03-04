import discord
import os
from discord.ext import commands

class Startup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Fetch the comma-separated list of channel IDs
        channel_ids_str = os.environ.get("CHANNEL_IDS", os.environ.get("CHANNEL_ID"))
        
        if channel_ids_str:
            # Split by comma, strip spaces, and ensure they are digits
            channel_ids = [cid.strip() for cid in channel_ids_str.split(",") if cid.strip().isdigit()]
            
            for cid in channel_ids:
                channel = self.bot.get_channel(int(cid))
                if channel:
                    await channel.send("Hello Hello people, I was restarting and taking a nap I am back now")
                else:
                    print(f"Startup Cog: Could not find the channel to send the startup message for ID {cid}.")
        else:
            print("Startup Cog: CHANNEL_IDS environment variable is not set.")

# Setup function to load the cog into the bot
async def setup(bot):
    await bot.add_cog(Startup(bot))
