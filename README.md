# discord-logger

A small self-hosted Discord bot that tracks how long a user spends **online**, **idle**, **do not disturb** and **offline**, sends a message every time that status changes, and shows the totals with slash commands.

- `/stats [period] [user]`: time per status for today, yesterday, the last 7 days or the last 30 days, plus time active on mobile
- `/timeline [day] [user]`: every status change for a day, with the devices used
- Alerts in a channel (or by DM):
  - **Comes online** → pings you: "🟢 Online · **you** came online on mobile, was offline for 3h 12m"
  - **Idle / do not disturb** → no ping: "🌙 Idle · was 🟢 Online for 45m"
  - **Goes offline** → session recap: "⚫ **you** went offline · was on for **2h 5m**, 🟢 1h 30m · 🌙 30m · ⛔ 5m"
- A daily summary at `SUMMARY_TIME` with time per status, number of sessions, longest session, and first and last seen

To get a notification only when you come online, set the alert channel to **Only @mentions** (long-press the channel → Notification Settings).

### The tracked account never gets reports

- `OWNER_IDS` (who gets alerts) is required, and the bot won't start if it contains a tracked ID.
- Before every post, the bot checks that no tracked account can see the alert channel. If one can, the bot DMs the owners instead.
- `/stats` and `/timeline` are hidden from everyone except server admins, and only `OWNER_IDS` can run them. Their replies are visible only to the person who ran them.

To make the alert channel private: long-press the channel → **Edit Channel** → **Permissions** → turn on **Private Channel**. Then add only your main account; the bot can see it as an admin. Tracked accounts are left out automatically.

The tracked account still has to be in a server with the bot so the bot can see its status. If it's in your private server, don't give it a role with Administrator or "View Channels" on the alert channel.

Replies are ephemeral (only the person who runs the command sees them), and only the IDs in `OWNER_IDS` can use the commands.

## Privacy

No IDs, tokens or channels are written in the code. Everything private lives in a local `.env` file, which `.gitignore` keeps out of git, along with the database (`presence.db`) that holds your tracking history.

Before you push, check that `git status` doesn't list `.env` or any `.db` file.

If a token ever gets committed by mistake, deleting the file won't help, because it stays in the git history. Reset the token in the Developer Portal right away.

## Setup

### 1. Create the bot

1. Go to <https://discord.com/developers/applications> → **New Application**.
2. **Bot** tab → **Reset Token** → copy the token (you'll put it in `.env`).
3. On the same tab, under **Privileged Gateway Intents**, turn on **Presence Intent** and **Server Members Intent**.
4. **OAuth2 → URL Generator**: tick `bot` and `applications.commands`, then under bot permissions tick `Send Messages` and `Embed Links`. Open the URL and add the bot to a server you're in.

The bot can only see the status of people who share a server with it.

### 2. Configure

```bash
cp .env.example .env
```

Fill in `.env`. To copy IDs, turn on Discord → Settings → Advanced → **Developer Mode**, then right-click a user, server or channel → **Copy ID**.

### 3. Run

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
python bot.py
```

The bot only records changes while it's running. Time when the bot is down is left out of the totals rather than counted as a status. To keep it running 24/7, host it online (see below).

## Hosting 24/7

On a host, your secrets go into the host's **environment variables** settings instead of a `.env` file. They're the same names as in `.env.example`. Nothing private is in the repo, so the repo can be public.

### Option A: your Android phone (free, no card)

Battery and data use are low when the bot is only in a **small private server**, ideally one with just you and the bot. Discord sends the bot status updates for every member of every server it's in, so keep it out of big servers.

1. Install **Termux** and **Termux:Boot** from [F-Droid](https://f-droid.org) (the Play Store version of Termux is outdated). Open Termux:Boot once so Android lets it run at startup.
2. In Android settings → Apps → Termux → Battery, choose **Unrestricted**. Otherwise Android kills the bot in the background.
3. In Termux:

   ```bash
   pkg install -y git
   git clone https://github.com/<you>/discord-logger.git && cd discord-logger
   bash termux/setup.sh
   nano .env                 # fill in your token and IDs, Ctrl+O to save, Ctrl+X to exit
   bash termux/start.sh
   tail -f bot.log           # should say "Logged in as ...", Ctrl+C to stop watching
   ```

The bot now runs in the background, restarts itself if it crashes, and starts again after a reboot. Termux shows a notification while it holds the wake lock. That's expected.

| Task | Command |
| --- | --- |
| Stop | `bash termux/stop.sh` |
| Start | `bash termux/start.sh` |
| Update | `git pull && bash termux/stop.sh && bash termux/start.sh` |

If the phone loses internet or turns off, that time shows up as a gap rather than wrong data. To move to a server later, copy `presence.db` across and your history comes with it.

### Option B: Railway (easiest, about $5/month)

1. Push this repo to GitHub.
2. On <https://railway.com>, choose **New Project → Deploy from GitHub repo** and pick this repo. Railway finds the `Dockerfile` automatically.
3. Open the service → **Variables**. Add `DISCORD_TOKEN`, `TRACKED_USER_IDS`, `TIMEZONE` and any others you use from `.env.example`.
4. Open the service → **Settings → Volumes**. Add a volume with mount path **`/data`**. Without it, your history is wiped on every redeploy.
5. Deploy. Check the logs for `Logged in as ...`.

Each push to GitHub redeploys the bot automatically, and your data stays on the volume.

### Option C: free Linux VM (Oracle Cloud Always Free or similar)

This one is free but takes more setup. Create an Ubuntu VM, then SSH into it:

```bash
sudo apt update && sudo apt install -y python3-venv git
git clone https://github.com/<you>/discord-logger.git && cd discord-logger
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env          # fill in your values
sudo cp deploy/discord-logger.service /etc/systemd/system/
sudo systemctl enable --now discord-logger
journalctl -u discord-logger -f            # watch the logs
```

If your VM user isn't `ubuntu`, edit `User=` and the paths in `deploy/discord-logger.service` first. systemd restarts the bot if it crashes and starts it again after a reboot.

To update later, run this on the VM:

```bash
git pull && sudo systemctl restart discord-logger
```

### Backups

All your history lives in one file: `/data/presence.db` on Railway, or `presence.db` on the VM. Download a copy now and then. Don't commit it.

## Notes

- Invisible looks the same as offline to bots, so it's recorded as offline.
- Tracking other people? Get their consent first.
- This uses a normal bot account. Don't adapt it to log in with your user token ("self-bot"), which is against Discord's Terms of Service.
