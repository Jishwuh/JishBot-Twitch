import asyncio
import logging

import uvicorn

from jishbot.app.bot import JishBot
from jishbot.app.db import database
from jishbot.app.settings import settings
from jishbot.app.web.webapp import app as fastapi_app
from jishbot.app.services import twitch_api_service


async def start_web():
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level=settings.log_level.lower())
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    db = await database.get_db()  # ensures migrations run
    channels = settings.twitch_channels
    if not channels:
        async with db.execute("SELECT channel_name FROM channels WHERE is_enabled=1") as cursor:
            rows = await cursor.fetchall()
            channels = [row["channel_name"].lstrip("#").lower() for row in rows]
    if not channels:
        raise RuntimeError("No channels configured; set TWITCH_CHANNELS or insert into channels table.")
    bot_id = settings.twitch_bot_id
    if not bot_id.isdigit():
        user = await twitch_api_service.get_user(settings.twitch_bot_nick)
        if not user:
            raise RuntimeError("Unable to resolve bot user id; set TWITCH_BOT_ID to numeric user id.")
        bot_id = user["id"]
    owner_id = settings.twitch_owner_id or bot_id
    bot = JishBot(channels, bot_id=bot_id, owner_id=owner_id)
    await asyncio.gather(bot.start(), start_web())


if __name__ == "__main__":
    asyncio.run(main())
