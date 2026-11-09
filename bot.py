"""Discord presence tracker.

Logs how long tracked users spend online / idle / dnd / offline, sends a
message every time their status changes, and shows totals via slash commands.

All private settings (token, user IDs, channel) come from environment
variables / a local `.env` file that is git-ignored.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys
import time
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from storage import Store

load_dotenv()
log = logging.getLogger("presence")


# --------------------------------------------------------------------------- config

def _ids(name: str) -> set[int]:
    raw = os.getenv(name, "")
    try:
        return {int(x) for x in raw.replace(" ", "").split(",") if x}
    except ValueError:
        sys.exit(f"{name} must be a comma-separated list of numeric Discord IDs")


def _int(name: str) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return 0
    if not raw.isdigit():
        sys.exit(f"{name} must be a number")
    return int(raw)


TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
TRACKED = _ids("TRACKED_USER_IDS")
OWNERS = _ids("OWNER_IDS") or TRACKED
GUILD_ID = _int("GUILD_ID")
NOTIFY_CHANNEL_ID = _int("NOTIFY_CHANNEL_ID")
TZ = ZoneInfo(os.getenv("TIMEZONE", "UTC").strip() or "UTC")
DB_PATH = os.getenv("DB_PATH", "presence.db").strip() or "presence.db"
# How often the bot saves a timestamp to the database. Lower = less time lost
# if it crashes; higher = fewer wake-ups (better battery on a phone).
HEARTBEAT_SECONDS = max(15, _int("HEARTBEAT_SECONDS") or 60)

STATUS_ORDER = ["online", "idle", "dnd", "offline"]
STATUS_LABEL = {"online": "🟢 Online", "idle": "🌙 Idle", "dnd": "⛔ Do not disturb", "offline": "⚫ Offline"}


def mask(user_id: int) -> str:
    """Short form for console logs so full IDs don't end up in shared logs."""
    return f"...{str(user_id)[-4:]}"


# --------------------------------------------------------------------------- helpers

def devices_of(member: discord.Member) -> str:
    parts = (
        ("desktop", member.desktop_status),
        ("mobile", member.mobile_status),
        ("web", member.web_status),
    )
    return ",".join(name for name, s in parts if s is not discord.Status.offline)


def normalize(status: discord.Status) -> str:
    s = str(status)
    return "offline" if s == "invisible" else s


def window(period: str) -> tuple[float, float, str]:
    now = dt.datetime.now(TZ)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "yesterday":
        return (midnight - dt.timedelta(days=1)).timestamp(), midnight.timestamp(), "Yesterday"
    if period == "week":
        return (now - dt.timedelta(days=7)).timestamp(), now.timestamp(), "Last 7 days"
    if period == "month":
        return (now - dt.timedelta(days=30)).timestamp(), now.timestamp(), "Last 30 days"
    return midnight.timestamp(), now.timestamp(), "Today"


