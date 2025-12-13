import asyncio
import json
import random
import time
from typing import Awaitable, Callable, Dict, Tuple

from jishbot.app.db import database

SendFunc = Callable[[str, str], Awaitable[None]]


class TimersService:
    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task] = {}
        self._last_activity: Dict[str, float] = {}
        self._last_fire: Dict[Tuple[str, int], float] = {}

    async def _fetch_timers(self, channel_id: str):
        db = await database.get_db()
        async with db.execute(
            "SELECT id, name, messages_json, interval_minutes, require_chat_activity FROM timers WHERE channel_id=? AND enabled=1",
            (channel_id,),
        ) as cursor:
            return await cursor.fetchall()

    def note_activity(self, channel_id: str) -> None:
        self._last_activity[channel_id] = time.time()

    async def start(self, channel_id: str, send_func: SendFunc) -> None:
        if channel_id in self._tasks:
            return
        self._last_activity.setdefault(channel_id, time.time())
        self._tasks[channel_id] = asyncio.create_task(self._runner(channel_id, send_func))

    async def _runner(self, channel_id: str, send_func: SendFunc) -> None:
        while True:
            now = time.time()
            timers = await self._fetch_timers(channel_id)
            for row in timers:
                last_fire = self._last_fire.get((channel_id, row["id"]), 0)
                if now - last_fire < row["interval_minutes"] * 60:
                    continue
                if row["require_chat_activity"]:
                    last_activity = self._last_activity.get(channel_id, 0)
                    if last_activity < last_fire or now - last_activity > row["interval_minutes"] * 60:
                        continue
                messages = json.loads(row["messages_json"])
                if not messages:
                    continue
                message = random.choice(messages)
                await send_func(channel_id, message)
                self._last_fire[(channel_id, row["id"])] = now
            await asyncio.sleep(10)

    async def stop_all(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()


timers_service = TimersService()
