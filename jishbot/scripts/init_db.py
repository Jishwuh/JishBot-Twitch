import asyncio

from jishbot.app.db import database


async def main():
    await database.get_db()
    await database.close_db()
    print("Database initialized.")


if __name__ == "__main__":
    asyncio.run(main())