def fmt(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    m = int(seconds // 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def bar(fraction: float, width: int = 14) -> str:
    filled = round(fraction * width)
    return "█" * filled + "░" * (width - filled)


def change_message(name: str, old: str, new: str, devices: str, old_secs: float, at: float) -> str:
    line = f"{STATUS_LABEL.get(new, new)} · **{name}**"
    if devices and new != "offline":
        line += f" on {devices.replace(',', ', ')}"
    return f"{line}\n-# was {STATUS_LABEL.get(old, old)} for {fmt(old_secs)} · <t:{int(at)}:T>"


# --------------------------------------------------------------------------- bot

class Tracker(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.presences = True  # privileged: enable in the Developer Portal
        intents.members = True    # privileged: enable in the Developer Portal
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.store = Store(DB_PATH)
        # user_id -> (status, when that status started). Used for alerts.
        self.since: dict[int, tuple[str, float]] = {}

    async def setup_hook(self) -> None:
        self.store.close_stale()
        if GUILD_ID:
            guild = discord.Object(GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        self.heartbeat.change_interval(seconds=HEARTBEAT_SECONDS)
        self.heartbeat.start()

    async def on_ready(self) -> None:
        log.info("Logged in as %s, tracking %d user(s)", self.user, len(TRACKED))
        self.snapshot()

    def find_member(self, user_id: int) -> discord.Member | None:
        for guild in self.guilds:
            member = guild.get_member(user_id)
            if member:
                return member
        return None

    def snapshot(self) -> None:
        """Record everyone's current state (on start and after reconnects)."""
        now = time.time()
        for uid in TRACKED:
            member = self.find_member(uid)
            if member is None:
                log.warning("Tracked user %s isn't in any server the bot is in", mask(uid))
                continue
            status = normalize(member.status)
            self.store.record(uid, status, devices_of(member), now)
            if self.since.get(uid, ("",))[0] != status:
                self.since[uid] = (status, now)

    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.id not in TRACKED:
            return
        now = time.time()
        status, devices = normalize(after.status), devices_of(after)
        self.store.record(after.id, status, devices, now)

        prev = self.since.get(after.id)
        if prev is None:
            self.since[after.id] = (status, now)
            return
        if prev[0] == status:
            return  # only a device change, or a duplicate from another server
        self.since[after.id] = (status, now)
        log.info("%s %s -> %s", mask(after.id), prev[0], status)
        await self.notify(change_message(after.display_name, prev[0], status, devices, now - prev[1], now))

    async def notify(self, text: str) -> None:
        try:
            if NOTIFY_CHANNEL_ID:
                channel = self.get_channel(NOTIFY_CHANNEL_ID) or await self.fetch_channel(NOTIFY_CHANNEL_ID)
                await channel.send(text)
                return
            for owner_id in OWNERS:
                user = self.get_user(owner_id) or await self.fetch_user(owner_id)
                await user.send(text)
        except discord.HTTPException as e:
            log.warning("Couldn't send status alert: %s", e)

    @tasks.loop(seconds=60)  # real interval set from HEARTBEAT_SECONDS in setup_hook
    async def heartbeat(self) -> None:
        self.store.heartbeat()

    def stats_embed(self, user_id: int, start: float, end: float, label: str) -> discord.Embed:
        totals, mobile = self.store.totals(user_id, start, end)
        tracked = sum(totals.values()) or 1
        member = self.find_member(user_id)
        name = member.display_name if member else "Unknown user"

        lines = []
        for status in STATUS_ORDER:
            secs = totals.get(status, 0.0)
            lines.append(f"{STATUS_LABEL[status]}\n`{bar(secs / tracked)}` **{fmt(secs)}**")

        embed = discord.Embed(title=f"{name} · {label}", description="\n".join(lines), color=0x5865F2)
        active = sum(v for k, v in totals.items() if k != "offline")
        embed.add_field(name="Active total", value=fmt(active))
        embed.add_field(name="On mobile", value=fmt(mobile))
        embed.set_footer(text=f"Tracked {fmt(sum(totals.values()))} of this period")
        return embed


client = Tracker()


# --------------------------------------------------------------------------- commands

def pick_user(interaction: discord.Interaction, user: discord.User | None) -> int | None:
    if user is not None:
        return user.id if user.id in TRACKED else None
    if interaction.user.id in TRACKED:
        return interaction.user.id
    return min(TRACKED) if TRACKED else None


async def guard(interaction: discord.Interaction) -> bool:
    if interaction.user.id in OWNERS:
        return True
    await interaction.response.send_message("You're not allowed to use this bot.", ephemeral=True)
    return False


PERIODS = [
    app_commands.Choice(name="Today", value="today"),
    app_commands.Choice(name="Yesterday", value="yesterday"),
    app_commands.Choice(name="Last 7 days", value="week"),
    app_commands.Choice(name="Last 30 days", value="month"),
]


@client.tree.command(description="How long you've been online / idle / offline")
@app_commands.describe(period="Time range", user="Tracked user (defaults to you)")
@app_commands.choices(period=PERIODS)
async def stats(
    interaction: discord.Interaction,
    period: app_commands.Choice[str] | None = None,
    user: discord.User | None = None,
) -> None:
    if not await guard(interaction):
        return
    uid = pick_user(interaction, user)
    if uid is None:
        await interaction.response.send_message("That user isn't being tracked.", ephemeral=True)
        return
    start, end, label = window(period.value if period else "today")
    await interaction.response.send_message(
        embed=client.stats_embed(uid, start, end, label), ephemeral=True
    )


@client.tree.command(description="List of status changes for a day")
@app_commands.describe(day="Which day", user="Tracked user (defaults to you)")
@app_commands.choices(day=PERIODS[:2])
async def timeline(
    interaction: discord.Interaction,
    day: app_commands.Choice[str] | None = None,
    user: discord.User | None = None,
) -> None:
    if not await guard(interaction):
        return
    uid = pick_user(interaction, user)
    if uid is None:
        await interaction.response.send_message("That user isn't being tracked.", ephemeral=True)
        return
    start, end, label = window(day.value if day else "today")
    rows = []
    for s in client.store.sessions(uid, start, end):
        t0 = dt.datetime.fromtimestamp(s.started_at, TZ).strftime("%H:%M")
        t1 = dt.datetime.fromtimestamp(s.ended_at, TZ).strftime("%H:%M")
        devices = f" ({s.devices})" if s.devices else ""
        rows.append(f"`{t0}–{t1}` {STATUS_LABEL.get(s.status, s.status)}{devices} · {fmt(s.ended_at - s.started_at)}")
    text = "\n".join(rows[-40:]) or "No data for this day yet."
    if len(rows) > 40:
        text = f"_…{len(rows) - 40} earlier entries hidden_\n" + text
    await interaction.response.send_message(
        embed=discord.Embed(title=f"Timeline · {label}", description=text[:4000], color=0x5865F2),
        ephemeral=True,
    )


# --------------------------------------------------------------------------- main

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not TOKEN:
        sys.exit("DISCORD_TOKEN is missing. Copy .env.example to .env and fill it in.")
    if not TRACKED:
        sys.exit("TRACKED_USER_IDS is empty. Add at least one Discord user ID to .env.")
    try:
        client.run(TOKEN, log_handler=None)
    finally:
        client.store.close()


if __name__ == "__main__":
    main()
