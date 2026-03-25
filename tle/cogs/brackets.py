import discord
from discord.ext import commands
import math
import random
import shlex
import io
from PIL import Image, ImageDraw, ImageFont

class Brackets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['bracket', 'tourney'])
    async def tournament(self, ctx, bracket_type: str, *, names_input: str = None):
        """
        Creates a tournament bracket based on a list of names.
        
        Supported types:
        `single` - Single Elimination
        `double` - Double Elimination
        `roundrobin` - Round Robin
        `swiss` - Swiss System (Round 1)
        `ffa` - Free For All (Pools)

        Input names can be:
        - Comma-separated: Alice, Bob, Charlie
        - Space-separated (use quotes for names with spaces): "John Doe" Alice "Jane Smith"
        - Newline-separated
        - Or attached as a .txt file!
        """
        names = []
        
        # 1. Check if the user attached a text file with names
        if ctx.message.attachments:
            file = ctx.message.attachments[0]
            if file.filename.endswith('.txt'):
                try:
                    content = (await file.read()).decode('utf-8')
                    names = [n.strip() for n in content.replace('\r', '\n').split('\n') if n.strip()]
                except Exception as e:
                    return await ctx.send(f"Error reading the file: {e}")
            else:
                return await ctx.send("Please attach a valid `.txt` file.")
        
        # 2. Fallback to parsing the string input
        if not names and names_input:
            if ',' in names_input:
                names = [n.strip() for n in names_input.split(',') if n.strip()]
            elif '\n' in names_input:
                names = [n.strip() for n in names_input.split('\n') if n.strip()]
            else:
                try:
                    # Allows quoted strings with spaces like "John Doe"
                    names = [n.strip() for n in shlex.split(names_input) if n.strip()]
                except ValueError:
                    # Fallback if quotes are unbalanced
                    names = [n.strip() for n in names_input.split() if n.strip()]
        
        if not names:
            return await ctx.send("Please provide a list of names! You can type them out or attach a `.txt` file.")
            
        # Filter out empty strings and remove duplicates while preserving insertion order
        unique_names = []
        for n in names:
            if n and n not in unique_names:
                unique_names.append(n)
        names = unique_names
        
        if len(names) < 2:
            return await ctx.send("A tournament requires at least 2 participants!")

        # Shuffle the roster to ensure random, fair seeding
        random.shuffle(names)
        
        bracket_type = bracket_type.lower()
        if bracket_type in ['single', 'se', 'single-elimination']:
            title, content = self._single_elimination(names)
        elif bracket_type in ['double', 'de', 'double-elimination']:
            title, content = self._double_elimination(names)
        elif bracket_type in ['roundrobin', 'rr', 'round-robin']:
            title, content = self._round_robin(names)
        elif bracket_type in ['swiss']:
            title, content = self._swiss(names)
        elif bracket_type in ['ffa', 'freeforall']:
            title, content = self._ffa(names)
        else:
            return await ctx.send(
                "Unknown format! Please choose from: `single`, `double`, `roundrobin`, `swiss`, or `ffa`."
            )

        # Generate the visual bracket image
        image_buf = None
        if bracket_type in ['single', 'se', 'single-elimination', 'double', 'de', 'double-elimination']:
            image_buf = self._generate_bracket_image(ctx, names, title)
        else:
            image_buf = self._generate_text_image(ctx, title, content)
            
        image_file = discord.File(image_buf, filename="bracket.png")

        # Send response: Use a file if the bracket is too large for Discord limits
        if len(content) > 4000:
            file_content = f"{title}\n\nTotal Participants: {len(names)}\n\n{content}"
            text_file = discord.File(io.StringIO(file_content), filename=f"{bracket_type}_bracket.txt")
            await ctx.send(
                f"The generated **{title}** is too large for a message! I've attached the visual bracket image and the full text schedule.", 
                files=[image_file, text_file]
            )
        else:
            embed = discord.Embed(title=title, description=content, color=discord.Color.green())
            embed.set_footer(text=f"Total Participants: {len(names)} | Seeded Randomly")
            embed.set_image(url="attachment://bracket.png")
            await ctx.send(embed=embed, file=image_file)

    def _clean_mentions(self, ctx, text):
        """Converts raw Discord mentions to display names for the image."""
        for m in ctx.message.mentions:
            text = text.replace(f'<@{m.id}>', f'@{m.display_name}')
            text = text.replace(f'<@!{m.id}>', f'@{m.display_name}')
        for r in ctx.message.role_mentions:
            text = text.replace(f'<@&{r.id}>', f'@{r.name}')
        return text

    def _generate_bracket_image(self, ctx, names, title):
        """Draws a tournament tree diagram using Pillow."""
        n = len(names)
        p = 2**math.ceil(math.log2(n)) if n > 1 else 2
        byes = p - n
        
        clean_names = [self._clean_mentions(ctx, name) for name in names]
        competitors = clean_names + ["(Bye)"] * byes
        
        rounds = int(math.log2(p)) + 1
        
        box_width = 200
        box_height = 40
        x_margin = 40
        y_margin = 20
        
        width = rounds * (box_width + x_margin) + x_margin
        height = (p // 2) * (box_height * 2 + y_margin) + 120
        
        img = Image.new('RGB', (width, height), color=(43, 45, 49))
        draw = ImageDraw.Draw(img)
        
        try:
            # Using TLE's embedded fonts
            font = ImageFont.truetype("tle/assets/fonts/NotoSans-Regular.ttf", 14)
            title_font = ImageFont.truetype("tle/assets/fonts/NotoSans-Bold.ttf", 24)
        except Exception:
            font = ImageFont.load_default()
            title_font = ImageFont.load_default()
            
        draw.text((x_margin, 20), title, font=title_font, fill=(255, 255, 255))
        
        match_coords = []
        current_y = 80
        round_matches = []
        
        # Draw the initial round (Round 1)
        for i in range(0, p, 2):
            p1 = competitors[i]
            p2 = competitors[i+1]
            x = x_margin
            y = current_y
            
            draw.rectangle([x, y, x + box_width, y + box_height], outline=(114, 137, 218), fill=(30, 33, 36))
            draw.text((x + 10, y + 10), str(p1)[:25], font=font, fill=(255, 255, 255))
            
            draw.rectangle([x, y + box_height, x + box_width, y + box_height * 2], outline=(114, 137, 218), fill=(30, 33, 36))
            draw.text((x + 10, y + box_height + 10), str(p2)[:25], font=font, fill=(255, 255, 255))
            
            round_matches.append((x + box_width, y + box_height))
            current_y += box_height * 2 + y_margin
            
        match_coords.append(round_matches)
        
        # Draw subsequent empty brackets & connecting lines
        for r in range(1, rounds):
            prev = match_coords[r-1]
            curr = []
            x = x_margin + r * (box_width + x_margin)
            
            for i in range(0, len(prev), 2):
                if i + 1 < len(prev):
                    m1 = prev[i]
                    m2 = prev[i+1]
                    y1 = m1[1]
                    y2 = m2[1]
                    new_y = (y1 + y2) // 2
                    
                    mid_x = m1[0] + x_margin // 2
                    # Connection Lines
                    draw.line([(m1[0], y1), (mid_x, y1)], fill=(255, 255, 255), width=2)
                    draw.line([(m2[0], y2), (mid_x, y2)], fill=(255, 255, 255), width=2)
                    draw.line([(mid_x, y1), (mid_x, y2)], fill=(255, 255, 255), width=2)
                    draw.line([(mid_x, new_y), (x, new_y)], fill=(255, 255, 255), width=2)
                    
                    if r < rounds - 1:
                        # Draw standard match box
                        box_top = new_y - box_height
                        draw.rectangle([x, box_top, x + box_width, box_top + box_height], outline=(114, 137, 218), fill=(30, 33, 36))
                        draw.rectangle([x, box_top + box_height, x + box_width, box_top + box_height * 2], outline=(114, 137, 218), fill=(30, 33, 36))
                        curr.append((x + box_width, new_y))
                    else:
                        # Draw Final Winner box
                        box_top = new_y - box_height // 2
                        draw.rectangle([x, box_top, x + box_width, box_top + box_height], outline=(255, 215, 0), fill=(30, 33, 36))
                        draw.text((x + 10, box_top + 10), "Winner", font=font, fill=(255, 215, 0))
                        
            match_coords.append(curr)
            
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf

    def _generate_text_image(self, ctx, title, content):
        """Generates a text-based image on a dark canvas for formats like Round Robin."""
        clean_content = self._clean_mentions(ctx, content)
        lines = clean_content.split('\n')
        
        height = len(lines) * 25 + 100
        max_len = max([len(l) for l in lines] + [len(title) * 2])
        width = max_len * 12 + 100
        
        img = Image.new('RGB', (width, height), color=(43, 45, 49))
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("tle/assets/fonts/NotoSans-Regular.ttf", 16)
            title_font = ImageFont.truetype("tle/assets/fonts/NotoSans-Bold.ttf", 24)
        except Exception:
            font = ImageFont.load_default()
            title_font = ImageFont.load_default()
            
        draw.text((40, 30), title, font=title_font, fill=(255, 215, 0))
        
        y = 80
        for line in lines:
            if line.startswith('```') or line.startswith('---'):
                continue
            draw.text((40, y), line, font=font, fill=(255, 255, 255))
            y += 25
            
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf

    def _single_elimination(self, names):
        n = len(names)
        # Calculate the next power of 2 for a balanced bracket
        p = 2**math.ceil(math.log2(n))
        byes = p - n
        
        competitors = names + ["(Bye)"] * byes
        
        out = "```yaml\n"
        out += f"Round 1 Matchups ({p} Bracket Size, {byes} Byes)\n"
        out += "-" * 45 + "\n"
        
        match_num = 1
        for i in range(0, len(competitors), 2):
            p1 = competitors[i]
            p2 = competitors[i+1]
            if p1 == "(Bye)":
                out += f"Match {match_num:<2} : {p2} advances automatically\n"
            elif p2 == "(Bye)":
                out += f"Match {match_num:<2} : {p1} advances automatically\n"
            else:
                out += f"Match {match_num:<2} : {p1} vs {p2}\n"
            match_num += 1
            
        out += "```\n*Winners advance to the next round.*"
        return "Single Elimination Bracket", out

    def _double_elimination(self, names):
        title, content = self._single_elimination(names)
        content = content.replace("Single Elimination Bracket", "Winners Bracket")
        content += "\n\n*Note: Losers from these matches will drop down to the Losers Bracket.*"
        return "Double Elimination Bracket", content

    def _round_robin(self, names):
        players = names.copy()
        if len(players) % 2 != 0:
            players.append("(Bye)")
        
        n = len(players)
        rounds = []
        
        # Standard circle method for round robin generation
        for i in range(n - 1):
            round_matches = []
            for j in range(n // 2):
                p1 = players[j]
                p2 = players[n - 1 - j]
                if p1 != "(Bye)" and p2 != "(Bye)":
                    round_matches.append(f"{p1} vs {p2}")
            rounds.append(round_matches)
            
            # Rotate players, keeping the first player fixed
            players.insert(1, players.pop())
            
        out = "```yaml\n"
        for r_num, matches in enumerate(rounds, 1):
            out += f"--- Round {r_num} ---\n"
            for m in matches:
                out += f"• {m}\n"
            out += "\n"
        out += "```"
        return "Round Robin Schedule", out

    def _swiss(self, names):
        n = len(names)
        byes = n % 2
        
        competitors = names + ["(Bye)"] * byes
        
        out = "```yaml\n"
        out += f"Round 1 Matchups (Initial Seed)\n"
        out += "-" * 45 + "\n"
        
        match_num = 1
        for i in range(0, len(competitors), 2):
            p1 = competitors[i]
            p2 = competitors[i+1]
            if p1 == "(Bye)":
                out += f"Match {match_num:<2} : {p2} gets a Bye\n"
            elif p2 == "(Bye)":
                out += f"Match {match_num:<2} : {p1} gets a Bye\n"
            else:
                out += f"Match {match_num:<2} : {p1} vs {p2}\n"
            match_num += 1
            
        out += "```\n*Subsequent rounds require matchmaking based on updated Win/Loss records.*"
        return "Swiss System Bracket", out

    def _ffa(self, names):
        # Default group sizes of 4, or fewer if total is less than 5
        pool_size = 4
        if len(names) <= 5:
            pool_size = len(names)
            
        out = "```yaml\n"
        pools = [names[i:i + pool_size] for i in range(0, len(names), pool_size)]
        
        for i, pool in enumerate(pools, 1):
            out += f"Pool {i}:\n"
            for p in pool:
                out += f"• {p}\n"
            out += "\n"
        out += "```\n*Top players from each pool advance to the next stage.*"
        return "Free For All (Pools) Bracket", out

async def setup(bot):
    await bot.add_cog(Brackets(bot))
