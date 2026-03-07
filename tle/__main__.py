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
        # Fetch the channel ID from the environment variable
        channel_id_str = os.environ.get('CHANNEL_ID')
        
        if channel_id_str and channel_id_str.isdigit():
            channel_id = int(channel_id_str)
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
        else:
            logging.warning("CHANNEL_ID is not set or invalid. Skipping restart message.")
        
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
        
        # 1. Bind user_db to cf_common (Crucial fix for 'NoneType' errors)
        if hasattr(db, 'UserDbConn'):
            cf_common.user_db = db.UserDbConn(db_file)
            logging.info("✅ User Database bound successfully.")
        else:
            logging.error("db.UserDbConn not found in your fork!")
            
        # 2. Bind the Cache database safely depending on your fork's version
        if hasattr(db, 'Cache2DbConn'):
            cf_common.cache2 = db.Cache2DbConn(db_file)
            logging.info("✅ Cache2 Database bound.")
        elif hasattr(db, 'CacheDbConn'):
            cf_common.cache2 = db.CacheDbConn(db_file)
            logging.info("✅ Cache Database bound.")
            
        # 3. Safely initialize cf_common utilities
        if hasattr(cf_common, 'initialize'):
            import inspect
            sig = inspect.signature(cf_common.initialize)
            try:
                # Some forks require args, some require none. This handles both!
                if len(sig.parameters) > 0:
                    cf_common.initialize(cf_common.user_db, getattr(cf_common, 'cache2', None))
                else:
                    cf_common.initialize()
                logging.info("✅ Codeforces utilities successfully initialized.")
            except Exception as e:
                logging.warning(f"cf_common.initialize warning (safe to ignore if cogs work): {e}")

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
