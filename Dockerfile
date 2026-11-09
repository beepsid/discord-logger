FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Keep the database on a mounted volume so it survives redeploys.
    DB_PATH=/data/presence.db

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py storage.py ./
RUN mkdir -p /data

# Secrets (DISCORD_TOKEN, TRACKED_USER_IDS, ...) are passed in as environment
# variables by the host. They are never baked into the image.
CMD ["python", "bot.py"]
