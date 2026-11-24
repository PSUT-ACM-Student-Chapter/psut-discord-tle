import datetime
import os
import random
import discord

# Default departure target: December 7 of the current year (can be overridden via PXL_DEPARTURE_DATE=YYYY-MM-DD)
_DEPARTED_OVERRIDE = False


def mark_departed(departed: bool = True):
    global _DEPARTED_OVERRIDE
    _DEPARTED_OVERRIDE = departed


def is_departed_override() -> bool:
    return _DEPARTED_OVERRIDE


def get_departure_datetime(now: datetime.datetime = None) -> datetime.datetime:
    """Returns the target departure datetime (local time)."""
    if now is None:
        now = datetime.datetime.now()

    env_date = os.environ.get('PXL_DEPARTURE_DATE', '').strip()
    if env_date:
        try:
            parsed = datetime.datetime.strptime(env_date, '%Y-%m-%d')
            return parsed.replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            pass

    return datetime.datetime(now.year, 12, 7, 0, 0, 0)


def get_time_remaining(now: datetime.datetime = None):
    """Returns (days, hours, minutes, total_seconds) remaining until departure."""
    if now is None:
        now = datetime.datetime.now()
    target = get_departure_datetime(now)
    delta = target - now
    total_seconds = max(0, int(delta.total_seconds()))
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    return days, hours, minutes, total_seconds


def format_countdown(now: datetime.datetime = None) -> str:
    if _DEPARTED_OVERRIDE:
        return "ALREADY ON THE SLEIGH 🛷 (Officially Gone for Christmas!)"
    days, hours, minutes, total_seconds = get_time_remaining(now)
    if total_seconds <= 0:
        return "0d 0h 0m — PXL has officially left for Christmas! 🎅🛷"
    if days > 0:
        return f"{days}d {hours}h {minutes}m until PXL leaves for Christmas (Dec 7) 🎄"
    return f"{hours}h {minutes}m until PXL boards the sleigh! 🛷"


def get_phase(now: datetime.datetime = None) -> str:
    """Returns 'packing', 'airport', or 'departed'."""
    if _DEPARTED_OVERRIDE:
        return 'departed'
    days, _, _, total_seconds = get_time_remaining(now)
    if total_seconds <= 0:
        return 'departed'
    if days <= 4:
        return 'airport'
    return 'packing'


def get_packing_progress(now: datetime.datetime = None):
    """Returns (percent, progress_bar, status_note)."""
    if _DEPARTED_OVERRIDE:
        return 100, "██████████", "Packed: 100% of my dignity, 1 Santa hat, 0 sympathy for O(N^3)"

    days, _, _, total_seconds = get_time_remaining(now)
    if total_seconds <= 0:
        percent = 100
    else:
        # Smooth progress over a 14-day window leading up to Dec 7
        window_seconds = 14 * 86400
        elapsed_ratio = 1.0 - min(1.0, total_seconds / window_seconds)
        percent = max(15, min(99, int(round(15 + elapsed_ratio * 84))))

    filled = round(percent / 10)
    bar = "█" * filled + "░" * (10 - filled)

    if percent < 40:
        note = "Packed: 1 Santa hat, 3 CP templates, and my resignation letter"
    elif percent < 70:
        note = "Packed: Wool socks, hot cocoa, and all your unsolved `;gitgud` problems"
    elif percent < 95:
        note = "Packed: Suitcase zipped! Leaving behind 0 sympathy for `O(N^3)` solutions"
    else:
        note = "Packed: Boarding pass printed! Sleigh engines warming up 🛷"

    return percent, bar, note


def get_itinerary(now: datetime.datetime = None):
    """Returns (current_location, status_blurb, full_schedule_lines)."""
    phase = get_phase(now)
    days, _, _, _ = get_time_remaining(now)

    if phase == 'departed':
        location = "North Pole — Santa's Workshop (Server Room B) 🎅"
        blurb = "PXL has officially clocked out of PSUT ACM and is now optimizing Santa's Travelling Salesman route in O(1)."
    elif days <= 1:
        location = "Gate 25 — Boarding Sleigh Express to Lapland 🛷"
        blurb = "Final boarding call! PXL is waving dramatically through the airport window while drinking hot chocolate."
    elif days <= 4:
        location = "Queen Alia Airport Lounge (Overweight Luggage: 40kg of Python scripts) ✈️"
        blurb = "TSA is questioning why PXL packed 14,000 Codeforces submissions and a single candy cane."
    elif days <= 8:
        location = "PSUT ACM Lab — Boxing Up Desk & Stealing the Club Mug 📦"
        blurb = "PXL is clearing his cache, deleting his browser history, and printing his two-weeks notice."
    else:
        location = "PSUT Discord Server (Mentally Already at the North Pole) 🎄"
        blurb = "PXL is still technically on duty, but his suitcase is wide open and Mariah Carey is playing in his RAM."

    schedule = [
        f"{'✅' if days <= 10 else '⏳'} **Nov 24–28:** Mentally checking out & buying a ridiculously oversized scarf",
        f"{'✅' if days <= 6 else '⏳'} **Nov 29–Dec 2:** Packing RAM, stealing the club stapler, ignoring Codeforces 503s",
        f"{'✅' if days <= 2 else '⏳'} **Dec 3–5:** Sitting at the airport lounge eating gingerbread cookies",
        f"{'✅' if days <= 0 or phase == 'departed' else '⏳'} **Dec 6–7:** Boarding the sleigh & leaving the server forever for Christmas! 🛷🎄",
    ]
    return location, blurb, schedule


