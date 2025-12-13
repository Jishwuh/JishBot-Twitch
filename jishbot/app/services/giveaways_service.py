import json
import random
import time
from typing import List, Optional, Tuple

from jishbot.app.db import database


async def start_giveaway(channel_id: str, keyword: str) -> None:
    db = await database.get_db()
    await db.execute(
        """
        INSERT INTO giveaways(channel_id, is_active, keyword, entries_json, started_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(channel_id) DO UPDATE SET is_active=excluded.is_active, keyword=excluded.keyword,
        entries_json=excluded.entries_json, started_at=excluded.started_at
        """,
        (channel_id, 1, keyword.lower(), json.dumps([]), int(time.time())),
    )
    await db.commit()


async def end_giveaway(channel_id: str) -> None:
    db = await database.get_db()
    await db.execute(
        "UPDATE giveaways SET is_active=0, keyword=NULL, entries_json='[]', started_at=NULL WHERE channel_id=?",
        (channel_id,),
    )
    await db.commit()


async def _get_giveaway(channel_id: str) -> Optional[dict]:
    db = await database.get_db()
    async with db.execute(
        "SELECT is_active, keyword, entries_json FROM giveaways WHERE channel_id=?",
        (channel_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return None
    return {
        "is_active": row["is_active"],
        "keyword": row["keyword"],
        "entries": json.loads(row["entries_json"]),
    }


async def handle_message(channel_id: str, user_id: str, user_name: str, content: str) -> bool:
    giveaway = await _get_giveaway(channel_id)
    if not giveaway or not giveaway["is_active"]:
        return False
    keyword = giveaway["keyword"]
    if not keyword or keyword.lower() not in content.lower().split():
        return False
    entries: List[dict] = giveaway["entries"]
    if any(e["user_id"] == user_id for e in entries):
        return False
    entries.append({"user_id": user_id, "user_name": user_name})
    db = await database.get_db()
    await db.execute(
        "UPDATE giveaways SET entries_json=? WHERE channel_id=?",
        (json.dumps(entries), channel_id),
    )
    await db.commit()
    return True


async def pick_winner(channel_id: str) -> Optional[Tuple[str, str]]:
    giveaway = await _get_giveaway(channel_id)
    if not giveaway or not giveaway["entries"]:
        return None
    winner = random.choice(giveaway["entries"])
    return winner["user_id"], winner["user_name"]


async def get_entries(channel_id: str) -> List[dict]:
    giveaway = await _get_giveaway(channel_id)
    return giveaway["entries"] if giveaway else []
