import asyncio
import datetime
import json
import os
import random

import discord
from discord.ext import commands

from tle import constants
from tle.util import pxl_christmas

GUESTBOOK_PATH = os.path.join(constants.MISC_DIR, 'pxl_guestbook.json')

_PXL_RETURN_GIFTS = [
    "+0 Codeforces rating and a brand-new `Segmentation Fault` on test 47 🎁",
    "a slightly used `std::vector` with 14 memory leaks 🎄",
    "a lump of coal and an `O(N^3)` solution that passes ONLY on sample cases 🪨",
    "one (1) guaranteed First-Try AC... on an 800-rated problem ✨",
    "my spare Santa hat and a mysterious `;gitgud` problem from 2014 🎅",
    "a candy cane shaped like a binary search tree (unbalanced, obviously) 🍬",
    "unlimited hot cocoa and a lifetime supply of `Time Limit Exceeded` verdicts ☕",
    "an autographed photo of PXL boarding Sleigh Express Gate 25 🛷",
    "a coupon for 100% off your next Wrong Answer on pretest 2 🎟️",
    "Santa's official permission to use `#define int long long` without shame ❄️",
]

_STAY_REJECTIONS = [
    "Nice try, {user}, but Santa offered me unlimited RAM and zero Codeforces API 503 errors. 🎅",
    "I'm flattered, {user}, truly. Counterpoint: the North Pole has free hot cocoa and nobody asks me why their `O(N^3)` got TLE. ☕",
    "You offered **{bribe}**? Tempting... unfortunately my suitcase is already zipped and sitting on it took 3 elves. 🧳",
    "Sorry {user}, I already signed a non-compete clause with Rudolph. I'm out before Dec 7! 🦌",
    "Keep your **{bribe}**! I'm retiring to Lapland to write `Hello World` in peace. ❄️",
    "A very generous offer of **{bribe}**, {user}, which I am politely declining via my sleigh's rearview mirror. 🛷",
    "Even if you gave me **{bribe}** AND a 3500 rating, my flight to the North Pole is non-refundable! ✈️",
    "No can do, {user}! If I stay one more week, I'm going to start dreaming in `Wrong Answer on test 1`. 🎄",
]

_FESTIVE_KEYWORDS = ('pxl', 'christmas', 'santa', 'reindeer', 'north pole', 'goodbye', 'bye pxl')
_FESTIVE_EMOJIS = ('🎄', '🎅', '🧳', '🛷', '❄️', '👋', '🎁')


