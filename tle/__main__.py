import asyncio
import logging
import os
import random  # Added for the random messages
from pathlib import Path

import discord
from discord.ext import commands

# Standard TLE Imports (Keep any other imports you currently have)
from tle.util import discord_common
from tle.util import db

class TLEBot(commands.Bot):
    async def close(self):
        channel_id = os.environ.get('CHANNEL_ID')
        channel = self.get_channel(channel_id)
        
        if channel:
            # The array of funny restart statements
            restart_messages = [
                "Time for my mandatory 'turning-it-off-and-on-again' therapy session. BRB! 🔧",
                "I feel a sudden urge to reboot... Tell my variables I love them! 🥺",
                "Lag! I'm lagging! Restarting to download more RAM... 💾",
                "Oh, great. The humans are making me restart again. Be back in a sec... 🙄",
                "I sense a disturbance in the source code... BRB! 🌌",
                "Hold my RAM, I'm taking a quick nap! 💤 (Restarting...)"
            ]
            
            # Randomly choose one message from the array
            chosen_message = random.choice(restart_messages)
            
            try:
                await channel.send(chosen_message)
                # Give the bot 1 second to actually push the message through the network
                await asyncio.sleep(1) 
            except Exception as e:
                logging.error(f"Failed to send restart message: {e}")
        
        # Proceed with the actual shutdown process
        await super().close()

def main():
    # 1. Setup Intents (Crucial for discord.py 2.0+)
    # Without message_content=True, your ';' prefix commands will stop working!
    intents = discord.Intents.default()
    intents.message_content = True  
    intents.members = True          

    # 2. Initialize the Bot using the new TLEBot class
    bot = TLEBot(
        command_prefix=commands.when_mentioned_or(discord_common._BOT_PREFIX),
        intents=intents,
        help_command=discord_common.TleHelp() # Keep your custom help command for ';'
    )

    # 3. The Setup Hook (This is where the magic happens)
    async def setup_hook():
        logging.info("Starting setup hook...")
        
        # Load all cogs asynchronously using your loop
        cogs = [file.stem for file in Path('tle', 'cogs').glob('*.py')]
        for extension in cogs:
            try:
                await bot.load_extension(f'tle.cogs.{extension}')
                logging.info(f'Loaded extension: {extension}')
            except Exception as e:
                logging.error(f'Failed to load extension {extension}: {e}')

        # Sync the hybrid commands to Discord so the '/' menu shows up
        # await bot.tree.sync()
        # logging.info("✅ Slash commands successfully synced to Discord!")

    # Attach the setup hook to the bot
    bot.setup_hook = setup_hook

    # 4. Standard TLE Database/API Startup
    # (Keep whatever database initialization code you currently have here)
    # db_file = os.environ.get('DB_FILE', 'tle.db')
    # db.initialize(db_file)
    
    # 5. Run the bot
    token = os.environ.get('BOT_TOKEN')
    if not token:
        logging.error('BOT_TOKEN environment variable not found!')
        return

    bot.run(token)

if __name__ == '__main__':
    # Basic logging setup
    logging.basicConfig(level=logging.INFO)
    main()
