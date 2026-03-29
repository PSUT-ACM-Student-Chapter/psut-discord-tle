import difflib
from discord.ext import commands

class CommandSuggestion(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        # We only care about the CommandNotFound error here
        if isinstance(error, commands.CommandNotFound):
            
            # Get the command name the user attempted to type
            invalid_command = ctx.invoked_with 
            if not invalid_command:
                return

            # Gather all command names and their aliases
            all_commands = []
            for cmd in self.bot.commands:
                # Optionally, you can skip hidden commands so they aren't suggested
                if not cmd.hidden:
                    all_commands.append(cmd.name)
                    all_commands.extend(cmd.aliases)

            # Use difflib to find the closest match
            # n=1 means we only want the top match
            # cutoff=0.6 requires a 60% similarity to suggest the command
            matches = difflib.get_close_matches(invalid_command, all_commands, n=1, cutoff=0.6)

            if matches:
                suggested_command = matches[0]
                await ctx.send(f"⚠️ Command not found. Did you mean `{ctx.prefix}{suggested_command}`?")
            
            # If you want to notify them even when no match is found, uncomment below:
            # else:
            #     await ctx.send("⚠️ Command not found.")
            
            return

        # Make sure to handle/raise other errors if this is your main error handler!
        # If you already have an on_command_error somewhere else in your bot, 
        # just copy the `if isinstance(error, commands.CommandNotFound):` block into it.

async def setup(bot):
    await bot.add_cog(CommandSuggestion(bot))
