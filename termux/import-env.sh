#!/usr/bin/env bash
# Use a .env you made on your laptop: copy it to the phone's Downloads folder
# as "discord-logger.env" (or "discord-logger.env.txt"), then run:
#   bash termux/import-env.sh
# It moves the file into place, deletes the copy in Downloads (other apps can
# read Downloads, and it contains your token), and restarts the bot.
set -euo pipefail
cd "$(dirname "$0")/.."

DL="$HOME/storage/downloads"
if [ ! -d "$DL" ]; then
  echo "Termux can't see your Downloads yet. Allow storage access in the popup, then run this again."
  termux-setup-storage
  exit 1
fi

SRC=""
for name in discord-logger.env discord-logger.env.txt; do
  if [ -f "$DL/$name" ]; then SRC="$DL/$name"; break; fi
done
if [ -z "$SRC" ]; then
  echo "No discord-logger.env found in Downloads."
  exit 1
fi

# strip Windows line endings so values don't end with a hidden \r
tr -d '\r' < "$SRC" > .env
chmod 600 .env
rm -f "$SRC"
echo "Imported .env and deleted $(basename "$SRC") from Downloads."

if [ -f bot.pid ] && kill -0 "$(cat bot.pid)" 2>/dev/null; then
  bash termux/stop.sh && bash termux/start.sh
else
  echo "Start the bot with: bash termux/start.sh"
fi