def _load_guestbook() -> dict:
    if not os.path.exists(GUESTBOOK_PATH):
        return {}
    try:
        with open(GUESTBOOK_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_guestbook(data: dict):
    os.makedirs(os.path.dirname(GUESTBOOK_PATH), exist_ok=True)
    with open(GUESTBOOK_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class ChristmasFarewell(commands.Cog):
    """Funny Christmas departure & retirement commands for PXL."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        content = message.content.strip().lower()
        if not content or content.startswith(';'):
            return
        if any(kw in content for kw in _FESTIVE_KEYWORDS):
            if random.random() < 0.35:
                try:
                    await message.add_reaction(random.choice(_FESTIVE_EMOJIS))
                except discord.HTTPException:
                    pass

    @commands.command(
        name='farewell',
        aliases=['guestbook', 'sign'],
        help='Sign PXL\'s Christmas going-away card before he leaves the server!'
    )
    async def farewell(self, ctx, *, message: str = None):
        if not message:
            await ctx.send(
                "✍️ Write a message to sign PXL's going-away card!\n"
                "Example: `;farewell Safe travels to the North Pole, PXL!`"
            )
            return

        cleaned = message.strip()[:300]
        guestbook = _load_guestbook()
        uid = str(ctx.author.id)
        updated = uid in guestbook
        guestbook[uid] = {
            'author': ctx.author.display_name,
            'message': cleaned,
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        _save_guestbook(guestbook)

        verb = "updated your note on" if updated else "signed"
        embed = discord.Embed(
            title="🎄 PXL's Going-Away Card Signed!",
            description=f"**{ctx.author.display_name}** {verb} PXL's farewell card:\n> *{cleaned}*",
            color=discord.Color.from_rgb(22, 163, 74),
        )
        embed.set_footer(text=f"Total signatures: {len(guestbook)} • View all with ;card")
        await ctx.send(embed=embed)

    @commands.command(
        name='card',
        aliases=['farewells', 'notes'],
        help='Read everyone\'s messages on PXL\'s Christmas going-away card.'
    )
    async def card(self, ctx):
        guestbook = _load_guestbook()
        if not guestbook:
            await ctx.send(
                "💌 PXL's going-away card is completely blank... nobody signed it yet! 🥺\n"
                "Be the first with `;farewell <your message>`!"
            )
            return

        entries = list(guestbook.values())
        chunk_size = 10
        for i in range(0, len(entries), chunk_size):
            chunk = entries[i:i + chunk_size]
            page_num = (i // chunk_size) + 1
            total_pages = (len(entries) + chunk_size - 1) // chunk_size

            lines = [
                f"🎄 **{entry['author']}**: *\"{entry['message']}\"* (`{entry.get('timestamp', '')}`)"
                for entry in chunk
            ]
            embed = discord.Embed(
                title="💌 PXL's Christmas Going-Away Card",
                description="\n\n".join(lines),
                color=discord.Color.from_rgb(220, 38, 38),
            )
            embed.set_footer(
                text=f"Page {page_num}/{total_pages} • {len(entries)} signature(s) • Sign with ;farewell <msg>"
            )
            await ctx.send(embed=embed)

    @commands.command(
        name='gift',
        aliases=['wishlist', 'present'],
        help='Give PXL a Christmas parting gift and receive a chaotic CP gift in return!'
    )
    async def gift(self, ctx, *, item: str = None):
        given = item.strip()[:120] if item else "a mysterious wrapped box full of semicolons"
        return_gift = random.choice(_PXL_RETURN_GIFTS)

        embed = discord.Embed(
            title="🎁 PXL's Chaotic Christmas Gift Exchange",
            description=(
                f"**{ctx.author.display_name}** handed PXL **{given}**!\n\n"
                f"PXL stuffs it into his overloaded suitcase and hands you back:\n"
                f"👉 **{return_gift}**"
            ),
            color=discord.Color.from_rgb(234, 179, 8),
        )
        embed.set_footer(text="No refunds after Dec 7 • North Pole Customs Approved 🎅")
        await ctx.send(embed=embed)

    @commands.command(
        name='stay',
        aliases=['bribe', 'plead'],
        help='Try to convince or bribe PXL not to leave the server for Christmas.'
    )
    async def stay(self, ctx, *, bribe: str = None):
        bribe_text = bribe.strip()[:120] if bribe else "pure emotional guilt"
        reply = random.choice(_STAY_REJECTIONS).format(
            user=ctx.author.display_name,
            bribe=bribe_text,
        )
        await ctx.send(reply)

    @commands.command(
        name='whereispxl',
        aliases=['itinerary', 'tracker', 'flight'],
        help='Track PXL\'s live Christmas departure itinerary to the North Pole.'
    )
    async def whereispxl(self, ctx):
        countdown = pxl_christmas.format_countdown()
        percent, bar, packing_note = pxl_christmas.get_packing_progress()
        location, blurb, schedule = pxl_christmas.get_itinerary()

        embed = discord.Embed(
            title="🛷 Live PXL Sleigh Tracker — Flight NORTH-POLE-25",
            description=f"**Current Location:** {location}\n*{blurb}*",
            color=discord.Color.from_rgb(220, 38, 38),
        )
        embed.add_field(name="⏳ Countdown", value=countdown, inline=False)
        embed.add_field(
            name="🧳 Packing Status",
            value=f"`[{bar}] {percent}%` — {packing_note}",
            inline=False,
        )
        embed.add_field(
            name="🗺️ Departure Schedule",
            value="\n".join(schedule),
            inline=False,
        )
        embed.set_footer(text="PSUT ACM → North Pole (One-Way Ticket) 🎄")
        await ctx.send(embed=embed)

    @commands.command(
        name='depart',
        help='(Admin/Pxl/Moon only) Trigger PXL\'s grand Christmas farewell sequence. Pass "shutdown" to also close the bot.'
    )
    @commands.has_role('Admin')
    async def depart(self, ctx, mode: str = ''):
        channel_ids_str = os.environ.get('ANNOUNCMENT') or os.environ.get('announcement', '')
        channel_ids = [int(cid.strip()) for cid in channel_ids_str.split(',') if cid.strip().isdigit()]
        targets = [self.bot.get_channel(cid) for cid in channel_ids]
        targets = [ch for ch in targets if ch is not None]
        if not targets:
            targets = [ctx.channel]

        pxl_christmas.mark_departed(True)

        farewell_beats = [
            "🧳 *Alright everyone, this is it... zipping up my suitcase for the final time...*",
            "🔑 *Leaving the PSUT ACM server keys under the doormat. Don't break the Codeforces API while I'm gone!*",
            "🛷 *Santa's sleigh is double-parked outside and the reindeer are getting impatient...*",
            "🎄✨ **Merry Christmas, PSUT ACM!** Thank you for all the `;gitgud`s, duels, `;-;` meltdowns, and memories. May all your verdicts be **Accepted**! PXL, signing off for Christmas! 🎅👋",
        ]

        for ch in targets:
            for line in farewell_beats:
                await ch.send(line)
                await asyncio.sleep(1.5)

            guestbook = _load_guestbook()
            if guestbook:
                lines = [
                    f"• **{entry['author']}**: *\"{entry['message']}\"*"
                    for entry in list(guestbook.values())[:15]
                ]
                embed = discord.Embed(
                    title="💌 Final Memories from PXL's Going-Away Card",
                    description="\n".join(lines),
                    color=discord.Color.from_rgb(22, 163, 74),
                )
                embed.set_footer(text=f"Signed by {len(guestbook)} legend(s) • Forever in PXL's RAM ❤️")
                await ch.send(embed=embed)

        if mode.strip().lower() == 'shutdown':
            await ctx.send("🛷 *Engine started. Closing connection now — Merry Christmas!* 🎄")
            await asyncio.sleep(1)
            await self.bot.close()
        else:
            await ctx.send(
                "🎅 *Farewell sequence posted! PXL is now in permanent 'Gone for Christmas' mode. "
                "Run `;depart shutdown` whenever you're ready to pull the plug.*"
            )


async def setup(bot):
    await bot.add_cog(ChristmasFarewell(bot))