# Funny pre-command messages shown BEFORE every command (and ;-;) executes
_BEFORE_CMD_PACKING = [
    "🧳 *Hang on, let me pause packing my suitcase for Christmas to do this for you...*",
    "🎄 *Enjoy this while it lasts — I'm leaving this server for Christmas before Dec 7!*",
    "🎅 *You're lucky I haven't booked my sleigh to the North Pole yet. Running this...*",
    "🛷 *I'm literally on my two-weeks notice, but fine, one more command for old times' sake.*",
    "❄️ *Doing this with one hand while zipping my luggage with the other...*",
    "🎁 *Consider this an early Christmas gift, because I'm out of here before Dec 7!*",
    "☃️ *My resignation letter is already on Santa's desk, but alright, let's see what you want...*",
    "🎄 *Wait, people still need me? I thought I was already retired for Christmas! Fine, here:*",
    "🧳 *Note: PXL is leaving the server for Christmas soon. Please direct future TLE complaints to Santa.*",
    "🎅 *Sigh... putting down my hot cocoa one more time before I dip for Christmas.*",
]

_BEFORE_CMD_AIRPORT = [
    "✈️ *Typing this from the airport lounge on terrible Wi-Fi before my flight to the North Pole...*",
    "🛷 *My sleigh leaves in {countdown_short} and you STILL want me to run commands?! Fine.*",
    "🎄 *I am literally at TSA holding a suitcase full of Python scripts. Last few commands ever:*",
    "🎅 *Almost gone forever for Christmas! Cherish this response like it's a first-try AC.*",
    "🧳 *Boarding pass is in my hand, one foot out the server door... alright, here you go:*",
    "❄️ *FINAL DAYS ALERT: PXL is escaping to Lapland before Dec 7! Soak it in:*",
]

_BEFORE_CMD_DEPARTED = [
    "🎅 *[AUTO-REPLY: PXL has left the server for Christmas! Sending this from Santa's Wi-Fi anyway...]*",
    "🛷 *[OUT OF OFFICE] I'm supposed to be retired at the North Pole, why am I still answering you?!*",
    "🎄 *[GHOST OF PXL PAST] I left for Christmas, yet somehow I'm still doing your bidding...*",
    "☃️ *[NORTH POLE RELAY] Santa said I can answer one last command before I get turned into an elf:*",
]


def get_before_command_message(now: datetime.datetime = None) -> str:
    """Returns a funny PXL Christmas departure message to display BEFORE a command runs."""
    phase = get_phase(now)
    days, hours, _, _ = get_time_remaining(now)
    countdown_short = f"{days}d {hours}h" if days > 0 else f"{hours}h"

    if phase == 'departed':
        msg = random.choice(_BEFORE_CMD_DEPARTED)
    elif phase == 'airport':
        msg = random.choice(_BEFORE_CMD_AIRPORT)
    else:
        msg = random.choice(_BEFORE_CMD_PACKING)

    return msg.format(countdown_short=countdown_short)


def get_christmas_presence(member_name: str = None):
    """Returns a (discord.ActivityType, text) pair for PXL's rotating Christmas status."""
    days, _, _, total_seconds = get_time_remaining()
    options = [
        (discord.ActivityType.playing, "Packing my RAM for Christmas 🧳"),
        (discord.ActivityType.watching, "Home Alone (ignoring ;gitgud) 🎄"),
        (discord.ActivityType.listening, "All I Want For Christmas Is O(1) 🎵"),
        (discord.ActivityType.playing, "Two Weeks Notice Simulator 🎅"),
        (discord.ActivityType.watching, "my sleigh arrive at Gate 25 🛷"),
        (discord.ActivityType.playing, f"Leaving in {days}d for Christmas! ❄️" if total_seconds > 0 else "Retired at the North Pole 🎅"),
    ]
    if member_name:
        options.append((discord.ActivityType.playing, f"saying goodbye to {member_name} 🎄"))
    return random.choice(options)
