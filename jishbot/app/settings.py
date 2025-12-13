import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv


@dataclass
class Settings:
    twitch_client_id: str
    twitch_client_secret: str
    twitch_bot_token: str
    twitch_bot_nick: str
    twitch_bot_id: str
    twitch_owner_id: str | None = None
    twitch_channels: List[str] = field(default_factory=list)
    web_secret_key: str = "dev-secret"
    base_url: str = "http://localhost:8000"
    sqlite_path: str = "./jishbot.db"
    log_level: str = "INFO"
    message_delay_seconds: float = 1.6  # Twitch limit ~20 msgs / 30s per channel

    @staticmethod
    def load() -> "Settings":
        load_dotenv()
        channels_raw = os.getenv("TWITCH_CHANNELS", "")
        channels = [c.strip().lstrip("#").lower() for c in channels_raw.split(",") if c.strip()]
        return Settings(
            twitch_client_id=os.getenv("TWITCH_CLIENT_ID", ""),
            twitch_client_secret=os.getenv("TWITCH_CLIENT_SECRET", ""),
            twitch_bot_token=os.getenv("TWITCH_BOT_TOKEN", ""),
            twitch_bot_nick=os.getenv("TWITCH_BOT_NICK", ""),
            twitch_bot_id=os.getenv("TWITCH_BOT_ID", os.getenv("TWITCH_BOT_NICK", "")),
            twitch_owner_id=os.getenv("TWITCH_OWNER_ID"),
            twitch_channels=channels,
            web_secret_key=os.getenv("WEB_SECRET_KEY", "dev-secret"),
            base_url=os.getenv("BASE_URL", "http://localhost:8000"),
            sqlite_path=os.getenv("SQLITE_PATH", "./jishbot.db"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


settings = Settings.load()
