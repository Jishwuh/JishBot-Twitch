from typing import Any, Literal

from jishbot.app.db import database

PermissionLevel = Literal["everyone", "regular", "subscriber", "moderator", "broadcaster"]

_rank = {
    "everyone": 0,
    "regular": 1,
    "subscriber": 2,
    "moderator": 3,
    "broadcaster": 4,
}


async def is_regular(channel_id: str, user_id: str) -> bool:
    db = await database.get_db()
    async with db.execute(
        "SELECT 1 FROM regulars WHERE channel_id=? AND user_id=? LIMIT 1", (channel_id, user_id)
    ) as cursor:
        return await cursor.fetchone() is not None


async def has_permission(msg: Any, required: PermissionLevel) -> bool:
    author = msg.author
    if author is None:
        return False
    channel_id = ""
    if getattr(msg, "channel", None):
        channel_id = getattr(msg.channel, "id", None) or msg.channel.name
    channel_id = str(channel_id).lower()
    user_id = str(author.id)

    if author.is_broadcaster:
        return True
    if required == "broadcaster":
        return False
    if author.is_mod and _rank["moderator"] >= _rank[required]:
        return True
    if required in ("subscriber", "regular"):
        if author.is_subscriber and _rank["subscriber"] >= _rank[required]:
            return True
        if required == "regular" and await is_regular(channel_id, user_id):
            return True
    return required == "everyone"
