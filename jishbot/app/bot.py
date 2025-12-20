import asyncio
import json
import logging
import random
import time
from typing import Dict

from twitchio.ext import commands

from jishbot.app.db import database
from jishbot.app.services import (
    commands_service,
    counters_service,
    giveaways_service,
    moderation_service,
    permissions_service,
    timers_service,
    twitch_api_service,
)
from jishbot.app.settings import settings

log = logging.getLogger(__name__)


class JishBot(commands.Bot):
    def __init__(self, channels: list[str], bot_id: str, owner_id: str | None) -> None:
        super().__init__(
            client_id=settings.twitch_client_id,
            client_secret=settings.twitch_client_secret,
            bot_id=bot_id,
            owner_id=owner_id,
            prefix="!",
            initial_channels=[c.lower() for c in channels],
            nick=settings.twitch_bot_nick,
            token=settings.twitch_bot_token,
        )
        self.message_queues: Dict[str, asyncio.Queue[str]] = {}
        self.sender_tasks: Dict[str, asyncio.Task] = {}

    async def event_ready(self):
        log.info("Connected to Twitch")
        for ch in self.connected_channels:
            await self._ensure_sender(ch.name)
            await timers_service.timers_service.start(ch.name, self.queue_message)

    async def event_message(self, message):
        if message.echo:
            return
        channel_id = message.channel.name.lower()
        timers_service.timers_service.note_activity(channel_id)
        await giveaways_service.handle_message(
            channel_id, str(message.author.id), message.author.name, message.content
        )

        # Moderation
        reason = await moderation_service.check_message(
            channel_id,
            str(message.author.id),
            message.author.name,
            message.content,
            message.author.is_mod,
            message.author.is_subscriber,
            await permissions_service.is_regular(channel_id, str(message.author.id)),
        )
        if reason:
            try:
                await message.channel.timeout(message.author.name, duration=15, reason=reason)
            except Exception:
                log.exception("Failed to timeout user")
            return

        await self.handle_commands(message)

    async def _ensure_sender(self, channel_name: str) -> None:
        if channel_name in self.sender_tasks:
            return
        queue: asyncio.Queue[str] = asyncio.Queue()
        self.message_queues[channel_name] = queue
        self.sender_tasks[channel_name] = asyncio.create_task(self._sender_loop(channel_name, queue))

    async def queue_message(self, channel_name: str, content: str) -> None:
        await self._ensure_sender(channel_name)
        await self.message_queues[channel_name].put(content)

    async def _sender_loop(self, channel_name: str, queue: asyncio.Queue[str]) -> None:
        while True:
            message = await queue.get()
            channel = self.get_channel(channel_name)
            if channel:
                try:
                    await channel.send(message)
                except Exception:
                    log.exception("Failed to send message to %s", channel_name)
            await asyncio.sleep(settings.message_delay_seconds)

    async def handle_commands(self, message):
        content = message.content.strip()
        if not content.startswith("!"):
            return
        parts = content[1:].split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]
        channel_id = message.channel.name.lower()

        # Built-in commands
        if cmd == "commands":
            names = await commands_service.list_allowed_command_names(channel_id, message)
            snippet = ", ".join(names[:25])
            if len(names) > 25:
                snippet += f" (+{len(names)-25} more)"
            await self.queue_message(channel_id, f"Commands: {snippet}")
            return

        if cmd == "uptime":
            uptime = await twitch_api_service.get_stream_uptime(channel_id)
            await self.queue_message(channel_id, uptime)
            return

        if cmd == "game":
            if args:
                if not await permissions_service.has_permission(message, "moderator"):
                    return
                new_game = " ".join(args)
                ok = await twitch_api_service.set_channel_game(channel_id, new_game)
                await self.queue_message(channel_id, "Game updated" if ok else "Failed to set game")
            else:
                info = await twitch_api_service.get_channel_info(channel_id)
                await self.queue_message(channel_id, info["game_name"] if info else "offline")
            return

        if cmd == "title":
            if args:
                if not await permissions_service.has_permission(message, "moderator"):
                    return
                new_title = " ".join(args)
                ok = await twitch_api_service.set_channel_title(channel_id, new_title)
                await self.queue_message(channel_id, "Title updated" if ok else "Failed to set title")
            else:
                info = await twitch_api_service.get_channel_info(channel_id)
                await self.queue_message(channel_id, info["title"] if info else "offline")
            return

        if cmd == "slow":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            if not args:
                await self.queue_message(channel_id, "Usage: !slow <seconds> (mods+)")
                return
            await self.queue_message(channel_id, f"/slow {args[0]}")
            return

        if cmd == "slowoff":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            await self.queue_message(channel_id, "/slowoff")
            return

        if cmd == "emoteonly":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            await self.queue_message(channel_id, "/emoteonly")
            return

        if cmd == "emoteoff":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            await self.queue_message(channel_id, "/emoteonlyoff")
            return

        if cmd == "clear":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            await self.queue_message(channel_id, "/clear")
            return

        if cmd == "shoutout":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            if not args:
                await self.queue_message(channel_id, "Usage: !shoutout <user> (mods+)")
                return
            target = args[0].lstrip("@")
            await self.queue_message(channel_id, f"/shoutout {target}")
            return

        if cmd == "permit":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            if not args:
                await self.queue_message(channel_id, "Usage: !permit <user> (mods+)")
                return
            target = args[0].lstrip("@")
            moderation_service.permit_user(channel_id, target.lower())
            await self.queue_message(channel_id, f"{target} can post a link for 60s.")
            return

        if cmd == "poll":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            if len(args) < 3:
                await self.queue_message(channel_id, "Usage: !poll <duration_sec> <question> | <option1> | <option2> (...) (mods+)")
                return
            try:
                duration = int(args[0])
            except ValueError:
                await self.queue_message(channel_id, "Poll duration must be a number of seconds.")
                return
            rest = " ".join(args[1:])
            parts = [p.strip() for p in rest.split("|") if p.strip()]
            if len(parts) < 3:
                await self.queue_message(channel_id, "Usage: !poll <duration_sec> <question> | <option1> | <option2> (...) (mods+)")
                return
            question = parts[0]
            options = parts[1:]
            ok = await twitch_api_service.start_poll(question, options, duration)
            await self.queue_message(channel_id, "Poll started." if ok else "Failed to start poll (check token/scopes).")
            return

        if cmd == "prediction":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            if len(args) < 3:
                await self.queue_message(channel_id, "Usage: !prediction <duration_sec> <title> | <outcome1> | <outcome2> (mods+)")
                return
            try:
                duration = int(args[0])
            except ValueError:
                await self.queue_message(channel_id, "Prediction duration must be a number of seconds.")
                return
            rest = " ".join(args[1:])
            parts = [p.strip() for p in rest.split("|") if p.strip()]
            if len(parts) < 3:
                await self.queue_message(channel_id, "Usage: !prediction <duration_sec> <title> | <outcome1> | <outcome2> (mods+)")
                return
            title = parts[0]
            outcomes = parts[1:3]
            ok = await twitch_api_service.start_prediction(title, outcomes, duration)
            await self.queue_message(channel_id, "Prediction started." if ok else "Failed to start prediction (check token/scopes).")
            return

        if cmd == "accountage":
            target = args[0].lstrip("@") if args else (message.author.name if message.author else None)
            if not target:
                await self.queue_message(channel_id, "Usage: !accountage [user]")
                return
            age = await twitch_api_service.get_account_age(target)
            if age:
                await self.queue_message(channel_id, f"{target} account created {age}.")
            else:
                await self.queue_message(channel_id, "Could not fetch account age.")
            return

        if cmd == "followage":
            follower = message.author.name if message.author else None
            target = channel_id
            if len(args) == 1:
                follower = args[0].lstrip("@")
            elif len(args) >= 2:
                follower = args[0].lstrip("@")
                target = args[1].lstrip("@").lower()
            if not follower:
                await self.queue_message(channel_id, "Usage: !followage [follower] [target_channel]")
                return
            duration = await twitch_api_service.get_follow_duration(follower.lower(), target.lower())
            if duration:
                await self.queue_message(channel_id, f"{follower} has been following {target} for {duration}.")
            else:
                await self.queue_message(channel_id, f"{follower} is not following {target}.")
            return

        if cmd == "8ball":
            question = " ".join(args)
            if not question:
                await self.queue_message(channel_id, "Usage: !8ball <question>")
                return
            answers = [
                "It is certain.",
                "Without a doubt.",
                "Yes - definitely.",
                "Most likely.",
                "Outlook good.",
                "Ask again later.",
                "Better not tell you now.",
                "Cannot predict now.",
                "Concentrate and ask again.",
                "My reply is no.",
                "Outlook not so good.",
                "Very doubtful.",
            ]
            await self.queue_message(channel_id, random.choice(answers))
            return

        if cmd == "regular":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            if not args:
                await self.queue_message(channel_id, "Usage: !regular add/remove <user> or !regular list (mods+)")
                return
            action = args[0]
            if action == "add" and len(args) >= 2:
                await self._add_regular(channel_id, args[1])
                await self.queue_message(channel_id, f"{args[1]} added as regular.")
            elif action == "remove" and len(args) >= 2:
                await self._remove_regular(channel_id, args[1])
                await self.queue_message(channel_id, f"{args[1]} removed from regulars.")
            elif action == "list":
                regs = await self._list_regulars(channel_id)
                await self.queue_message(channel_id, f"Regulars: {', '.join(regs) or 'none'}")
            else:
                await self.queue_message(channel_id, "Usage: !regular add/remove <user> or !regular list (mods+)")
            return

        if cmd == "command":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            if not args:
                await self.queue_message(
                    channel_id,
                    "Usage: !command add <name> <response> | edit <name> <response> | del <name> (mods+)",
                )
                return
            sub = args[0]
            if sub == "add" and len(args) >= 3:
                name = args[1]
                response = " ".join(args[2:])
                await commands_service.add_or_update_command(channel_id, name, response)
                await self.queue_message(channel_id, f"Command !{name} added.")
            elif sub == "edit" and len(args) >= 3:
                name = args[1]
                response = " ".join(args[2:])
                await commands_service.add_or_update_command(channel_id, name, response)
                await self.queue_message(channel_id, f"Command !{name} updated.")
            elif sub == "del" and len(args) >= 2:
                await commands_service.delete_command(channel_id, args[1])
                await self.queue_message(channel_id, f"Command !{args[1]} deleted.")
            else:
                await self.queue_message(
                    channel_id,
                    "Usage: !command add <name> <response> | edit <name> <response> | del <name> (mods+)",
                )
            return

        if cmd == "timer":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            if not args:
                await self.queue_message(
                    channel_id, "Usage: !timer add <name> <interval_minutes> <msg1|msg2> | del <name> (mods+)"
                )
                return
            sub = args[0]
            if sub in {"add", "edit"} and len(args) >= 4:
                name = args[1]
                interval = int(args[2])
                messages = " ".join(args[3:]).split("|")
                await self._upsert_timer(channel_id, name, interval, messages)
                await self.queue_message(channel_id, f"Timer {name} saved.")
            elif sub == "del" and len(args) >= 2:
                await self._delete_timer(channel_id, args[1])
                await self.queue_message(channel_id, f"Timer {args[1]} deleted.")
            else:
                await self.queue_message(
                    channel_id, "Usage: !timer add <name> <interval_minutes> <msg1|msg2> | del <name> (mods+)"
                )
            return

        if cmd == "giveaway":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            if not args:
                await self.queue_message(channel_id, "Usage: !giveaway start <keyword> | pick | end (mods/broadcaster)")
                return
            action = args[0]
            if action == "start" and len(args) >= 2:
                keyword = args[1]
                await giveaways_service.start_giveaway(channel_id, keyword)
                await self.queue_message(channel_id, f"Giveaway started with keyword '{keyword}'.")
            elif action == "end":
                await giveaways_service.end_giveaway(channel_id)
                await self.queue_message(channel_id, "Giveaway ended.")
            elif action == "pick":
                winner = await giveaways_service.pick_winner(channel_id)
                if winner:
                    await self.queue_message(channel_id, f"Winner: {winner[1]}!")
                else:
                    await self.queue_message(channel_id, "No entries to pick from.")
            else:
                await self.queue_message(
                    channel_id, "Usage: !giveaway start <keyword> | pick | end (mods/broadcaster)"
                )
            return

        if cmd == "counter":
            if not await permissions_service.has_permission(message, "moderator"):
                return
            if not args:
                await self.queue_message(channel_id, "Usage: !counter set <key> <value> | inc <key> | dec <key> (mods+)")
                return
            action = args[0]
            if action == "set" and len(args) == 3:
                key, value = args[1], int(args[2])
                await counters_service.set_counter(channel_id, key, value)
                await self.queue_message(channel_id, f"{key} set to {value}")
            elif action == "inc" and len(args) >= 2:
                key = args[1]
                value = await counters_service.increment_counter(channel_id, key, 1)
                await self.queue_message(channel_id, f"{key} is now {value}")
            elif action == "dec" and len(args) >= 2:
                key = args[1]
                value = await counters_service.increment_counter(channel_id, key, -1)
                await self.queue_message(channel_id, f"{key} is now {value}")
            else:
                await self.queue_message(
                    channel_id, "Usage: !counter set <key> <value> | inc <key> | dec <key> (mods+)"
                )
            return

        # Custom command
        command = await commands_service.get_command(channel_id, cmd)
        if command:
            response = await commands_service.execute_command(command, message)
            if response:
                await self.queue_message(channel_id, response)

    async def _add_regular(self, channel_id: str, user_name: str) -> None:
        db = await database.get_db()
        await db.execute(
            """
            INSERT INTO regulars(channel_id, user_id, user_name, added_at)
            VALUES(?,?,?,?)
            ON CONFLICT(channel_id, user_id) DO UPDATE SET user_name=excluded.user_name
            """,
            (channel_id, user_name.lower(), user_name, int(time.time())),
        )
        await db.commit()

    async def _remove_regular(self, channel_id: str, user_name: str) -> None:
        db = await database.get_db()
        await db.execute("DELETE FROM regulars WHERE channel_id=? AND user_id=?", (channel_id, user_name.lower()))
        await db.commit()

    async def _list_regulars(self, channel_id: str):
        db = await database.get_db()
        async with db.execute("SELECT user_name FROM regulars WHERE channel_id=?", (channel_id,)) as cursor:
            rows = await cursor.fetchall()
            return [row["user_name"] for row in rows]

    async def _upsert_timer(self, channel_id: str, name: str, interval: int, messages):
        db = await database.get_db()
        await db.execute(
            """
            INSERT INTO timers(channel_id, name, messages_json, interval_minutes, require_chat_activity, enabled)
            VALUES(?,?,?,?,0,1)
            ON CONFLICT(channel_id, name) DO UPDATE SET messages_json=excluded.messages_json,
            interval_minutes=excluded.interval_minutes
            """,
            (channel_id, name, json.dumps(messages), interval),
        )
        await db.commit()

    async def _delete_timer(self, channel_id: str, name: str):
        db = await database.get_db()
        await db.execute("DELETE FROM timers WHERE channel_id=? AND name=?", (channel_id, name))
        await db.commit()
