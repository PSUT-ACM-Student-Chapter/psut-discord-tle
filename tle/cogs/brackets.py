import os
import json
import math
import random
import io
import itertools

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

class BracketRenderer:
    """Unified UI engine for drawing brackets and tournament dashboards."""
    def __init__(self, tournament, names_dict):
        self.t = tournament
        self.names = names_dict
        self.b_type = tournament.get('type')
        
        # UI Theme (Discord Modern Dark)
        self.bg_color = (43, 45, 49)       # Base background
        self.box_color = (49, 51, 56)      # Match box background
        self.box_outline = (30, 31, 34)    # Match box inner border
        self.line_color = (88, 101, 242)   # Blurple connections
        self.text_color = (242, 243, 245)  # White text
        self.tbd_color = (128, 132, 142)   # Gray TBD text
        self.win_outline = (87, 242, 135)  # Green win outline
        self.win_text = (87, 242, 135)     # Green win text
        self.loss_text = (237, 66, 69)     # Red loss text
        
        # Dimensions
        self.box_w = 220
        self.box_h = 64
        self.gap_x = 60
        self.gap_y = 24
        
        # Fonts
        try:
            self.font = ImageFont.truetype("tle/assets/fonts/NotoSans-Bold.ttf", 16)
            self.title_font = ImageFont.truetype("tle/assets/fonts/NotoSans-Bold.ttf", 24)
        except:
            self.font = ImageFont.load_default()
            self.title_font = ImageFont.load_default()

    def draw_rounded_rect(self, draw, xy, radius, fill, outline, width=2):
        try:
            draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
        except AttributeError:
            draw.rectangle(xy, fill=fill, outline=outline, width=width)

    def get_name(self, player_id):
        if player_id in (None, "TBD", "None"): return "TBD"
        if player_id == "BYE": return "BYE"
        name = self.names.get(str(player_id), f"User {player_id}")
        return name[:20] + "..." if len(name) > 20 else name

    def draw_match_box(self, draw, x, y, match):
        p1 = match.get('p1')
        p2 = match.get('p2')
        winner = match.get('winner')
        
        outline = self.win_outline if winner else self.box_outline
        self.draw_rounded_rect(draw, [x, y, x + self.box_w, y + self.box_h], 8, self.box_color, outline, 2)
        
        # Separator line
        draw.line([(x, y + self.box_h/2), (x + self.box_w, y + self.box_h/2)], fill=self.box_outline, width=2)
        
        # Draw players
        for i, pid in enumerate([p1, p2]):
            name = self.get_name(pid)
            is_winner = (winner == pid and pid is not None)
            is_loser = (winner is not None and not is_winner and pid not in (None, "BYE"))
            
            color = self.win_text if is_winner else self.loss_text if is_loser else self.text_color
            if name in ("TBD", "BYE"): color = self.tbd_color
            
            text_y = y + 8 if i == 0 else y + self.box_h/2 + 8
            draw.text((x + 12, text_y), name, fill=color, font=self.font)
            
            if is_winner:
                draw.text((x + self.box_w - 28, text_y), "🏆", fill=self.win_text, font=self.font)

    def draw_single_elim(self):
        """Draws a strict binary tree bracket layout."""
        matches = self.t.get('matches', {})
        if not matches: return None
        
        match_ids = [int(k) for k in matches.keys()]
        max_id = max(match_ids)
        max_depth = int(math.log2(max_id)) if match_ids else 0
        
        def get_depth(mid):
            return int(math.log2(mid)) if mid > 0 else 0
            
        x_coords = {}
        y_coords = {}
        
        # Calculate Coordinates 
        leaf_nodes = sorted([mid for mid in match_ids if get_depth(mid) == max_depth])
        for idx, mid in enumerate(leaf_nodes):
            x_coords[mid] = 40
            y_coords[mid] = 80 + idx * (self.box_h + self.gap_y)
            
        for d in range(max_depth - 1, -1, -1):
            nodes = [mid for mid in match_ids if get_depth(mid) == d]
            for mid in nodes:
                r = max_depth - d
                x_coords[mid] = 40 + r * (self.box_w + self.gap_x)
                
                # Children in binary heap math
                child1, child2 = mid * 2, mid * 2 + 1
                if child1 in y_coords and child2 in y_coords:
                    y_coords[mid] = (y_coords[child1] + y_coords[child2]) / 2
                elif child1 in y_coords:
                    y_coords[mid] = y_coords[child1]
                else:
                    y_coords[mid] = 80
                    
        max_x = max(x_coords.values()) + self.box_w + 80 if x_coords else 800
        max_y = max(y_coords.values()) + self.box_h + 80 if y_coords else 600
        
        img = Image.new('RGB', (int(max_x), int(max_y)), self.bg_color)
        draw = ImageDraw.Draw(img)
        
        draw.text((40, 24), f"🏆 {self.t['name']} - Single Elimination", fill=self.text_color, font=self.title_font)
        
        # Draw connecting lines first
        for mid in match_ids:
            if mid == 1: continue # Final match doesn't point to anything
            parent = mid // 2
            if parent in x_coords and parent in y_coords:
                start_x = x_coords[mid] + self.box_w
                start_y = y_coords[mid] + self.box_h / 2
                end_x = x_coords[parent]
                end_y = y_coords[parent] + self.box_h / 2
                mid_x = start_x + self.gap_x / 2
                
                draw.line([(start_x, start_y), (mid_x, start_y)], fill=self.line_color, width=3)
                draw.line([(mid_x, start_y), (mid_x, end_y)], fill=self.line_color, width=3)
                draw.line([(mid_x, end_y), (end_x, end_y)], fill=self.line_color, width=3)
                
        # Draw match boxes over the lines
        for mid in match_ids:
            self.draw_match_box(draw, x_coords[mid], y_coords[mid], matches[str(mid)])
            
        return img

    def draw_standings_dashboard(self):
        """Draws a beautiful dashboard for Double Elimination, Swiss, and Point Systems."""
        scores = self.t.get('scores', {})
        players = self.t.get('players', [])
        b_type = self.b_type
        
        if b_type in ['point_system', 'round_robin']:
            sorted_players = sorted(players, key=lambda p: scores.get(str(p), 0), reverse=True)
        else:
            sorted_players = sorted(players, key=lambda p: (scores.get(str(p), {}).get('wins', 0), -scores.get(str(p), {}).get('losses', 0)), reverse=True)
            
        margin = 40
        header_h = 80
        row_h = 48
        col_w_rank = 60
        col_w_name = 260
        col_w_score = 160
        col_w_status = 120
        
        table_w = col_w_rank + col_w_name + col_w_score
        if b_type in ['double_elimination', 'swiss']:
            table_w += col_w_status
            
        match_start_x = margin * 2 + table_w
        match_col_w = self.box_w + self.gap_x
        
        # Organize matches by round
        rounds = {}
        for m in self.t.get('matches', {}).values():
            r = m.get('round', 1)
            rounds.setdefault(r, []).append(m)
            
        num_rounds = max(rounds.keys()) if rounds else 1
        max_matches = max([len(rm) for rm in rounds.values()]) if rounds else 0
        
        # Calculate Canvas Dimensions
        img_w = max(1000, match_start_x + num_rounds * match_col_w + margin)
        img_h = max(600, header_h + margin + max(len(sorted_players) * row_h, max_matches * (self.box_h + self.gap_y)))
        
        img = Image.new('RGB', (img_w, img_h), self.bg_color)
        draw = ImageDraw.Draw(img)
        
        draw.text((margin, 24), f"🏆 {self.t['name']} - {b_type.replace('_', ' ').title()}", fill=self.text_color, font=self.title_font)
        
        # Draw Table Headers
        y = header_h + margin
        draw.text((margin, y), "Rank", fill=self.tbd_color, font=self.font)
        draw.text((margin + col_w_rank, y), "Player", fill=self.tbd_color, font=self.font)
        draw.text((margin + col_w_rank + col_w_name, y), "Score", fill=self.tbd_color, font=self.font)
        if b_type in ['double_elimination', 'swiss']:
            draw.text((margin + col_w_rank + col_w_name + col_w_score, y), "Status", fill=self.tbd_color, font=self.font)
            
        y += row_h
        
        # Draw Players
        for i, p in enumerate(sorted_players):
            row_bg = self.box_color if i % 2 == 0 else self.bg_color
            draw.rectangle([margin, y - 10, margin + table_w, y + row_h - 10], fill=row_bg)
            
            draw.text((margin, y), f"#{i+1}", fill=self.text_color, font=self.font)
            draw.text((margin + col_w_rank, y), self.get_name(p), fill=self.text_color, font=self.font)
            
            if b_type in ['point_system', 'round_robin']:
                score_str = f"{scores.get(str(p), 0)} pts"
            else:
                stats = scores.get(str(p), {'wins': 0, 'losses': 0})
                score_str = f"{stats['wins']} W - {stats['losses']} L"
            draw.text((margin + col_w_rank + col_w_name, y), score_str, fill=self.win_text, font=self.font)
            
            if b_type in ['double_elimination', 'swiss']:
                losses = scores.get(str(p), {}).get('losses', 0)
                status = "Eliminated" if losses >= 2 else "Active"
                s_color = self.loss_text if losses >= 2 else self.win_text
                draw.text((margin + col_w_rank + col_w_name + col_w_score, y), status, fill=s_color, font=self.font)
                
            y += row_h
            
        # Draw Matches Right Side
        for r in sorted(rounds.keys()):
            col_x = match_start_x + (r - 1) * match_col_w
            draw.text((col_x, header_h + margin), f"Round {r}", fill=self.line_color, font=self.font)
            
            m_y = header_h + margin + row_h
            for match in rounds[r]:
                self.draw_match_box(draw, col_x, m_y, match)
                m_y += self.box_h + self.gap_y
                
        return img


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
        for name, t in self.tournaments.items():
            if t['state'] != 'active':
                continue
                
            match_id_to_resolve = None
            
            for mid, m in t.get('matches', {}).items():
                if m['winner'] is None:
                    participants = [m.get('p1'), m.get('p2')]
                    if winner_id in participants and loser_id in participants:
                        match_id_to_resolve = mid
                        break
            
            channel_id = t.get('channel_id')
            channel = self.bot.get_channel(channel_id) if channel_id else None

            if t['type'] == 'point_system':
                if winner_id in t['players'] and loser_id in t['players']:
                    t.setdefault('scores', {})
                    t['scores'][str(winner_id)] = t['scores'].get(str(winner_id), 0) + 1
                    self.save_data()
                    
                    if channel:
                        await channel.send(f"⚔️ **{name} Update!** <@{winner_id}> won a duel against <@{loser_id}> and earned 1 point!")
                        await self.send_status_image(channel, name, t)
            
            elif match_id_to_resolve is not None:
                new_matches = await self.process_win(name, t, match_id_to_resolve, winner_id)
                
                if channel:
                    await channel.send(f"⚔️ **{name} Update!** <@{winner_id}> defeated <@{loser_id}>!")
                    await self.send_status_image(channel, name, t)
                    
                    if t['state'] == 'finished':
                        await channel.send(f"🎉 **TOURNAMENT FINISHED!** 🎉")
                    elif new_matches:
                        await self.announce_matches(channel, t, new_matches)

    # --- MATCH PROCESSING LOGIC ---

    async def process_win(self, name, t, match_id, winner_id):
        t['matches'][str(match_id)]['winner'] = winner_id
        b_type = t['type']
        new_matches = []

        if b_type == 'single_elimination':
            new_matches = self.advance_single_elim(t, int(match_id), winner_id)
        
        elif b_type in ['swiss', 'double_elimination']:
            loser_id = t['matches'][str(match_id)]['p1'] if t['matches'][str(match_id)]['p2'] == winner_id else t['matches'][str(match_id)]['p2']
            t['scores'][str(winner_id)]['wins'] += 1
            t['scores'][str(loser_id)]['losses'] += 1
            
            if all(m['winner'] is not None for m in t['matches'].values() if m.get('round') == t.get('current_round', 1)):
                new_matches = self.generate_next_round(t)
        
        elif b_type == 'round_robin':
            t['scores'][str(winner_id)] += 1
            if all(m['winner'] is not None for m in t['matches'].values()):
                t['state'] = 'finished'

        self.save_data()
        return new_matches

    def advance_single_elim(self, t, match_id, winner_id):
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
        if t['type'] == 'swiss':
            max_rounds = max(1, math.ceil(math.log2(len(t['players']))))
            if t.get('current_round', 0) >= max_rounds:
                t['state'] = 'finished'
                return []

        t['current_round'] = t.get('current_round', 0) + 1
        active_players = []
        
        if t['type'] == 'double_elimination':
            active_players = [int(p) for p, stats in t['scores'].items() if stats['losses'] < 2]
        else:
            active_players = [int(p) for p in t['scores'].keys()]

        if len(active_players) <= 1:
            t['state'] = 'finished'
            return []

        if t['type'] == 'double_elimination':
            active_players.sort(key=lambda x: (t['scores'][str(x)]['losses'], -t['scores'][str(x)]['wins']))
        else:
            active_players.sort(key=lambda x: -t['scores'][str(x)]['wins'])

        new_match_ids = []
        base_idx = len(t.get('matches', {}))
        
        for i in range(0, len(active_players), 2):
            if i + 1 < len(active_players):
                p1 = active_players[i]
                p2 = active_players[i+1]
                mid = str(base_idx + 1)
                t['matches'][mid] = {'p1': p1, 'p2': p2, 'winner': None, 'round': t['current_round']}
                new_match_ids.append(mid)
                base_idx += 1
            else:
                t['scores'][str(active_players[i])]['wins'] += 1

        return new_match_ids

    # --- VISUALS & FORMATTING ---

    async def get_image_buffer(self, t):
        names = {}
        for p in t.get('players', []):
            user = self.bot.get_user(int(p))
            if not user:
                try:
                    user = await self.bot.fetch_user(int(p))
                except discord.NotFound:
                    pass
            names[str(p)] = user.display_name if user else f"User {p}"
            
        names["BYE"] = "BYE"
        names["TBD"] = "TBD"

        def render():
            renderer = BracketRenderer(t, names)
            if t.get('type') == 'single_elimination':
                img = renderer.draw_single_elim()
            else:
                img = renderer.draw_standings_dashboard()
                
            if not img:
                img = Image.new('RGB', (400, 100), (43, 45, 49))
                d = ImageDraw.Draw(img)
                font = ImageFont.load_default()
                d.text((20, 40), "Not enough data to draw bracket.", fill=(255,255,255), font=font)

            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            return buffer
            
        return await self.bot.loop.run_in_executor(None, render)

    async def send_status_image(self, channel, name, t):
        if t['state'] == 'registering':
            await channel.send(f"Bracket `{name}` is registering. Players: {len(t['players'])}")
            return
            
        buffer = await self.get_image_buffer(t)
        file = discord.File(fp=buffer, filename='bracket.png')
        
        embed = discord.Embed(
            title=f"🏆 Tournament: {name}",
            color=0x5865F2
        )
        embed.set_image(url="attachment://bracket.png")
        await channel.send(embed=embed, file=file)

    async def announce_matches(self, ctx_or_channel, t, match_ids):
        for mid in match_ids:
            match = t['matches'][str(mid)]
            if match.get('p1') not in (None, 'BYE') and match.get('p2') not in (None, 'BYE'):
                await ctx_or_channel.send(f'⚔️ **Match Time!** <@{match["p1"]}> 🆚 <@{match["p2"]}>\n*Managers can report the winner using `;bracket report "{t["name"]}" @winner` or complete a TLE duel!*')

    # --- DISCORD COMMANDS ---

    @commands.group(brief='Tournament bracket commands', invoke_without_command=True)
    async def bracket(self, ctx):
        await ctx.send_help(ctx.command)

    @bracket.command(brief='Create a new bracket.')
    async def create(self, ctx, name: str, b_type: str = 'single_elimination', *managers: discord.Member):
        if name in self.tournaments:
            return await ctx.send(f"❌ Bracket `{name}` already exists!")
        
        if b_type in TYPE_MAP:
            b_type = TYPE_MAP[b_type]
            
        if b_type not in VALID_TYPES:
            return await ctx.send("❌ Invalid type. Valid types:\n`1` Single Elim\n`2` Double Elim\n`3` Point System\n`4` Round Robin\n`5` Swiss")
            
        manager_ids = [ctx.author.id] + [m.id for m in managers]
        self.tournaments[name] = {
            'name': name,
            'type': b_type,
            'state': 'registering',
            'managers': list(set(manager_ids)),
            'players': [],
            'matches': {},
            'channel_id': ctx.channel.id
        }
        self.save_data()
        await ctx.send(f"✅ Created {b_type.replace('_', ' ')} bracket `{name}`. Type `;bracket register \"{name}\"` to join!")

    @bracket.command(brief='List all brackets and their status.')
    async def list(self, ctx):
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
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if not self.is_manager(ctx, t): return await ctx.send("❌ Only managers can delete the bracket.")
        
        del self.tournaments[name]
        self.save_data()
        await ctx.send(f"🗑️ Successfully deleted the bracket `{name}`.")

    @bracket.command(brief='Add new managers to an existing bracket.')
    async def addmanager(self, ctx, name: str, *new_managers: discord.Member):
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
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if t['state'] != 'registering': return await ctx.send("❌ Registration is closed.")
        if ctx.author.id in t['players']: return await ctx.send("❌ You are already registered.")

        t['players'].append(ctx.author.id)
        self.save_data()
        await ctx.send(f"✅ Registered **{ctx.author.display_name}** for `{name}`. Total players: {len(t['players'])}")

    @bracket.command(brief='Unregister a user from a bracket.')
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

    @bracket.command(brief='Starts the bracket.')
    async def start(self, ctx, name: str):
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if not self.is_manager(ctx, t): return await ctx.send("❌ Only managers can start the bracket.")
        if t['state'] != 'registering': return await ctx.send("❌ Bracket is already started.")
        if len(t['players']) < 2: return await ctx.send("❌ Need at least 2 players to start.")

        t['channel_id'] = ctx.channel.id

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
        await self.send_status_image(ctx.channel, name, t)
        if active_matches:
            await self.announce_matches(ctx.channel, t, active_matches)

    @bracket.command(brief='Manually report the winner of a match.')
    async def report(self, ctx, name: str, winner: discord.Member):
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        if not self.is_manager(ctx, t): return await ctx.send("❌ Only managers can manually report scores.")
        if t['state'] != 'active': return await ctx.send("❌ Bracket is not currently active.")

        t['channel_id'] = ctx.channel.id

        if t['type'] == 'point_system':
            t['scores'][str(winner.id)] = t['scores'].get(str(winner.id), 0) + 1
            self.save_data()
            await ctx.send(f"✅ Added 1 point for **{winner.display_name}**!")
            return await self.send_status_image(ctx.channel, name, t)

        active_match = None
        current_round = t.get('current_round')
        for mid, m in t['matches'].items():
            if m['winner'] is None and winner.id in (m.get('p1'), m.get('p2')):
                if current_round and m.get('round') != current_round:
                    continue
                active_match = mid
                break
                
        if not active_match:
            return await ctx.send(f"❌ Could not find an active pending match for {winner.display_name}.")

        new_matches = await self.process_win(name, t, active_match, winner.id)

        await ctx.send(f"✅ Reported win for **{winner.display_name}**!")
        await self.send_status_image(ctx.channel, name, t)
        
        if t['state'] == 'finished':
            await ctx.send(f"🎉 **TOURNAMENT FINISHED!** 🎉")
        elif new_matches:
            await self.announce_matches(ctx.channel, t, new_matches)

    @bracket.command(brief='Show current bracket image or leaderboard.')
    async def status(self, ctx, name: str):
        t = self.tournaments.get(name)
        if not t: return await ctx.send("❌ Bracket not found.")
        
        t['channel_id'] = ctx.channel.id
        self.save_data()
        
        await self.send_status_image(ctx.channel, name, t)

async def setup(bot):
    await bot.add_cog(Brackets(bot))
