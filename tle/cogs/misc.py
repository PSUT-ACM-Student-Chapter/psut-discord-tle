import random
from discord.ext import commands

class Prizes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name='where', help='just prizes, try where are prizes ;where is the prizes')
    async def where_command(self, ctx, *args):
        # Join the extra words together and make them lowercase
        phrase = " ".join(args).lower()
        
        # Check if they typed exactly "is the prizes" after ";where"
        if phrase == "is the prizes":
            # Generate a random number between 50 and 70
            random_years = random.randint(50, 70)
            
            # Send the response back to the channel
            await ctx.send(f"{random_years} years")

# This async setup function is REQUIRED for your bot's version
async def setup(bot):
    await bot.add_cog(Prizes(bot))
