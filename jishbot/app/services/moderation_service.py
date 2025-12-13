import json
import re
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

from jishbot.app.db import database

MessageRecord = Tuple[float, str]

_recent_messages: Dict[str, Dict[str, Deque[MessageRecord]]] = defaultdict(lambda: defaultdict(deque))

URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)


async def _record_infraction(channel_id: str, user_id: str, user_name: str, reason: str) -> None:
    db = await database.get_db()
    await db.execute(
        "INSERT INTO infractions(channel_id, user_id, user_name, type, reason, created_at) VALUES(?,?,?,?,?,?)",
        (channel_id, user_id, user_name, "timeout", reason, int(time.time())),
    )
    await db.commit()


async def _get_filters(channel_id: str):
    db = await database.get_db()
    async with db.execute(
        "SELECT type, pattern FROM filters WHERE channel_id=? AND enabled=1", (channel_id,)
    ) as cursor:
        return await cursor.fetchall()


async def _get_link_settings(channel_id: str) -> dict:
    db = await database.get_db()
    async with db.execute(
        """
        SELECT enabled, allow_mod, allow_sub, allow_regular, allowed_domains_json
        FROM link_settings WHERE channel_id=?
        """,
        (channel_id,),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return {
            "enabled": 1,
            "allow_mod": 1,
            "allow_sub": 1,
            "allow_regular": 1,
            "allowed_domains": [],
        }
    return {
        "enabled": row["enabled"],
        "allow_mod": row["allow_mod"],
        "allow_sub": row["allow_sub"],
        "allow_regular": row["allow_regular"],
        "allowed_domains": json.loads(row["allowed_domains_json"] or "[]"),
    }


def _caps_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    upper = [c for c in letters if c.isupper()]
    return len(upper) / len(letters)


def _symbol_ratio(text: str) -> float:
    symbols = [c for c in text if not c.isalnum() and not c.isspace()]
    if not text:
        return 0.0
    return len(symbols) / len(text)


async def check_message(
    channel_id: str,
    user_id: str,
    user_name: str,
    content: str,
    is_mod: bool,
    is_sub: bool,
    is_regular: bool,
) -> Optional[str]:
    """Return reason string when a moderation action should occur."""
    if is_mod:
        return None
    now = time.time()
    recent = _recent_messages[channel_id][user_id]
    recent.append((now, content))
    while recent and now - recent[0][0] > 15:
        recent.popleft()

    # Flood detection
    if len(recent) >= 6 and now - recent[0][0] <= 10:
        await _record_infraction(channel_id, user_id, user_name, "message flood")
        return "message flood"

    # Repeated message
    same_count = sum(1 for _, c in recent if c == content)
    if same_count >= 3:
        await _record_infraction(channel_id, user_id, user_name, "repeated message")
        return "repeated message"

    # Caps and symbol spam
    if len(content) > 15 and _caps_ratio(content) > 0.7:
        await _record_infraction(channel_id, user_id, user_name, "caps spam")
        return "caps spam"
    if len(content) > 10 and _symbol_ratio(content) > 0.6:
        await _record_infraction(channel_id, user_id, user_name, "symbol spam")
        return "symbol spam"

    # Filters
    for row in await _get_filters(channel_id):
        ptype, pattern = row["type"], row["pattern"]
        if ptype == "regex":
            if re.search(pattern, content, re.IGNORECASE):
                await _record_infraction(channel_id, user_id, user_name, f"filter regex: {pattern}")
                return "filtered regex"
        elif ptype == "word":
            tokens = {w.lower() for w in re.findall(r"[\\w']+", content)}
            if pattern.lower() in tokens:
                await _record_infraction(channel_id, user_id, user_name, f"filter word: {pattern}")
                return "filtered word"
        else:  # phrase
            if pattern.lower() in content.lower():
                await _record_infraction(channel_id, user_id, user_name, f"filter phrase: {pattern}")
                return "filtered phrase"

    # Link protection
    link_settings = await _get_link_settings(channel_id)
    if link_settings["enabled"]:
        if is_mod and link_settings["allow_mod"]:
            return None
        if is_sub and link_settings["allow_sub"]:
            return None
        if is_regular and link_settings["allow_regular"]:
            return None
        match = URL_REGEX.search(content)
        if match:
            url = match.group(0)
            allowed = any(domain.lower() in url.lower() for domain in link_settings["allowed_domains"])
            if not allowed:
                await _record_infraction(channel_id, user_id, user_name, "link protection")
                return "link protection"
    return None
