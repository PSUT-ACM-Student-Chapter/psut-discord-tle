import os
import json
import math
import random
import io

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

DATA_FILE = "data/brackets.json"

class Brackets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tournaments = {}
        self.load_data()

    def load_data(self):
        """Loads bracket data from the JSON file."""
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                self.tournaments = json.load(f)

    def save_data(self):
        """Saves current bracket data to the JSON file."""
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w') as f:
            json.dump(self.tournaments, f, indent=4)

    def is_manager(self, ctx, t):
        """Checks if the user has permission to manage the bracket."""
        if ctx.author.guild_permissions.administrator:
            return True
        return ctx.author.id in t.get('managers', [])

    def next_power_of_2(self, x):
        return 1 if x == 0 else 2**(x - 1).bit_length()

    def advance_winner(self, t, match_id, winner_id):
        """Recursively advances a winner up the bracket tree and returns newly activated matches."""
        str_id = str(match_id)
        t['matches'][str_id]['winner'] = winner_id
        
        # If this was the final match
        if match_id == 1:
            t['state'] = 'finished'
            return []
            
        parent_id = match_id // 2
        str_parent = str(parent_id)
        parent = t['matches'][str_parent]
        
        if match_id % 2 == 0:
            parent['p1'] = winner_id
        else:
            parent['p2'] = winner_id

        # Check if parent match is now fully populated
        if parent['p1'] is not None and parent['p2'] is not None:
            if parent['p1'] == 'BYE':
                return self.advance_winner(t, parent_id, parent['p2'])
            elif parent['p2'] == 'BYE':
                return self.advance_winner(t, parent_id, parent['p1'])
            else:
                return [parent_id]
        return []

    def generate_bracket_image(self, t):
        """Uses Pillow to draw the bracket graph."""
        BOX_WIDTH = 220
        BOX_HEIGHT = 60
        COL_SPACING = 300
        ROW_SPACING = 100

        N = len(t['matches']) + 1
        D = int(math.log2(N))

        img_width = D * COL_SPACING + 50
        img_height = (N // 2) * ROW_SPACING + 50
        
        # Discord dark theme background
        image = Image.new('RGB', (img_width, img_height), (44, 47, 51))
        draw = ImageDraw.Draw(image)

        # Use TLE's NotoSans font if available, fallback otherwise
        font_path = os.path.join('tle', 'assets', 'fonts', 'NotoSans-Bold.ttf')
        try:
            font = ImageFont.truetype(font_path, 16)
        except IOError:
            font = ImageFont.load_default()

        # Calculate Box Coordinates
        Y = {}
        for i in range(N // 2):
            Y[(N // 2) + i] = i * ROW_SPACING + 25

        for x in range(N // 2 - 1, 0, -1):
            Y[x] = (Y[2*x] + Y[2*x + 1]) / 2

        X = {}
        for x in range(1, N):
            d = int(math.log2(x))
            X[x] = (D - 1 - d) * COL_SPACING + 25

        # 1. Draw connecting lines
        for x in range(2, N):
            parent = x // 2
            startX = X[x] + BOX_WIDTH
            startY = Y[x] + BOX_HEIGHT // 2
            endX = X[parent]
            endY = Y[parent] + BOX_HEIGHT // 2
            midX = startX + (endX - startX) // 2

            draw.line([(startX, startY), (midX, startY)], fill=(114, 137, 218), width=3)
            draw.line([(midX, startY), (midX, endY)], fill=(114, 137, 218), width=3)
            draw.line([(midX, endY), (endX, endY)], fill=(114, 137, 218), width=3)

        # 2. Draw Match Boxes and Text
        for x in range(1, N):
            match = t['matches'][str(x)]
            x_pos = X[x]
            y_pos = Y[x]

            # Box background
            draw.rectangle(
                [x_pos, y_pos, x_pos + BOX_WIDTH, y_pos + BOX_HEIGHT], 
                fill=(35, 39, 42), outline=(153, 170, 181), width=2
            )
            draw.line(
                [(x_pos, y_pos + BOX_HEIGHT//2), (x_pos + BOX_WIDTH, y_pos + BOX_HEIGHT//2)], 
                fill=(153, 170, 181), width=1
            )

            # Name Resolving
            def get_name(user_id):
                if user_id is None: return "TBD"
                if user_id == "BYE": return "BYE"
                user = self.bot.get_user(user_id)
                return user.display_name if user else f"User {user_id}"

            p1_name = get_name(match.get('p1'))
            p2_name = get_name(match.get('p2'))

            # Highlights for winner
            color1 = (255, 255, 255)
            color2 = (255, 255, 255)
            if match.get('winner') == match.get('p1') and match.get('p1') not in (None, 'BYE'):
                color1 = (67, 181, 129) # Discord Green
            elif match.get('winner') == match.get('p2') and match.get('p2') not in (None, 'BYE'):
                color2 = (67, 181, 129)

            draw.text((x_pos + 10, y_pos + 5), p1_name, fill=color1, font=font)
            draw.text((x_pos + 10, y_pos + BOX_HEIGHT//2 + 5), p2_name, fill=color2, font=font)

        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

    async def announce_matches(self, ctx, t, match_ids):
        """Pings the players who are paired up."""
        for mid in match_ids:
            match = t['matches'][str(mid)]
            if match['p1'] not in (None, 'BYE') and match['p2'] not in (None, 'BYE'):
                await ctx.send(f"⚔️ **Match Time!** <@{match['p1']}> 🆚 <@{match['p2']}>\n*Managers can report the winner using `;bracket report {t['name']} @winner`*")

    # --- DISCORD COMMANDS ---

    @commands.group(brief='Tournament bracket commands', invoke_without_command=True)
    async def bracket(self, ctx):
        await ctx.send_help(ctx.command)

    @bracket.command(brief='Create a new bracket')
    async def create(self, ctx, name: str, b_type: str = 'single_elimination', *managers: discord.Member):
        if name in self.tournaments:
            return await ctx.send(f"❌ Bracket `{name}` already exists!")
        
        manager_ids = [ctx.author.id] + [m.id for m in managers]
        self.tournaments[name] = {
            'name': name,
            'type': b_type,
            'state': 'registering',
            'managers': list(set(manager_ids)),
            'players': [],
            'matches': {}
        }
        self.save_data()
        await ctx.send(f"✅ Created bracket `{name}`. Type `;bracket register {name}` to join!")

    @bracket.command(brief='Register for a bracket')
    async def register(self, ctx, name: str):
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if t['state'] != 'registering': return await ctx.send("❌ Registration is closed.")
        if ctx.author.id in t['players']: return await ctx.send("❌ You are already registered.")

        t['players'].append(ctx.author.id)
        self.save_data()
        await ctx.send(f"✅ Registered **{ctx.author.display_name}** for `{name}`. Total players: {len(t['players'])}")

    @bracket.command(brief='Unregister a user from a bracket')
    async def unregister(self, ctx, name: str, user: discord.Member = None):
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        
        target = user or ctx.author
        if target.id != ctx.author.id and not self.is_manager(ctx, t):
            return await ctx.send("❌ You do not have permission to remove other users.")
            
        if target.id in t['players']:
            t['players'].remove(target.id)
            self.save_data()
            await ctx.send(f"✅ Removed **{target.display_name}** from `{name}`.")
        else:
            await ctx.send("❌ User not found in bracket.")

    @bracket.command(brief='Starts the bracket and randomizes seeds')
    async def start(self, ctx, name: str):
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if not self.is_manager(ctx, t): return await ctx.send("❌ Only managers can start the bracket.")
        if t['state'] != 'registering': return await ctx.send("❌ Bracket is already started.")
        if len(t['players']) < 2: return await ctx.send("❌ Need at least 2 players to start.")

        # Setup Power of 2 Size
        players = t['players'].copy()
        random.shuffle(players)
        N = self.next_power_of_2(len(players))
        
        # Pad with BYEs
        while len(players) < N:
            players.append("BYE")
        
        # Initialize matches (1 to N-1)
        t['matches'] = {str(x): {'p1': None, 'p2': None, 'winner': None} for x in range(1, N)}
        
        # Populate leaves (Round 1)
        for i in range(N // 2):
            match_id = (N // 2) + i
            t['matches'][str(match_id)]['p1'] = players[2*i]
            t['matches'][str(match_id)]['p2'] = players[2*i + 1]

        t['state'] = 'active'
        self.save_data()

        # Resolve initial BYEs
        active_matches = []
        for i in range(N // 2):
            match_id = (N // 2) + i
            m = t['matches'][str(match_id)]
            if m['p1'] == 'BYE':
                active_matches.extend(self.advance_winner(t, match_id, m['p2']))
            elif m['p2'] == 'BYE':
                active_matches.extend(self.advance_winner(t, match_id, m['p1']))
            else:
                active_matches.append(match_id)

        self.save_data()
        
        # Send output
        await ctx.send(f"🏆 Bracket **{name}** has started!")
        await self.status(ctx, name)
        await self.announce_matches(ctx, t, active_matches)

    @bracket.command(brief='Report the winner of a match')
    async def report(self, ctx, name: str, winner: discord.Member):
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if not self.is_manager(ctx, t): return await ctx.send("❌ Only managers can report scores.")
        if t['state'] != 'active': return await ctx.send("❌ Bracket is not currently active.")

        # Find the active match containing the winner
        active_match = None
        for mid, m in t['matches'].items():
            if m['winner'] is None and winner.id in (m['p1'], m['p2']):
                active_match = int(mid)
                break
                
        if not active_match:
            return await ctx.send(f"❌ Could not find an active match for {winner.display_name}.")

        # Advance the winner
        new_matches = self.advance_winner(t, active_match, winner.id)
        self.save_data()

        await ctx.send(f"✅ Reported win for **{winner.display_name}**!")
        await self.status(ctx, name)
        
        if t['state'] == 'finished':
            await ctx.send(f"🎉 **TOURNAMENT FINISHED!** Congratulations <@{winner.id}>! 🎉")
        else:
            await self.announce_matches(ctx, t, new_matches)

    @bracket.command(brief='Show current bracket image')
    async def status(self, ctx, name: str):
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if t['state'] == 'registering':
            return await ctx.send(f"Bracket `{name}` is registering. Players: {len(t['players'])}")

        buffer = await self.bot.loop.run_in_executor(None, self.generate_bracket_image, t)
        file = discord.File(buffer, filename="bracket.png")
        embed = discord.Embed(title=f"Bracket: {name} ({t['state'].upper()})", color=0x7289da)
        embed.set_image(url="attachment://bracket.png")
        await ctx.send(embed=embed, file=file)

async def setup(bot):
    await bot.add_cog(Brackets(bot))
