import time

import aiosqlite


SCHEMA_VERSION = 2


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL,
            applied_at INTEGER NOT NULL
        )
        """
    )
    await db.commit()
    async with db.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1") as cursor:
        row = await cursor.fetchone()
    current_version = row["version"] if row else 0
    if current_version < 1:
        await apply_v1(db)
        current_version = 1
    if current_version < 2:
        await apply_v2(db)
        current_version = 2
    if row is None or row["version"] != current_version:
        await db.execute("DELETE FROM schema_version")
        await db.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
            (current_version, int(time.time())),
        )
        await db.commit()


async def apply_v1(db: aiosqlite.Connection) -> None:
    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS channels(
            channel_id TEXT PRIMARY KEY,
            channel_name TEXT UNIQUE NOT NULL,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS commands(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            name TEXT NOT NULL,
            response TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            permission TEXT NOT NULL DEFAULT 'everyone',
            cooldown_global INTEGER NOT NULL DEFAULT 0,
            cooldown_user INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_commands_channel_name ON commands(channel_id, name);

        CREATE TABLE IF NOT EXISTS timers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            name TEXT NOT NULL,
            messages_json TEXT NOT NULL,
            interval_minutes INTEGER NOT NULL DEFAULT 5,
            require_chat_activity INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_timers_channel_name ON timers(channel_id, name);

        CREATE TABLE IF NOT EXISTS filters(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            type TEXT NOT NULL,
            pattern TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS link_settings(
            channel_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            allow_mod INTEGER NOT NULL DEFAULT 1,
            allow_sub INTEGER NOT NULL DEFAULT 1,
            allow_regular INTEGER NOT NULL DEFAULT 1,
            allowed_domains_json TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS regulars(
            channel_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            added_at INTEGER NOT NULL,
            PRIMARY KEY(channel_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS giveaways(
            channel_id TEXT PRIMARY KEY,
            is_active INTEGER NOT NULL DEFAULT 0,
            keyword TEXT,
            entries_json TEXT NOT NULL DEFAULT '[]',
            started_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS counters(
            channel_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(channel_id, key)
        );

        CREATE TABLE IF NOT EXISTS infractions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            type TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        """
    )
    await db.commit()


async def apply_v2(db: aiosqlite.Connection) -> None:
    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS notifications(
            channel_id TEXT PRIMARY KEY,
            webhook_url TEXT,
            last_status TEXT,
            last_notified_at INTEGER
        );
        """
    )
    await db.commit()
