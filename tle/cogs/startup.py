import discord
import os
import random
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
            
            # Adapted the messages to be "waking up" variants!
            startup_messages = [
                "My 'turning-it-off-and-on-again' therapy session is complete. I'm back! 🔧",
                "I survived the reboot! My variables missed you all. 🥺",
                "RAM downloaded successfully. No more lag! 💾",
                "Oh, great. The humans woke me up again. I'm back... 🙄",
                "The source code has stabilized... I have returned! 🌌",
                "Nap time is over! RAM cleared, ready to go! ✨",
                "Hello Hello people, I was restarting and taking a nap, I am back now! 💤"
            ]

            for cid in channel_ids:
                channel = self.bot.get_channel(int(cid))
                if channel:
                    # Randomly pick a message from the list
                    await channel.send(random.choice(startup_messages))
                else:
                    print(f"Startup Cog: Could not find the channel to send the startup message for ID {cid}.")
        else:
            print("Startup Cog: CHANNEL_IDS environment variable is not set.")

# Setup function to load the cog into the bot
async def setup(bot):
    await bot.add_cog(Startup(bot))
