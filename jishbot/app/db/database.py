import aiosqlite

from jishbot.app.settings import settings
from jishbot.app.db import migrations

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Singleton-ish connection; caller should not close."""
    global _db
    if _db is None:
        _db = await aiosqlite.connect(settings.sqlite_path)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA foreign_keys = ON;")
        await migrations.ensure_schema(_db)
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
