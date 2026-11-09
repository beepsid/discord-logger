#!/usr/bin/env bash
# Start the bot in the background. Safe to run more than once.
cd "$(dirname "$0")/.."

if [ -f bot.pid ] && kill -0 "$(cat bot.pid)" 2>/dev/null; then
  echo "Already running (pid $(cat bot.pid)). Logs: tail -f bot.log"
  exit 0
fi

# Stop Android from putting Termux to sleep while the bot runs.
termux-wake-lock 2>/dev/null || true

nohup bash termux/loop.sh > /dev/null 2>&1 &
echo $! > bot.pid
echo "Started (pid $!). Logs: tail -f bot.log   Stop: bash termux/stop.sh"
