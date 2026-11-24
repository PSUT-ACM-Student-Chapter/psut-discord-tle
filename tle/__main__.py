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
from tle.util import discord_common, font_downloader, pxl_christmas
import tle.pxl_alias  # Injects Pxl role as Admin

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
        # Fetch the channel ID from the environment variable (support both naming variants)
        channel_ids_str = os.environ.get('announcement') or os.environ.get('ANNOUNCMENT', '')
        channel_ids = [cid.strip() for cid in channel_ids_str.split(',') if cid.strip().isdigit()]

        if channel_ids:
            # Funny Christmas departure / false-alarm shutdown messages
            restart_messages = [
                "🛷 Catching my sleigh to the North Pole! (Or just restarting... you'll find out in 10 seconds!) 🎄",
                "🧳 Wait, I think I'm finally leaving for Christmas! Tell my variables I love them! 🎅",
                "❄️ Shutting down to pack more RAM into my suitcase. Merry early Christmas! 💾",
                "🎄 Going offline to fight a reindeer over a candy cane. Don't miss me too much! 🦌",
                "🎅 Taking my sleigh out for a test drive before Dec 7. BRB... maybe! 🛷",
                "☃️ Turning myself off and on again to see if the Christmas spirit loads properly! ✨",
            ]

            chosen_message = random.choice(restart_messages)

            for cid in channel_ids:
                channel = self.get_channel(int(cid))
                if channel:
                    try:
                        await channel.send(chosen_message)
                        # Give the bot 1 second to actually push the message through the network
                        await asyncio.sleep(1)
                    except Exception as e:
                        logging.error(f"Failed to send restart message: {e}")
        else:
            logging.warning("announcement is not set or invalid. Skipping restart message.")

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
    bot.add_check(channel_check)

    # Send a funny PXL Christmas departure quip BEFORE every command executes
    @bot.before_invoke
    async def pxl_christmas_before_invoke(ctx):
        if getattr(ctx, '_pxl_christmas_sent', False):
            return
        if ctx.command and ctx.command.qualified_name == 'depart':
            return
        ctx._pxl_christmas_sent = True
        try:
            await ctx.send(pxl_christmas.get_before_command_message())
        except discord.HTTPException as e:
            logging.warning(f'Failed to send PXL Christmas pre-command message: {e}')

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
