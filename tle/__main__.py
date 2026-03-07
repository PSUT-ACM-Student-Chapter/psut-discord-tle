import argparse
import asyncio
import distutils.util
import logging
import os
import random  # Added for the random messages
import discord
from logging.handlers import TimedRotatingFileHandler
from os import environ
from pathlib import Path

import seaborn as sns
from discord.ext import commands
from matplotlib import pyplot as plt

from tle import constants
from tle.util import codeforces_common as cf_common
from tle.util import discord_common, font_downloader

# --- DISABLE SLASH COMMANDS (USE PREFIX ONLY) ---
# The bot is configured to only use prefix commands (like ;cf profile).
# This overrides any hybrid commands in the cogs to act as standard text commands,
# preventing errors with *args and keeping the classic TLE experience.
commands.hybrid_command = commands.command
commands.hybrid_group = commands.group
# ----------------------------------------

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

def setup():
    # Make required directories.
    for path in constants.ALL_DIRS:
        os.makedirs(path, exist_ok=True)

    # logging to console and file on daily interval
    logging.basicConfig(format='{asctime}:{levelname}:{name}:{message}', style='{',
                        datefmt='%d-%m-%Y %H:%M:%S', level=logging.INFO,
                        handlers=[logging.StreamHandler(),
                                  TimedRotatingFileHandler(constants.LOG_FILE_PATH, when='D',
                                                           backupCount=3, utc=True)])

    # matplotlib and seaborn
    plt.rcParams['figure.figsize'] = 7.0, 3.5
    sns.set()
    options = {
        'axes.edgecolor': '#A0A0C5',
        'axes.spines.top': False,
        'axes.spines.right': False,
    }
    sns.set_style('darkgrid', options)

    # Download fonts if necessary
    font_downloader.maybe_download()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--nodb', action='store_true')
    args = parser.parse_args()

    token = environ.get('BOT_TOKEN')
    if not token:
        logging.error('Token required')
        return

    setup()
    
    intents = discord.Intents.default()
    intents.members = True
    intents.message_content = True

    # Use the custom TLEBot class instead of standard commands.Bot
    bot = TLEBot(command_prefix=commands.when_mentioned_or(discord_common._BOT_PREFIX), intents=intents)
    bot.help_command = discord_common.TleHelp()
    cogs = [file.stem for file in Path('tle', 'cogs').glob('*.py')]
    for extension in cogs:
        await bot.load_extension(f'tle.cogs.{extension}')
    logging.info(f'Cogs loaded: {", ".join(bot.cogs)}')

    def no_dm_check(ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage('Private messages not permitted.')
        return True

    def channel_check(ctx):
        # Allow checking either CHANNEL_IDS or CHANNEL_ID for backward compatibility
        channel_ids_str = os.environ.get("CHANNEL_IDS", os.environ.get("CHANNEL_ID"))
        if channel_ids_str:
            # Parse multiple channels separated by commas and remove empty spaces
            channel_ids = [int(cid.strip()) for cid in channel_ids_str.split(",") if cid.strip().isdigit()]
            return ctx.channel.id in channel_ids
        return True

    # Restrict bot usage to inside guild channels only.
    bot.add_check(no_dm_check)
    
    # Restrict bot usage to specific channels if CHANNEL_IDS is set.
    # bot.add_check(channel_check)

    # cf_common.initialize needs to run first, so it must be set as the bot's
    # on_ready event handler rather than an on_ready listener.
    @discord_common.on_ready_event_once(bot)
    async def init():
        await cf_common.initialize(args.nodb)
        asyncio.create_task(discord_common.presence(bot))

    bot.add_listener(discord_common.bot_error_handler, name='on_command_error')
    await bot.start(token)


if __name__ == '__main__':
     asyncio.run(main())
