"""
Fetch Twitch user IDs using credentials from .env.

Usage:
  python -m jishbot.scripts.fetch_ids [login]
Defaults to TWITCH_BOT_NICK when login not provided.
"""

import asyncio
import sys

import httpx

from jishbot.app.settings import settings


async def fetch_user_id(login: str) -> None:
    # Get app token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": settings.twitch_client_id,
                "client_secret": settings.twitch_client_secret,
                "grant_type": "client_credentials",
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        # Fetch user info
        user_resp = await client.get(
            "https://api.twitch.tv/helix/users",
            headers={
                "Client-ID": settings.twitch_client_id,
                "Authorization": f"Bearer {access_token}",
            },
            params={"login": login},
            timeout=10,
        )
        user_resp.raise_for_status()
        data = user_resp.json().get("data", [])
        if not data:
            print(f"Login '{login}' not found.")
            return
        user = data[0]
        print(f"Login: {user['login']}")
        print(f"ID: {user['id']}")
        print(f"Display: {user.get('display_name')}")
        print(f"Created at: {user.get('created_at')}")


async def main():
    login = sys.argv[1] if len(sys.argv) > 1 else settings.twitch_bot_nick
    if not login:
        print("No login provided and TWITCH_BOT_NICK not set.")
        return
    await fetch_user_id(login.lower())


if __name__ == "__main__":
    asyncio.run(main())
