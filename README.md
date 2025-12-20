# 🚀 JishBot

Twitch chatbot + FastAPI dashboard, powered by TwitchIO and SQLite. Async, rate-limited, and ready for multi-channel.

## ⚡ Quickstart
```bash
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt
cp .env.example .env
python -m jishbot.scripts.init_db
python -m jishbot.app.main
```

## 🔑 Configure `.env`
- `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET`
- `TWITCH_BOT_TOKEN` (OAuth, prefixed with `oauth:`)
- `TWITCH_BROADCASTER_TOKEN` (optional; if set, used for !game/!title/polls/predictions)
- `TWITCH_BOT_NICK` (bot username)
- `TWITCH_BOT_ID` (numeric user id; auto-resolves from nick if blank)
- `TWITCH_BROADCASTER_ID` (optional; numeric id for broadcaster; falls back to bot id/login lookup)
- `TWITCH_OWNER_ID` (optional; defaults to bot id)
- `TWITCH_CHANNELS` (comma list, no `#`)
- `WEB_SECRET_KEY` (dashboard/login & API header)
- `BASE_URL` (for OAuth later)
- `SQLITE_PATH` (default `./jishbot.db`)
- `LOG_LEVEL` (INFO/DEBUG/etc)
- `DISCORD_WEBHOOK_URL` (optional per-channel via dashboard; leave blank if unused)

### Twitch token scopes (important)
- You can use:
  - One token for everything (put in `TWITCH_BOT_TOKEN`) that has scopes `channel:manage:broadcast` + `chat:read` + `chat:edit`, and belongs to the broadcaster.
  - Or two tokens: `TWITCH_BOT_TOKEN` for chat (chat:read/chat:edit) and `TWITCH_BROADCASTER_TOKEN` for broadcast actions (game/title/poll/prediction).
- If you use polls/predictions, add scopes `channel:manage:polls` and `channel:manage:predictions` (ideally on the broadcaster token).
- Keep the `oauth:` prefix in env values. `TWITCH_BROADCASTER_ID` can be set if the broadcaster differs from the bot.

## 🖥️ Dashboard
- Go to `http://localhost:8000/login`, enter `WEB_SECRET_KEY`, then manage at `/dashboard`.
- Features: channel picker, create/edit/delete commands, timers, filters, link protection, giveaways, Discord live notifications (with test button).
- API (JSON) uses header `X-Auth-Token: <WEB_SECRET_KEY>`:
  - `GET /health`
  - `GET/POST/DELETE /api/commands/{channel}`
  - `GET/POST/DELETE /api/timers/{channel}`
  - `GET/POST/DELETE /api/filters/{channel}`
  - `GET/POST /api/links/{channel}`
  - `GET/POST /api/giveaways/{channel}`

## 💬 Chat Commands (built-in)
- `!commands`
- `!uptime`
- `!game [new]` (mods+)
- `!title [new]` (mods+)
- `!regular add|remove|list` (mods+)
- `!command add|edit|del` (mods+)
- `!timer add <name> <interval_minutes> <msg1|msg2>` / `!timer del <name>` (mods+)
- `!giveaway start <keyword>` / `pick` / `end` (mods+)
- `!counter set|inc|dec <key> [value]` (mods+)
- `!slow <seconds>` / `!slowoff` (mods+)
- `!emoteonly` / `!emoteoff` (mods+)
- `!clear` (mods+)
- `!shoutout <user>` (mods+)
- `!permit <user>` allow links for 60s (mods+)
- `!poll <duration_sec> <question> | <opt1> | <opt2> [...]` (mods+, scope: channel:manage:polls)
- `!prediction <duration_sec> <title> | <outcome1> | <outcome2>` (mods+, scope: channel:manage:predictions)
- `!accountage [user]`
- `!followage [follower] [channel]`
- `!8ball <question>`
- Custom `!<name>` supports `${user}`, `${channel}`, `${count}`, `${uptime}`, `${game}`, `${title}`.

## 📝 Notes
- Async everywhere; per-channel message queue (~1.6s/send).
- SQLite migrations auto-run on startup.
- Logs respect `LOG_LEVEL`.
