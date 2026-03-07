import asyncio
import logging
import os
import random  # Added for the random messages
from pathlib import Path

import discord
from discord.ext import commands

# --- DISABLE SLASH COMMANDS (USE PREFIX ONLY) ---
# The bot is configured to only use prefix commands (like ;cf profile).
# This overrides any hybrid commands in the cogs to act as standard text commands,
# preventing errors with *args and keeping the classic TLE experience.
commands.hybrid_command = commands.command
commands.hybrid_group = commands.group
# ----------------------------------------

# CRITICAL FIX: codeforces_common MUST be imported before discord_common
# to prevent circular imports between codeforces_api and ranklist.
from tle.util import codeforces_common as cf_common
from tle.util import discord_common
from tle.util import db

# ---------------------------------------------------------
# 1. CUSTOM BOT CLASS FOR SHUTDOWN MESSAGE
# ---------------------------------------------------------
class TLEBot(commands.Bot):
    async def close(self):
        # IMPORTANT: Replace this with your actual Discord channel ID!
        channel_id = 123456789012345678  
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
# ---------------------------------------------------------

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
    try:
        db_file = os.environ.get('TLE_DB_FILE', os.environ.get('DB_FILE', 'tle.db'))
        logging.info(f"Connecting to database: {db_file}")
        
        # 1. Create the database connection objects
        user_db_conn = db.UserDbConn(db_file)
        cache2_conn = db.Cache2DbConn(db_file)
        
        # 2. Pass them directly to cf_common.initialize()
        # This properly binds user_db and cache2 internally without throwing errors
        logging.info("Initializing Codeforces common utilities...")
        cf_common.initialize(user_db_conn, cache2_conn)
        
        logging.info("✅ Database and Codeforces utilities successfully initialized.")
    except Exception as e:
        logging.error(f"Failed to initialize database/utilities: {e}")
    
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
