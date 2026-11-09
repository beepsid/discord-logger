#!/usr/bin/env bash
# Keeps the bot running: restarts it if it crashes. Started by start.sh.
cd "$(dirname "$0")/.."
while true; do
  # keep the log small: roll it over at ~1 MB
  if [ -f bot.log ] && [ "$(stat -c %s bot.log)" -gt 1000000 ]; then
    mv -f bot.log bot.log.old
  fi
  .venv/bin/python bot.py >> bot.log 2>&1
  echo "$(date '+%F %T') bot stopped (exit $?), restarting in 30s" >> bot.log
  sleep 30
done
