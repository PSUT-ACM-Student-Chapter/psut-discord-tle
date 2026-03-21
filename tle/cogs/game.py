import random
import discord
from discord.ext import commands

class Game:
    """Base class for interactive games."""
    def __init__(self):
        self.queries_used = 0
        self.max_queries = 0
        self.description = ""
        self.name = ""

    def query(self, *args):
        raise NotImplementedError

    def guess(self, *args):
        raise NotImplementedError

class EasyGame(Game):
    """Guess the number (Binary Search)"""
    def __init__(self):
        super().__init__()
        self.name = "Guess the Number (Binary Search)"
        self.target = random.randint(1, 100000)
        self.max_queries = 20
        self.description = (
            "I have hidden a number x between `1` and `100,000`.\n"
            "Use `;ig q <number>` to ask if your number is `< target`, `> target`, or `= target`.\n"
            "Use `;ig g <number>` to make your final guess!"
        )

    def query(self, *args):
        if len(args) != 1:
            return "❌ Please provide exactly one number: `;ig q <x>`"
        try:
            x = int(args[0])
        except ValueError:
            return "❌ Invalid number."
        
        self.queries_used += 1
        if x < self.target:
            return f"The target is **greater** than {x} `(target > {x})`"
        elif x > self.target:
            return f"The target is **less** than {x} `(target < {x})`"
        else:
            return f"{x} is **equal** to the target! You can guess it now."

    def guess(self, *args):
        if len(args) != 1:
            return False, "❌ Please provide exactly one number: `;ig g <x>`"
        try:
            x = int(args[0])
        except ValueError:
            return False, "❌ Invalid number."

        if x == self.target:
            return True, f"🎉 **Correct!** The hidden number was {self.target}."
        else:
            return False, f"💀 **Wrong!** The hidden number was {self.target}."

class MediumGame(Game):
    """Find the Peak (Ternary Search)"""
    def __init__(self):
        super().__init__()
        self.name = "Find the Peak (Ternary Search)"
        self.P = random.randint(1, 10000)
        self.A = random.randint(1, 10)
        self.B = random.randint(10**7, 10**8)
        self.max_queries = 40
        self.description = (
            "I have a hidden unimodal quadratic function f(x) with a single maximum peak at an integer P (`1 <= P <= 10,000`).\n"
            "Use `;ig q <x>` to get the value of f(x).\n"
            "Use `;ig g <P>` to guess the exact location of the peak P!"
        )

    def query(self, *args):
        if len(args) != 1:
            return "❌ Please provide exactly one number: `;ig q <x>`"
        try:
            x = int(args[0])
        except ValueError:
            return "❌ Invalid number."
        
        self.queries_used += 1
        val = -(self.A * ((x - self.P) ** 2)) + self.B
        return f"$f({x}) = {val}$"

    def guess(self, *args):
        if len(args) != 1:
            return False, "❌ Please provide exactly one number: `;ig g <P>`"
        try:
            x = int(args[0])
        except ValueError:
            return False, "❌ Invalid number."

        if x == self.P:
            return True, f"🎉 **Correct!** The peak was exactly at $P = {self.P}$."
        else:
            return False, f"💀 **Wrong!** The peak was at $P = {self.P}$."

class HardGame(Game):
    """Lost Numbers (Codeforces 1167B)"""
    def __init__(self):
        super().__init__()
        self.name = "Lost Numbers (Interactive Logic)"
        self.arr = [4, 8, 15, 16, 23, 42]
        random.shuffle(self.arr)
        self.max_queries = 4
        self.description = (
            "I have a hidden array of length 6. It is a permutation of `[4, 8, 15, 16, 23, 42]`.\n"
            "Use `;ig q <i> <j>` to query the product of the elements at indices i and j (1-indexed, `1 <= i, j <= 6`).\n"
            "You only have **4 queries**.\n"
            "Use `;ig g <n1> <n2> <n3> <n4> <n5> <n6>` to guess the full array."
        )

    def query(self, *args):
        if len(args) != 2:
            return "❌ Please provide exactly two indices: `;ig q <i> <j>`"
        try:
            i, j = int(args[0]), int(args[1])
            if not (1 <= i <= 6 and 1 <= j <= 6):
                return "❌ Indices must be between 1 and 6."
        except ValueError:
            return "❌ Invalid numbers."
        
        self.queries_used += 1
        product = self.arr[i-1] * self.arr[j-1]
        return f"The product of elements at indices {i} and {j} is **{product}**."

    def guess(self, *args):
        if len(args) != 6:
            return False, "❌ Please provide exactly six numbers: `;ig g <n1> <n2> <n3> <n4> <n5> <n6>`"
        try:
            guessed_arr = [int(x) for x in args]
        except ValueError:
            return False, "❌ Invalid numbers."

        if guessed_arr == self.arr:
            return True, f"🎉 **Correct!** The array was `{self.arr}`."
        else:
            return False, f"💀 **Wrong!** The correct array was `{self.arr}`."


class InteractiveGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Maps (channel_id, user_id) to an active Game instance
        self.active_games = {}

    @commands.group(brief='Play interactive CP games', aliases=['ig'], invoke_without_command=True)
    async def interactive(self, ctx):
        """Play interactive Competitive Programming games (Easy, Medium, Hard)."""
        await ctx.send_help(ctx.command)

    @interactive.command(brief='Start a new game (easy, medium, hard)')
    async def play(self, ctx, difficulty: str):
        difficulty = difficulty.lower()
        key = (ctx.channel.id, ctx.author.id)

        if key in self.active_games:
            await ctx.send(f"{ctx.author.mention}, you already have an active game in this channel! Use `;ig quit` to stop it.")
            return

        if difficulty == "easy":
            game = EasyGame()
        elif difficulty == "medium":
            game = MediumGame()
        elif difficulty == "hard":
            game = HardGame()
        else:
            await ctx.send("❌ Unknown difficulty. Please choose `easy`, `medium`, or `hard`.")
            return

        self.active_games[key] = game
        
        embed = discord.Embed(title=f"Started: {game.name}", description=game.description, color=discord.Color.blue())
        embed.set_footer(text=f"Max queries allowed: {game.max_queries}")
        await ctx.send(embed=embed)

    @interactive.command(name='query', aliases=['q'], brief='Make a query to the judge')
    async def query(self, ctx, *args):
        key = (ctx.channel.id, ctx.author.id)
        if key not in self.active_games:
            await ctx.send(f"{ctx.author.mention}, you don't have an active game here. Start one with `;ig play <difficulty>`.")
            return

        game = self.active_games[key]
        
        if game.queries_used >= game.max_queries:
            await ctx.send(f"⚠️ {ctx.author.mention}, you've used all {game.max_queries} queries! You must guess now using `;ig g <args>`.")
            return

        response = game.query(*args)
        
        embed = discord.Embed(description=response, color=discord.Color.orange())
        if "❌" not in response:
            embed.set_footer(text=f"Queries used: {game.queries_used} / {game.max_queries}")
        
        await ctx.send(embed=embed)

    @interactive.command(name='guess', aliases=['g'], brief='Make your final guess')
    async def guess(self, ctx, *args):
        key = (ctx.channel.id, ctx.author.id)
        if key not in self.active_games:
            await ctx.send(f"{ctx.author.mention}, you don't have an active game here.")
            return

        game = self.active_games[key]
        won, message = game.guess(*args)
        
        if "❌" in message:
            await ctx.send(message) # Validation error
            return

        # Game is over
        color = discord.Color.green() if won else discord.Color.red()
        embed = discord.Embed(title="Game Over!", description=message, color=color)
        embed.set_footer(text=f"You used {game.queries_used} queries.")
        await ctx.send(embed=embed)
        
        del self.active_games[key]

    @interactive.command(name='quit', brief='Quit your current game')
    async def quit(self, ctx):
        key = (ctx.channel.id, ctx.author.id)
        if key in self.active_games:
            del self.active_games[key]
            await ctx.send(f"{ctx.author.mention}, your game has been cancelled.")
        else:
            await ctx.send(f"{ctx.author.mention}, you don't have an active game to quit.")

async def setup(bot):
    await bot.add_cog(InteractiveGames(bot))
