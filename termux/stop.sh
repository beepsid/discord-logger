#!/usr/bin/env bash
# Stop the bot and release the wake lock.
cd "$(dirname "$0")/.."

if [ -f bot.pid ]; then
  kill "$(cat bot.pid)" 2>/dev/null || true
  rm -f bot.pid
fi
pkill -f ".venv/bin/python bot.py" 2>/dev/null || true
termux-wake-unlock 2>/dev/null || true
echo "Stopped."
