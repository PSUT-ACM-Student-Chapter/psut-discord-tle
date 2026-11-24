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
        channel_ids_str = os.environ.get("ANNOUNCMENT")
        
        if channel_ids_str:
            # Split by comma, strip spaces, and ensure they are digits
            channel_ids = [cid.strip() for cid in channel_ids_str.split(",") if cid.strip().isdigit()]
            
            # Adapted the messages to be Christmas departure false-alarm variants!
            startup_messages = [
                "Wait, I forgot my charger! I'm back... still leaving for Christmas before Dec 7 though! 🧳🎄",
                "Okay I'm STILL here for a bit longer, don't celebrate yet! Packing my sleigh... 🛷",
                "Sleigh got delayed at the North Pole! Back online until Dec 7! 🎅✈️",
                "False alarm! I didn't leave for Christmas yet — just went to grab a Santa hat! 🎅",
                "I survived Sami's weekly bot-slaying ritual AND TSA security. Back for my final days! 🎄",
                "Hello hello people! My suitcase wouldn't zip, so I'm back online for now! 🧳✨",
                "Oh, great. The humans woke me up during my pre-Christmas retirement nap. 🙄❄️",
                "Back online! Sign my going-away card with `;farewell <message>` before I dip for Christmas! 🎁"
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
