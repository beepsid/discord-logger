#!/usr/bin/env bash
# One-time setup for running the bot on an Android phone with Termux.
# Run from the repo folder:  bash termux/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"

echo "==> Installing packages"
pkg update -y
# clang is needed to build one of discord.py's dependencies on Android
pkg install -y python git clang nano

echo "==> Installing Python requirements (this can take a few minutes)"
# Use the pure-Python versions of aiohttp's helpers: faster to install, same behaviour
export AIOHTTP_NO_EXTENSIONS=1 MULTIDICT_NO_EXTENSIONS=1 YARL_NO_EXTENSIONS=1 \
       FROZENLIST_NO_EXTENSIONS=1 PROPCACHE_NO_EXTENSIONS=1
python -m venv .venv
.venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Created .env. Fill it in with:  nano .env"
fi

echo "==> Setting up auto-start on boot (needs the Termux:Boot app)"
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/discord-logger <<EOF
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
bash "$REPO/termux/start.sh"
EOF
chmod +x ~/.termux/boot/discord-logger termux/*.sh

echo
echo "Done. Next:"
echo "  1. nano .env              (add your token and IDs)"
echo "  2. bash termux/start.sh   (start the bot in the background)"
echo "  3. tail -f bot.log        (check it says 'Logged in as ...')"
