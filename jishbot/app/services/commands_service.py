import re
import time
from typing import Any, List, Optional

from jishbot.app.db import database
from jishbot.app.services import counters_service, cooldowns_service, permissions_service, twitch_api_service


async def list_command_names(channel_id: str) -> List[str]:
    channel_id = channel_id.lower()
    db = await database.get_db()
    async with db.execute(
        "SELECT name FROM commands WHERE lower(channel_id)=? AND enabled=1 ORDER BY name", (channel_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [row["name"] for row in rows]


async def list_allowed_command_names(channel_id: str, msg: Any) -> List[str]:
    channel_id = channel_id.lower()
    db = await database.get_db()
    async with db.execute(
        "SELECT name, permission FROM commands WHERE lower(channel_id)=? AND enabled=1 ORDER BY name",
        (channel_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    allowed = []
    for row in rows:
        if await permissions_service.has_permission(msg, row["permission"]):
            allowed.append(row["name"])
    return allowed


async def get_command(channel_id: str, name: str) -> Optional[dict]:
    channel_id = channel_id.lower()
    db = await database.get_db()
    async with db.execute(
        "SELECT * FROM commands WHERE lower(channel_id)=? AND name=? AND enabled=1",
        (channel_id, name),
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            return None
        return dict(row)


async def add_or_update_command(
    channel_id: str,
    name: str,
    response: str,
    permission: str = "everyone",
    cooldown_global: int = 0,
    cooldown_user: int = 0,
) -> None:
    channel_id = channel_id.lower()
    db = await database.get_db()
    now = int(time.time())
    await db.execute(
        """
        INSERT INTO commands(channel_id, name, response, permission, cooldown_global, cooldown_user, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(channel_id, name)
        DO UPDATE SET response=excluded.response, permission=excluded.permission,
                      cooldown_global=excluded.cooldown_global, cooldown_user=excluded.cooldown_user,
                      updated_at=excluded.updated_at
        """,
        (channel_id, name, response, permission, cooldown_global, cooldown_user, now, now),
    )
    await db.commit()


async def delete_command(channel_id: str, name: str) -> None:
    db = await database.get_db()
    await db.execute("DELETE FROM commands WHERE channel_id=? AND name=?", (channel_id, name))
    await db.commit()


async def _replace_variables(command: dict, msg: Any) -> str:
    content = command["response"]
    channel_login = msg.channel.name
    author = msg.author.name if msg.author else "someone"
    replacements = {
        "${user}": author,
        "${channel}": channel_login,
    }
    if "${count}" in content:
        count = await counters_service.increment_counter(command["channel_id"], f"cmd:{command['name']}")
        replacements["${count}"] = str(count)
    if "${uptime}" in content:
        replacements["${uptime}"] = await twitch_api_service.get_stream_uptime(channel_login)
    if "${game}" in content or "${title}" in content:
        info = await twitch_api_service.get_channel_info(channel_login)
        replacements["${game}"] = info["game_name"] if info else "offline"
        replacements["${title}"] = info["title"] if info else "offline"

    for key, val in replacements.items():
        content = content.replace(key, val)
    return content


async def can_run_command(command: dict, msg: Any) -> bool:
    allowed = await permissions_service.has_permission(msg, command["permission"])
    if not allowed:
        return False
    author = msg.author
    if not author:
        return False
    return cooldowns_service.cooldowns.check_and_set(
        command["channel_id"].lower(),
        command["name"],
        str(author.id),
        command.get("cooldown_global", 0),
        command.get("cooldown_user", 0),
    )


async def execute_command(command: dict, msg: Any) -> Optional[str]:
    if not await can_run_command(command, msg):
        return None
    return await _replace_variables(command, msg)
