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
                # Supportive messages pool (33 messages)
                responses = [
                    "Hey, it's going to be okay. Take a deep breath! You've got this. 💙",
                    "Don't give up! Every WA (Wrong Answer) is just a step towards AC (Accepted). Keep pushing! 🌟",
                    "Take a break if you need to. Your mental health is more important than your rating. You are doing great! 🫂",
                    "I believe in you! Drink some water and look at the code with fresh eyes. 🍵",
                    "It's just one contest. Your worth isn't defined by a single rating change. 📈",
                    "Consistency is key! You're making progress even when it doesn't feel like it. Keep grinding! ✨",
                    "Even the best LGMs started with a lot of ';-;' moments. You're on your way! 🚀",
                    "Take a walk, clear your mind. Sometimes the best logic comes when you aren't looking at the screen. 🌳",
                    "كل الافكار بتطلع حلول بالاخير! ~Void",
                    "Success is 1% inspiration and 99% debugging. You're almost there! 🐛",
                    "Your logic is solid, just a tiny bug hiding somewhere. You'll find it! 🔍",
                    "Think of the rating as a sine wave. You're just at a local minimum right now! 📉",
                    "If coding was easy, everyone would do it. You're doing the hard stuff! 💪",
                    "AC is temporary, but the problem-solving skills you gain are permanent. 🧠",
                    "You've solved harder problems than this. Go get 'em! 🏆",
                    "Relax, even the compilers need a break sometimes. You're doing fine. ☕",
                    "The only way to fail is to stop trying. You're still in the game! 🎮",
                    "One bug at a time, one line at a time. You're getting closer. 🛠️",
                    "Your effort today is building the skills for tomorrow's victory. 🏰",
                    "Don't compare your Chapter 1 to someone else's Chapter 20. 📖",
                    "It's okay to feel frustrated. It just shows how much you care about improving! ❤️",
                    "Remember: Progress isn't always linear. You're learning even through the failures. 📈",
                    "A bad contest doesn't make you a bad coder. It's just data for your next improvement. 📊",
                    "You're like an unoptimized loop: eventually, you'll get there, it just takes a bit longer! 🔄",
                    "Debugging is like being the detective in a crime movie where you are also the murderer. You'll catch him! 🕵️‍♂️",
                    "You're the `main()` function of this club. Don't `return 1` yet! 💻",
                    "If at first you don't succeed, call it version 1.0 and try again. 🆕",
                    "Your code might have bugs, but at least it has personality! 🐛",
                    "Rating is temporary, but the 'I actually solved it' high is forever. 🚀",
                    "Think of every Wrong Answer as a personalized hint from the judge. 💡",
                    "May your logic be as fast as O(1) and your focus as deep as O(N!). ⚡",
                    "You're not stuck, you're just 'processing'. Give your brain a buffer! 🧠",
                    "You're doing great! Even the best programmers started by printing 'Hello World' and crying. 🌍"
                ]
            else:
                # Harsh / "Tough Love" messages pool (Expanded to 33 messages)
                responses = [
                    "Stop crying and get back to work! The code isn't going to write itself! 🛑",
                    "Skill issue. Read the problem statement again and debug your logic! 💻",
                    "Tears won't fix that Time Limit Exceeded. Optimize your algorithm! ⚡",
                    "Why are you crying over a simple implementation problem? Get good! 🔨",
                    "If you spent as much time coding as you did sending ';-;', you'd be a Master by now. 🙄",
                    "Stop checking the leaderboard and start checking your edge cases. 🧐",
                    "Expected: AC. Found: Crying. Fix your status! ❌",
                    "Go back to 800-rated problems if this is too hard for you. No participation trophies here! 🏆",
                    "Your code is a hazard to the server's CPU. Optimize or quit! 🔌",
                    "Even a random number generator has better odds of AC than your current logic. 🎲",
                    "O(N^3) on a 10^5 constraint? Do you want the judge to die of old age? ⏳",
                    "Binary search for your brain cells because they seem to be missing. 🕵️‍♂️",
                    "Instead of ';-;', try 'thinking'. It's a new feature in competitive programming. 🧠",
                    "The problem isn't the test cases, the problem is sitting between the chair and the keyboard. 🪑",
                    "LGM doesn't stand for 'Let's Go Moan'. Back to the IDE! 🚀",
                    "Your complexity analysis is 'I hope it works'. Narrative: It didn't. 📉",
                    "Is your complexity O(log N) or O(log No hope)? Fix it! 📉",
                    "Do you want a 🔪 reaction? Because this level of laziness is exactly how you get a 🔪 reaction. 😤",
                    "Are you solving the problem or trying to DOS the judge with WA submissions? 🛑",
                    "Your variable names are a cry for help. 'a', 'aa', 'aaa'? Seriously? 🤡",
                    "Your code is so messy it probably violates the Geneva Convention. 🏳️",
                    "You call this code? I've seen better logic in a broken calculator. 📉",
                    "I've seen O(N!) solutions faster than your brain today. 🧠",
                    "If I had a nickel for every time you used a global variable, I'd have enough to buy you a brain. 💸",
                    "Your brute force is so slow, the sun will explode before you get AC. ☀️",
                    "Memory Limit Exceeded? More like Talent Limit Exceeded. 🧠",
                    "If laziness was a problem, you'd be rated 4000. 🙄",
                    "The judge is tired of looking at your code. Have some mercy and debug it! 🧘",
                    "Is that an infinite loop or are you just stuck in a cycle of failure? 🔄",
                    "You're proof that even with a computer, some people can't compute. 🤡",
                    "Training is mandatory. The 🔪 is also mandatory for those who don't. Choice is yours.",
                    "You're the reason Python has a recursion limit. Calm down and optimize. 📉",
                    "You're the weak link in our `std::vector`. Don't make me `pop_back()` you. 🚮"
                ]

            # 4. Pick a random message from the chosen category
            reply_msg = random.choice(responses)
            
            # 5. Send the message back to the channel
            await message.channel.send(reply_msg)

# Setup function to load the cog into the bot
async def setup(bot):
    await bot.add_cog(Motivation(bot))
