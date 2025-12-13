import aiosqlite

from jishbot.app.db import database


async def get_counter(channel_id: str, key: str) -> int:
    db = await database.get_db()
    async with db.execute(
        "SELECT value FROM counters WHERE channel_id=? AND key=?",
        (channel_id, key),
    ) as cursor:
        row = await cursor.fetchone()
        return int(row["value"]) if row else 0


async def set_counter(channel_id: str, key: str, value: int) -> int:
    db = await database.get_db()
    await db.execute(
        """
        INSERT INTO counters(channel_id, key, value) VALUES(?,?,?)
        ON CONFLICT(channel_id, key) DO UPDATE SET value=excluded.value
        """,
        (channel_id, key, value),
    )
    await db.commit()
    return value


async def increment_counter(channel_id: str, key: str, delta: int = 1) -> int:
    value = await get_counter(channel_id, key)
    value += delta
    await set_counter(channel_id, key, value)
    return value
