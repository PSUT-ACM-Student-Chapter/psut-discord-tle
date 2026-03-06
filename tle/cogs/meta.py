import os
import subprocess
import sys
import time
import textwrap

from discord.ext import commands

from tle import constants
from tle.util.codeforces_common import pretty_time_format

RESTART = 42


# Adapted from numpy sources.
# https://github.com/numpy/numpy/blob/master/setup.py#L64-85
def git_history():
    def _minimal_ext_cmd(cmd):
        # construct minimal environment
        env = {}
        for k in ['SYSTEMROOT', 'PATH']:
            v = os.environ.get(k)
            if v is not None:
                env[k] = v
        # LANGUAGE is used on win32
        env['LANGUAGE'] = 'C'
        env['LANG'] = 'C'
        env['LC_ALL'] = 'C'
        out = subprocess.Popen(cmd, stdout = subprocess.PIPE, env=env).communicate()[0]
        return out
    try:
        out = _minimal_ext_cmd(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
        branch = out.strip().decode('ascii')
        out = _minimal_ext_cmd(['git', 'log', '--oneline', '-5'])
        history = out.strip().decode('ascii')
        return (
            'Branch:\n' +
            textwrap.indent(branch, '  ') +
            '\nCommits:\n' +
            textwrap.indent(history, '  ')
        )
    except OSError:
        return "Fetching git info failed"


class Meta(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    @commands.hybrid_group(description='Bot control', invoke_without_command=True)
    async def meta(self, ctx):
        """Command the bot or get information about the bot."""
        await ctx.send_help(ctx.command)

    @meta.command(description='Restarts TLE')
    @commands.has_role(constants.TLE_ADMIN)
    async def restart(self, ctx):
        """Restarts the bot."""
        # Really, we just exit with a special code
        # the magic is handled elsewhere
        await ctx.send('Restarting...')
        os._exit(RESTART)

    @meta.command(description='Kill TLE')
    @commands.has_role(constants.TLE_ADMIN)
    async def kill(self, ctx):
        """Restarts the bot."""
        await ctx.send('Dying...')
        os._exit(0)
    
    @meta.command(description='Is TLE up?')
    async def ping(self, ctx):
        """Replies to a ping."""
        start = time.perf_counter()
        message = await ctx.send(':ping_pong: Pong!')
        end = time.perf_counter()
        
        rest_latency = int((end - start) * 1000)
        gateway_latency = int(self.bot.latency * 1000)
        
        # Determine a funny CP-themed message based on how slow the API is
        if rest_latency < 150:
            joke = "O(1) complexity! Did you precompute the answers? 🚀"
        elif rest_latency < 400:
            joke = "Acceptable O(N log N) time. Passes the system tests. 🏃"
        elif rest_latency < 1000:
            joke = "O(N²) detected. Careful, you might get a TLE soon... 🐢"
        else:
            joke = "Time Limit Exceeded on Pretest 1. Who wrote this O(N!) brute force? 💀"

        await message.edit(content=f'REST API latency: {rest_latency}ms\n'
                                   f'Gateway API latency: {gateway_latency}ms\n\n'
                                   f'*{joke}*')

    @meta.command(description='Get git information')
    async def git(self, ctx):
        """Replies with git information."""
        await ctx.send('```yaml\n' + git_history() + '```')

    @meta.command(description='Prints bot uptime')
    async def uptime(self, ctx):
        """Replies with how long TLE has been up."""
        await ctx.send('PXL has been running for ' +
                       pretty_time_format(time.time() - self.start_time))

    @meta.command(description='Print bot guilds')
    @commands.has_role(constants.TLE_ADMIN)
    async def guilds(self, ctx):
        "Replies with info on the bot's guilds"
        msg = [f'Guild ID: {guild.id} | Name: {guild.name} | Owner: {guild.owner.id} | Icon: {guild.icon}'
                for guild in self.bot.guilds]
        await ctx.send('```' + '\n'.join(msg) + '```')


async def setup(bot):
    await bot.add_cog(Meta(bot))
