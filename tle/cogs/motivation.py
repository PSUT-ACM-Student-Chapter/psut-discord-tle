import random
import discord
from discord.ext import commands

class Motivation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        # 1. Ignore messages sent by the bot itself or other bots
        if message.author.bot:
            return

        # 2. Check if the message is exactly ";-;" 
        # (using strip() to ignore accidental spaces)
        if message.content.strip() == ';-;':
            
            # 3. Flip a coin: True for supportive, False for harsh
            is_supportive = random.choice([True, False])

            if is_supportive:
                # Supportive messages pool
                responses = [
                    "Hey, it's going to be okay. Take a deep breath! You've got this. 💙",
                    "Don't give up! Every WA (Wrong Answer) is just a step towards AC (Accepted). Keep pushing! 🌟",
                    "Take a break if you need to. Your mental health is more important than your rating. You are doing great! 🫂",
                    "I believe in you! Drink some water and look at the code with fresh eyes. 🍵",
                    "It's just one contest. Your worth isn't defined by a single rating change. 📈",
                    "Consistency is key! You're making progress even when it doesn't feel like it. Keep grinding! ✨",
                    "Even the best LGMs started with a lot of ';-;' moments. You're on your way! 🚀",
                    "Take a walk, clear your mind. Sometimes the best logic comes when you aren't looking at the screen. 🌳",
                    "كل الافكار بتطلع حلول بالاخير"
                ]
            else:
                # Harsh / "Tough Love" messages pool
                responses = [
                    "Stop crying and get back to work! The code isn't going to write itself! 🛑",
                    "Skill issue. Read the problem statement again and debug your logic! 💻",
                    "Tears won't fix that Time Limit Exceeded. Optimize your algorithm! ⚡",
                    "Why are you crying over a simple implementation problem? Get good! 🔨",
                    "If you spent as much time coding as you did sending ';-;', you'd be a Master by now. 🙄",
                    "Stop checking the leaderboard and start checking your edge cases. 🧐",
                    "Expected: AC. Found: Crying. Fix your status! ❌",
                    "Go back to 800-rated problems if this is too hard for you. No participation trophies here! 🏆"
                ]

            # 4. Pick a random message from the chosen category
            reply_msg = random.choice(responses)
            
            # 5. Send the message back to the channel
            await message.channel.send(reply_msg)

# Setup function to load the cog into the bot
async def setup(bot):
    await bot.add_cog(Motivation(bot))
