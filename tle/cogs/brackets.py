import os
import json
import math
import random
import io
import itertools

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

DATA_FILE = "data/brackets.json"
VALID_TYPES = ['single_elimination', 'double_elimination', 'point_system', 'round_robin', 'swiss']
TYPE_MAP = {
    '1': 'single_elimination',
    '2': 'double_elimination',
    '3': 'point_system',
    '4': 'round_robin',
    '5': 'swiss'
}

class Brackets(commands.Cog):
    """Tournament and Bracket management system."""
    
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

    # --- DUEL TRACKING LISTENER ---
    
    @commands.Cog.listener()
    async def on_duel_complete(self, duel_type, winner_id: int, loser_id: int):
        """
        Listens for the custom 'duel_complete' event from tle/cogs/duel.py.
        """
        for name, t in self.tournaments.items():
            if t['state'] != 'active':
                continue
                
            match_id_to_resolve = None
            
            # Find if these two players have a pending match in this bracket
            for mid, m in t.get('matches', {}).items():
                if m['winner'] is None:
                    participants = [m.get('p1'), m.get('p2')]
                    if winner_id in participants and loser_id in participants:
                        match_id_to_resolve = mid
                        break
            
            # Point system doesn't need predefined matches, just general tracking
            if t['type'] == 'point_system':
                if winner_id in t['players'] and loser_id in t['players']:
                    t.setdefault('scores', {})
                    t['scores'][str(winner_id)] = t['scores'].get(str(winner_id), 0) + 1
                    self.save_data()
            
            elif match_id_to_resolve is not None:
                # Process the win silently in the background
                await self.process_win(name, t, match_id_to_resolve, winner_id)

    # --- MATCH PROCESSING LOGIC ---

    async def process_win(self, name, t, match_id, winner_id):
        """Core logic to process a win based on the tournament type."""
        t['matches'][str(match_id)]['winner'] = winner_id
        b_type = t['type']
        new_matches = []

        if b_type == 'single_elimination':
            new_matches = self.advance_single_elim(t, int(match_id), winner_id)
        
        elif b_type in ['swiss', 'double_elimination']:
            # Update scores/losses
            loser_id = t['matches'][str(match_id)]['p1'] if t['matches'][str(match_id)]['p2'] == winner_id else t['matches'][str(match_id)]['p2']
            t['scores'][str(winner_id)]['wins'] += 1
            t['scores'][str(loser_id)]['losses'] += 1
            
            # Check if round is complete
            if all(m['winner'] is not None for m in t['matches'].values() if m.get('round') == t.get('current_round', 1)):
                new_matches = self.generate_next_round(t)
        
        elif b_type == 'round_robin':
            t['scores'][str(winner_id)] += 1
            if all(m['winner'] is not None for m in t['matches'].values()):
                t['state'] = 'finished'

        self.save_data()

    def advance_single_elim(self, t, match_id, winner_id):
        """Advances a winner up the single elimination tree."""
        str_id = str(match_id)
        
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

        if parent['p1'] is not None and parent['p2'] is not None:
            if parent['p1'] == 'BYE':
                return self.advance_single_elim(t, parent_id, parent['p2'])
            elif parent['p2'] == 'BYE':
                return self.advance_single_elim(t, parent_id, parent['p1'])
            else:
                return [parent_id]
        return []

    def generate_next_round(self, t):
        """Generates the next round for Swiss or Double Elimination."""
        
        # Check if Swiss reached its max rounds based on player count
        if t['type'] == 'swiss':
            # e.g., 8 players = 3 rounds, 16 players = 4 rounds
            max_rounds = max(1, math.ceil(math.log2(len(t['players']))))
            if t.get('current_round', 0) >= max_rounds:
                t['state'] = 'finished'
                return []

        t['current_round'] = t.get('current_round', 0) + 1
        active_players = []
        
        if t['type'] == 'double_elimination':
            # Filter out players with 2+ losses
            active_players = [int(p) for p, stats in t['scores'].items() if stats['losses'] < 2]
        else:
            # Swiss
            active_players = [int(p) for p in t['scores'].keys()]

        if len(active_players) <= 1:
            t['state'] = 'finished'
            return []

        # Sort by wins (Swiss) or by losses then wins (Double Elim)
        if t['type'] == 'double_elimination':
            active_players.sort(key=lambda x: (t['scores'][str(x)]['losses'], -t['scores'][str(x)]['wins']))
        else:
            active_players.sort(key=lambda x: -t['scores'][str(x)]['wins'])

        new_match_ids = []
        base_idx = len(t.get('matches', {}))
        
        # Pair up adjacently
        for i in range(0, len(active_players), 2):
            if i + 1 < len(active_players):
                p1 = active_players[i]
                p2 = active_players[i+1]
                mid = str(base_idx + 1)
                t['matches'][mid] = {'p1': p1, 'p2': p2, 'winner': None, 'round': t['current_round']}
                new_match_ids.append(mid)
                base_idx += 1
            else:
                # Odd man out gets a BYE
                t['scores'][str(active_players[i])]['wins'] += 1

        return new_match_ids

    # --- VISUALS & FORMATTING ---

    def generate_bracket_image(self, t):
        """Uses Pillow to draw the single elimination bracket graph."""
        BOX_WIDTH = 220
        BOX_HEIGHT = 60
        COL_SPACING = 300
        ROW_SPACING = 100

        N = len(t['matches']) + 1
        D = int(math.log2(N))

        img_width = D * COL_SPACING + 50
        img_height = (N // 2) * ROW_SPACING + 50
        
        image = Image.new('RGB', (img_width, img_height), (44, 47, 51))
        draw = ImageDraw.Draw(image)

        font_path = os.path.join('tle', 'assets', 'fonts', 'NotoSans-Bold.ttf')
        try:
            font = ImageFont.truetype(font_path, 16)
        except IOError:
            font = ImageFont.load_default()

        Y = {}
        for i in range(N // 2):
            Y[(N // 2) + i] = i * ROW_SPACING + 25

        for x in range(N // 2 - 1, 0, -1):
            Y[x] = (Y[2*x] + Y[2*x + 1]) / 2

        X = {}
        for x in range(1, N):
            d = int(math.log2(x))
            X[x] = (D - 1 - d) * COL_SPACING + 25

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

        for x in range(1, N):
            match = t['matches'][str(x)]
            x_pos = X[x]
            y_pos = Y[x]

            draw.rectangle([x_pos, y_pos, x_pos + BOX_WIDTH, y_pos + BOX_HEIGHT], fill=(35, 39, 42), outline=(153, 170, 181), width=2)
            draw.line([(x_pos, y_pos + BOX_HEIGHT//2), (x_pos + BOX_WIDTH, y_pos + BOX_HEIGHT//2)], fill=(153, 170, 181), width=1)

            def get_name(user_id):
                if user_id is None: return "TBD"
                if user_id == "BYE": return "BYE"
                user = self.bot.get_user(user_id)
                return user.display_name if user else f"User {user_id}"

            p1_name = get_name(match.get('p1'))
            p2_name = get_name(match.get('p2'))

            color1 = (255, 255, 255)
            color2 = (255, 255, 255)
            if match.get('winner') == match.get('p1') and match.get('p1') not in (None, 'BYE'):
                color1 = (67, 181, 129)
            elif match.get('winner') == match.get('p2') and match.get('p2') not in (None, 'BYE'):
                color2 = (67, 181, 129)

            draw.text((x_pos + 10, y_pos + 5), p1_name, fill=color1, font=font)
            draw.text((x_pos + 10, y_pos + BOX_HEIGHT//2 + 5), p2_name, fill=color2, font=font)

        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

    def generate_leaderboard_embed(self, t):
        """Generates a text-based embed leaderboard for point/round-robin/swiss formats."""
        embed = discord.Embed(title=f"Tournament: {t['name']} ({t['type'].replace('_', ' ').title()})", color=0x7289da)
        embed.description = f"**State:** {t['state'].upper()}"
        
        if t['type'] == 'point_system' or t['type'] == 'round_robin':
            scores = t.get('scores', {})
            sorted_players = sorted(t['players'], key=lambda p: scores.get(str(p), 0), reverse=True)
            board = ""
            for i, p in enumerate(sorted_players, 1):
                board += f"**{i}.** <@{p}> — {scores.get(str(p), 0)} pts\n"
            embed.add_field(name="Standings", value=board or "No matches yet.")

        elif t['type'] in ['swiss', 'double_elimination']:
            scores = t.get('scores', {})
            # Sort by wins, then fewest losses
            sorted_players = sorted(t['players'], key=lambda p: (scores.get(str(p), {}).get('wins', 0), -scores.get(str(p), {}).get('losses', 0)), reverse=True)
            board = ""
            for i, p in enumerate(sorted_players, 1):
                stats = scores.get(str(p), {'wins': 0, 'losses': 0})
                board += f"**{i}.** <@{p}> — {stats['wins']} W / {stats['losses']} L\n"
            embed.add_field(name="Standings", value=board or "No matches yet.", inline=False)
            
            # Show current round matches
            current_round = t.get('current_round', 1)
            matches_text = ""
            for m in t.get('matches', {}).values():
                if m.get('round') == current_round:
                    w_text = f"(Winner: <@{m['winner']}>)" if m.get('winner') else "[Pending]"
                    matches_text += f"<@{m['p1']}> vs <@{m['p2']}> {w_text}\n"
            if matches_text:
                embed.add_field(name=f"Round {current_round} Matches", value=matches_text, inline=False)

        return embed

    async def announce_matches(self, ctx, t, match_ids):
        """Pings the players who are paired up."""
        for mid in match_ids:
            match = t['matches'][str(mid)]
            if match.get('p1') not in (None, 'BYE') and match.get('p2') not in (None, 'BYE'):
                await ctx.send(f"⚔️ **Match Time!** <@{match['p1']}> 🆚 <@{match['p2']}>\n*Managers can report the winner using `;bracket report {t['name']} @winner` or complete a TLE duel!*")

    # --- DISCORD COMMANDS ---

    @commands.group(brief='Tournament bracket commands', invoke_without_command=True)
    async def bracket(self, ctx):
        """
        Main command group for managing tournaments and brackets.
        
        Use `;help bracket <subcommand>` for more info on a specific command.
        """
        await ctx.send_help(ctx.command)

    @bracket.command(brief='Create a new bracket.')
    async def create(self, ctx, name: str, b_type: str = 'single_elimination', *managers: discord.Member):
        """
        Creates a new tournament bracket.
        
        <name>: The name of the bracket (use quotes if it contains spaces).
        <b_type>: The type of the tournament.
                  Valid options: 
                  1 or single_elimination
                  2 or double_elimination
                  3 or point_system
                  4 or round_robin
                  5 or swiss
        [managers]: (Optional) Mention users to give them admin rights over the bracket.
        """
        if name in self.tournaments:
            return await ctx.send(f"❌ Bracket `{name}` already exists!")
        
        # Map number shortcuts to the full name
        if b_type in TYPE_MAP:
            b_type = TYPE_MAP[b_type]
            
        if b_type not in VALID_TYPES:
            return await ctx.send("❌ Invalid type. Valid types/numbers:\n`1` Single Elim\n`2` Double Elim\n`3` Point System\n`4` Round Robin\n`5` Swiss")
            
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
        await ctx.send(f"✅ Created {b_type.replace('_', ' ')} bracket `{name}`. Type `;bracket register \"{name}\"` to join!")

    @bracket.command(brief='List all brackets and their status.')
    async def list(self, ctx):
        """
        Shows a list of all existing brackets, their types, and whether they are finished.
        """
        if not self.tournaments:
            return await ctx.send("No brackets currently exist. Create one with `;bracket create`!")

        embed = discord.Embed(title="🏆 Tournament Brackets", color=0x7289da)
        for name, t in self.tournaments.items():
            b_type = t.get('type', 'Unknown').replace('_', ' ').title()
            state = t.get('state', 'Unknown').capitalize()
            players_count = len(t.get('players', []))
            
            status_emoji = "🟢" if state.lower() == "active" else "🔴" if state.lower() == "finished" else "🟡"
            
            embed.add_field(
                name=f"{status_emoji} {name}", 
                value=f"**Type:** {b_type} | **Status:** {state} | **Players:** {players_count}", 
                inline=False
            )
        
        await ctx.send(embed=embed)

    @bracket.command(brief='Delete a bracket entirely.')
    async def delete(self, ctx, name: str):
        """
        Deletes an existing bracket.
        
        Requires you to be a server administrator or a designated manager for this bracket.
        """
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if not self.is_manager(ctx, t): return await ctx.send("❌ Only managers can delete the bracket.")
        
        del self.tournaments[name]
        self.save_data()
        await ctx.send(f"🗑️ Successfully deleted the bracket `{name}`.")

    @bracket.command(brief='Add new managers to an existing bracket.')
    async def addmanager(self, ctx, name: str, *new_managers: discord.Member):
        """
        Adds new managers to a bracket.
        
        <name>: The name of the bracket (use quotes if it contains spaces).
        [new_managers...]: Mention the users you want to add as managers.
        """
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if not self.is_manager(ctx, t): return await ctx.send("❌ Only existing managers can add new managers.")
        
        if not new_managers:
            return await ctx.send("❌ You must mention at least one user to add as a manager.")

        current_managers = set(t['managers'])
        added_managers = []
        for m in new_managers:
            if m.id not in current_managers:
                current_managers.add(m.id)
                added_managers.append(m.display_name)
        
        t['managers'] = list(current_managers)
        self.save_data()
        
        if added_managers:
            await ctx.send(f"✅ Added **{', '.join(added_managers)}** as manager(s) for `{name}`.")
        else:
            await ctx.send("⚠️ All mentioned users are already managers.")

    @bracket.command(brief='Register for a bracket.')
    async def register(self, ctx, name: str):
        """
        Registers you for an upcoming bracket.
        
        The bracket must be in the 'registering' state (not yet started).
        """
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if t['state'] != 'registering': return await ctx.send("❌ Registration is closed.")
        if ctx.author.id in t['players']: return await ctx.send("❌ You are already registered.")

        t['players'].append(ctx.author.id)
        self.save_data()
        await ctx.send(f"✅ Registered **{ctx.author.display_name}** for `{name}`. Total players: {len(t['players'])}")

    @bracket.command(brief='Unregister a user from a bracket.')
    async def unregister(self, ctx, name: str, user: discord.Member = None):
        """
        Removes a user from a bracket.
        
        You can use this to remove yourself.
        Managers can mention another [user] to remove them forcefully.
        """
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

    @bracket.command(brief='Starts the bracket.')
    async def start(self, ctx, name: str):
        """
        Closes registration and starts the bracket.
        
        Requires you to be a bracket manager. 
        Depending on the bracket type, this will randomize seeds, 
        generate matches, pad with BYEs, and announce the first round!
        """
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if not self.is_manager(ctx, t): return await ctx.send("❌ Only managers can start the bracket.")
        if t['state'] != 'registering': return await ctx.send("❌ Bracket is already started.")
        if len(t['players']) < 2: return await ctx.send("❌ Need at least 2 players to start.")

        players = t['players'].copy()
        random.shuffle(players)
        t['state'] = 'active'
        active_matches = []

        if t['type'] == 'single_elimination':
            N = self.next_power_of_2(len(players))
            while len(players) < N:
                players.append("BYE")
            
            t['matches'] = {str(x): {'p1': None, 'p2': None, 'winner': None} for x in range(1, N)}
            for i in range(N // 2):
                match_id = (N // 2) + i
                t['matches'][str(match_id)]['p1'] = players[2*i]
                t['matches'][str(match_id)]['p2'] = players[2*i + 1]

            for i in range(N // 2):
                match_id = (N // 2) + i
                m = t['matches'][str(match_id)]
                if m['p1'] == 'BYE':
                    active_matches.extend(self.advance_single_elim(t, match_id, m['p2']))
                elif m['p2'] == 'BYE':
                    active_matches.extend(self.advance_single_elim(t, match_id, m['p1']))
                else:
                    active_matches.append(match_id)

        elif t['type'] == 'point_system':
            t['scores'] = {str(p): 0 for p in players}

        elif t['type'] == 'round_robin':
            t['scores'] = {str(p): 0 for p in players}
            pairs = list(itertools.combinations(players, 2))
            t['matches'] = {str(i+1): {'p1': p1, 'p2': p2, 'winner': None} for i, (p1, p2) in enumerate(pairs)}
            active_matches = list(range(1, len(pairs) + 1))

        elif t['type'] in ['swiss', 'double_elimination']:
            t['scores'] = {str(p): {'wins': 0, 'losses': 0} for p in players}
            active_matches = self.generate_next_round(t)

        self.save_data()
        
        await ctx.send(f"🏆 Bracket **{name}** has started!")
        await self.status(ctx, name)
        if active_matches:
            await self.announce_matches(ctx, t, active_matches)

    @bracket.command(brief='Manually report the winner of a match.')
    async def report(self, ctx, name: str, winner: discord.Member):
        """
        Manually forces a win for a specific player.
        
        Requires you to be a manager. It will automatically find 
        the active pending match for that player and advance them.
        *Note: Standard TLE duels will automatically report scores!*
        """
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if not self.is_manager(ctx, t): return await ctx.send("❌ Only managers can manually report scores.")
        if t['state'] != 'active': return await ctx.send("❌ Bracket is not currently active.")

        if t['type'] == 'point_system':
            t['scores'][str(winner.id)] = t['scores'].get(str(winner.id), 0) + 1
            self.save_data()
            await ctx.send(f"✅ Added 1 point for **{winner.display_name}**!")
            return await self.status(ctx, name)

        # Find the active match containing the winner for other types
        active_match = None
        current_round = t.get('current_round')
        for mid, m in t['matches'].items():
            if m['winner'] is None and winner.id in (m.get('p1'), m.get('p2')):
                # For round-based, only allow reporting current round matches
                if current_round and m.get('round') != current_round:
                    continue
                active_match = mid
                break
                
        if not active_match:
            return await ctx.send(f"❌ Could not find an active pending match for {winner.display_name}.")

        await self.process_win(name, t, active_match, winner.id)

        await ctx.send(f"✅ Reported win for **{winner.display_name}**!")
        await self.status(ctx, name)
        
        if t['state'] == 'finished':
            await ctx.send(f"🎉 **TOURNAMENT FINISHED!** 🎉")

    @bracket.command(brief='Show current bracket image or leaderboard.')
    async def status(self, ctx, name: str):
        """
        Displays the current status of the bracket.
        
        Generates a visual bracket tree for Single Elimination, 
        or an embedded leaderboard/standings page for other types.
        """
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if t['state'] == 'registering':
            return await ctx.send(f"Bracket `{name}` is registering. Players: {len(t['players'])}")

        if t['type'] == 'single_elimination':
            buffer = await self.bot.loop.run_in_executor(None, self.generate_bracket_image, t)
            file = discord.File(buffer, filename="bracket.png")
            embed = discord.Embed(title=f"Bracket: {name} ({t['state'].upper()})", color=0x7289da)
            embed.set_image(url="attachment://bracket.png")
            await ctx.send(embed=embed, file=file)
        else:
            embed = self.generate_leaderboard_embed(t)
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Brackets(bot))
