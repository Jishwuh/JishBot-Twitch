import asyncio
import time
from typing import Dict, Optional

import httpx

from jishbot.app.db import database
from jishbot.app.services import twitch_api_service

POLL_SECONDS = 120  # Twitch rate limits are friendly at this cadence


async def set_webhook(channel_id: str, webhook_url: Optional[str]) -> None:
    db = await database.get_db()
    await db.execute(
        """
        INSERT INTO notifications(channel_id, webhook_url, last_status, last_notified_at)
        VALUES(?,?,NULL,0)
        ON CONFLICT(channel_id) DO UPDATE SET webhook_url=excluded.webhook_url
        """,
        (channel_id, webhook_url),
    )
    await db.commit()


async def get_webhook(channel_id: str) -> Optional[str]:
    db = await database.get_db()
    async with db.execute("SELECT webhook_url FROM notifications WHERE channel_id=?", (channel_id,)) as cursor:
        row = await cursor.fetchone()
        return row["webhook_url"] if row else None


async def _update_status(channel_id: str, status: str) -> None:
    db = await database.get_db()
    await db.execute(
        "UPDATE notifications SET last_status=?, last_notified_at=? WHERE channel_id=?",
        (status, int(time.time()), channel_id),
    )
    await db.commit()


async def _send_webhook(webhook_url: str, title: str, game: str, channel: str) -> None:
    data = {
        "content": None,
        "embeds": [
            {
                "title": f"{channel} is live!",
                "description": title or "Streaming now",
                "url": f"https://twitch.tv/{channel}",
                "color": 6570404,
                "fields": [{"name": "Game", "value": game or "Just Chatting", "inline": True}],
            }
        ],
    }
    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json=data, timeout=10)


async def send_test(webhook_url: str, channel: str) -> None:
    await _send_webhook(webhook_url, "This is a test notification", "Test", channel)


async def _check_channel(channel: str) -> None:
    webhook = await get_webhook(channel)
    if not webhook:
        return
    is_live, title, game = await twitch_api_service.get_stream_status(channel)
    db = await database.get_db()
    async with db.execute(
        "SELECT last_status FROM notifications WHERE channel_id=?", (channel,)
    ) as cursor:
        row = await cursor.fetchone()
        last_status = row["last_status"] if row else None
    if is_live and last_status != "live":
        try:
            await _send_webhook(webhook, title, game, channel)
            await _update_status(channel, "live")
        except Exception:
            # Swallow errors to avoid crashing loop
            pass
    elif not is_live and last_status != "offline":
        await _update_status(channel, "offline")


async def run_poll_loop(channels: list[str]) -> None:
    while True:
        for ch in channels:
            await _check_channel(ch)
        await asyncio.sleep(POLL_SECONDS)
