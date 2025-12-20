import asyncio
import time
from typing import Optional

import httpx

from jishbot.app.settings import settings

_app_token: Optional[str] = None
_app_token_expiry = 0.0
_user_cache: dict[str, dict] = {}
_creation_cache: dict[str, str] = {}


async def _fetch_app_token() -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": settings.twitch_client_id,
                "client_secret": settings.twitch_client_secret,
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"], time.time() + data.get("expires_in", 3600) - 60


async def _get_app_token() -> str:
    global _app_token, _app_token_expiry
    if not _app_token or time.time() >= _app_token_expiry:
        _app_token, _app_token_expiry = await _fetch_app_token()
    return _app_token


async def _auth_headers(use_app_token: bool = True, use_broadcaster_token: bool = False) -> dict:
    token = settings.twitch_bot_token.replace("oauth:", "") if settings.twitch_bot_token else ""
    if use_broadcaster_token and settings.twitch_broadcaster_token:
        token = settings.twitch_broadcaster_token.replace("oauth:", "")
    if use_app_token or not token:
        token = await _get_app_token()
    return {
        "Client-ID": settings.twitch_client_id,
        "Authorization": f"Bearer {token}",
    }


async def get_user(channel_login: str) -> Optional[dict]:
    if channel_login in _user_cache:
        return _user_cache[channel_login]
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.twitch.tv/helix/users",
            headers=await _auth_headers(),
            params={"login": channel_login},
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", [])
        if not data:
            return None
        _user_cache[channel_login] = data[0]
        return data[0]


async def get_user_creation(login: str) -> Optional[str]:
    login = login.lower()
    if login in _creation_cache:
        return _creation_cache[login]
    user = await get_user(login)
    if not user:
        return None
    created_at = user.get("created_at")
    if created_at:
        _creation_cache[login] = created_at
    return created_at


async def get_stream_uptime(channel_login: str) -> str:
    user = await get_user(channel_login)
    if not user:
        return "offline"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.twitch.tv/helix/streams",
            headers=await _auth_headers(),
            params={"user_id": user["id"]},
        )
        if resp.status_code != 200:
            return "offline"
        data = resp.json().get("data", [])
        if not data:
            return "offline"
        started_at = data[0]["started_at"]
        # Basic human diff
        from datetime import datetime, timezone

        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - started
        hours, remainder = divmod(diff.seconds, 3600)
        minutes = remainder // 60
        days = diff.days
        if days > 0:
            return f"live for {days}d {hours}h {minutes}m"
        return f"live for {hours}h {minutes}m"


def _humanize_duration(seconds: int) -> str:
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    months, days = divmod(days, 30)
    years, months = divmod(months, 12)
    parts = []
    for value, label in ((years, "year"), (months, "month"), (days, "day"), (hours, "hour"), (minutes, "minute")):
        if value:
            parts.append(f"{value} {label}{'s' if value != 1 else ''}")
    return " ".join(parts) if parts else "just now"


async def get_account_age(login: str) -> Optional[str]:
    created_at = await get_user_creation(login)
    if not created_at:
        return None
    from datetime import datetime, timezone

    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    seconds = int((now - created).total_seconds())
    return _humanize_duration(seconds) + " ago"


async def get_follow_duration(follower_login: str, broadcaster_login: str) -> Optional[str]:
    follower = await get_user(follower_login)
    broadcaster = await get_user(broadcaster_login)
    if not follower or not broadcaster:
        return None
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.twitch.tv/helix/users/follows",
            headers=await _auth_headers(),
            params={"from_id": follower["id"], "to_id": broadcaster["id"]},
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", [])
        if not data:
            return None
        followed_at = data[0].get("followed_at")
        if not followed_at:
            return None
        from datetime import datetime, timezone

        followed = datetime.fromisoformat(followed_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        seconds = int((now - followed).total_seconds())
        return _humanize_duration(seconds)


async def get_channel_info(channel_login: str) -> Optional[dict]:
    user = await get_user(channel_login)
    if not user:
        return None
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.twitch.tv/helix/channels",
            headers=await _auth_headers(),
            params={"broadcaster_id": user["id"]},
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", [])
        return data[0] if data else None


async def set_channel_game(channel_login: str, game_name: str) -> bool:
    broadcaster_id = settings.twitch_broadcaster_id or settings.twitch_bot_id
    if not broadcaster_id:
        user = await get_user(channel_login)
        broadcaster_id = user["id"] if user else None
    if not broadcaster_id:
        return False
    async with httpx.AsyncClient() as client:
        search = await client.get(
            "https://api.twitch.tv/helix/games",
            headers=await _auth_headers(),
            params={"name": game_name},
        )
        game_data = search.json().get("data", [])
        if not game_data:
            return False
        game_id = game_data[0]["id"]
        resp = await client.patch(
            "https://api.twitch.tv/helix/channels",
            headers=await _auth_headers(use_app_token=False, use_broadcaster_token=True),
            params={"broadcaster_id": broadcaster_id},
            json={"game_id": game_id},
        )
        return resp.status_code in (200, 204)


async def set_channel_title(channel_login: str, title: str) -> bool:
    broadcaster_id = settings.twitch_broadcaster_id or settings.twitch_bot_id
    if not broadcaster_id:
        user = await get_user(channel_login)
        broadcaster_id = user["id"] if user else None
    if not broadcaster_id:
        return False
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            "https://api.twitch.tv/helix/channels",
            headers=await _auth_headers(use_app_token=False, use_broadcaster_token=True),
            params={"broadcaster_id": broadcaster_id},
            json={"title": title[:140]},
        )
        return resp.status_code in (200, 204)


async def start_poll(title: str, choices: list[str], duration: int = 120) -> bool:
    broadcaster_id = settings.twitch_broadcaster_id or settings.twitch_bot_id
    if not broadcaster_id:
        return False
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.twitch.tv/helix/polls",
            headers=await _auth_headers(use_app_token=False, use_broadcaster_token=True),
            json={
                "broadcaster_id": broadcaster_id,
                "title": title[:60],
                "choices": [{"title": c[:25]} for c in choices[:5]],
                "duration": max(15, min(duration, 1800)),
            },
        )
        return resp.status_code in (200, 201)


async def start_prediction(title: str, outcomes: list[str], duration: int = 120) -> bool:
    broadcaster_id = settings.twitch_broadcaster_id or settings.twitch_bot_id
    if not broadcaster_id:
        return False
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.twitch.tv/helix/predictions",
            headers=await _auth_headers(use_app_token=False, use_broadcaster_token=True),
            json={
                "broadcaster_id": broadcaster_id,
                "title": title[:45],
                "outcomes": [{"title": o[:25]} for o in outcomes[:2]],
                "prediction_window": max(30, min(duration, 1800)),
            },
        )
        return resp.status_code in (200, 201)
