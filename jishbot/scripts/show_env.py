"""Utility script to load and print configuration from .env."""

from jishbot.app.settings import settings


def main() -> None:
    print("TWITCH_CLIENT_ID:", settings.twitch_client_id)
    print("TWITCH_CLIENT_SECRET:", "***redacted***" if settings.twitch_client_secret else "")
    print("TWITCH_BOT_TOKEN:", "***redacted***" if settings.twitch_bot_token else "")
    print("TWITCH_BOT_NICK:", settings.twitch_bot_nick)
    print("TWITCH_BOT_ID:", settings.twitch_bot_id)
    print("TWITCH_OWNER_ID:", settings.twitch_owner_id)
    print("TWITCH_CHANNELS:", settings.twitch_channels)
    print("WEB_SECRET_KEY:", "***redacted***" if settings.web_secret_key else "")
    print("BASE_URL:", settings.base_url)
    print("SQLITE_PATH:", settings.sqlite_path)
    print("LOG_LEVEL:", settings.log_level)


if __name__ == "__main__":
    main()
