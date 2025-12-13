from typing import List, Optional
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from jishbot.app.db import database
from jishbot.app.services import giveaways_service
from jishbot.app.settings import settings

app = FastAPI(title="JishBot Dashboard")
BASE_DIR = Path(__file__).resolve().parent.parent  # points to jishbot/app
templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
AUTH_COOKIE = "auth_token"


def is_authed(request: Request) -> bool:
    return request.cookies.get(AUTH_COOKIE) == settings.web_secret_key


def auth_redirect() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


async def verify_token(x_auth_token: str = Header(...)) -> None:
    if x_auth_token != settings.web_secret_key:
        raise HTTPException(status_code=401, detail="invalid token")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/dashboard")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
async def login_submit(request: Request, token: str = Form(...)):
    if token != settings.web_secret_key:
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Invalid token. Try again."}
        )
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(AUTH_COOKIE, token, httponly=True, max_age=7 * 24 * 3600)
    return response


async def get_channels() -> List[str]:
    channels = settings.twitch_channels
    if channels:
        return channels
    db = await database.get_db()
    async with db.execute("SELECT channel_name FROM channels WHERE is_enabled=1") as cursor:
        rows = await cursor.fetchall()
        return [row["channel_name"].lstrip("#").lower() for row in rows]


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, channel: Optional[str] = None, notice: Optional[str] = None):
    if not is_authed(request):
        return auth_redirect()
    channels = await get_channels()
    active_channel = (channel or (channels[0] if channels else "")).lstrip("#").lower()
    db = await database.get_db()
    # Commands
    async with db.execute(
        "SELECT name, response, permission, cooldown_global, cooldown_user FROM commands WHERE channel_id=? ORDER BY name",
        (active_channel,),
    ) as cursor:
        commands_rows = await cursor.fetchall()
    # Timers
    import json

    async with db.execute(
        "SELECT id, name, messages_json, interval_minutes, require_chat_activity, enabled FROM timers WHERE channel_id=?",
        (active_channel,),
    ) as cursor:
        timer_rows = await cursor.fetchall()
        timers = [
            {
                "id": row["id"],
                "name": row["name"],
                "messages": json.loads(row["messages_json"]),
                "interval_minutes": row["interval_minutes"],
                "require_chat_activity": bool(row["require_chat_activity"]),
                "enabled": bool(row["enabled"]),
            }
            for row in timer_rows
        ]
    # Filters
    async with db.execute(
        "SELECT id, type, pattern, enabled FROM filters WHERE channel_id=?", (active_channel,)
    ) as cursor:
        filters = await cursor.fetchall()
    # Link settings
    async with db.execute(
        "SELECT enabled, allow_mod, allow_sub, allow_regular, allowed_domains_json FROM link_settings WHERE channel_id=?",
        (active_channel,),
    ) as cursor:
        link_row = await cursor.fetchone()
    if link_row:
        link_settings = {
            "enabled": bool(link_row["enabled"]),
            "allow_mod": bool(link_row["allow_mod"]),
            "allow_sub": bool(link_row["allow_sub"]),
            "allow_regular": bool(link_row["allow_regular"]),
            "allowed_domains": json.loads(link_row["allowed_domains_json"] or "[]"),
        }
    else:
        link_settings = {
            "enabled": True,
            "allow_mod": True,
            "allow_sub": True,
            "allow_regular": True,
            "allowed_domains": [],
        }
    # Giveaway
    async with db.execute(
        "SELECT is_active, keyword, entries_json FROM giveaways WHERE channel_id=?", (active_channel,)
    ) as cursor:
        giveaway_row = await cursor.fetchone()
    giveaway = None
    if giveaway_row:
        giveaway = {
            "is_active": bool(giveaway_row["is_active"]),
            "keyword": giveaway_row["keyword"],
            "entries": json.loads(giveaway_row["entries_json"] or "[]"),
        }
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "channels": channels,
            "channel": active_channel,
            "commands": commands_rows,
            "timers": timers,
            "filters": filters,
            "links": link_settings,
            "giveaway": giveaway,
            "notice": notice,
        },
    )


@app.get("/api/commands/{channel}", dependencies=[Depends(verify_token)])
async def get_commands(channel: str):
    channel = channel.lower()
    db = await database.get_db()
    async with db.execute(
        "SELECT name, response, permission, cooldown_global, cooldown_user FROM commands WHERE channel_id=?",
        (channel,),
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


@app.post("/api/commands/{channel}", dependencies=[Depends(verify_token)])
class CommandIn(BaseModel):
    name: str
    response: str
    permission: str = "everyone"
    cooldown_global: int = 0
    cooldown_user: int = 0


class TimerIn(BaseModel):
    name: str
    messages: List[str]
    interval_minutes: int = 5
    require_chat_activity: bool = False
    enabled: bool = True


class FilterIn(BaseModel):
    type: str
    pattern: str
    enabled: bool = True


class LinkSettingsIn(BaseModel):
    enabled: bool = True
    allow_mod: bool = True
    allow_sub: bool = True
    allow_regular: bool = True
    allowed_domains: List[str] = []


@app.get("/api/commands/{channel}", dependencies=[Depends(verify_token)])
async def get_commands(channel: str):
    db = await database.get_db()
    async with db.execute(
        "SELECT name, response, permission, cooldown_global, cooldown_user FROM commands WHERE channel_id=?",
        (channel,),
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


@app.post("/api/commands/{channel}", dependencies=[Depends(verify_token)])
async def create_command(channel: str, payload: CommandIn):
    channel = channel.lower()
    from jishbot.app.services import commands_service

    await commands_service.add_or_update_command(
        channel, payload.name, payload.response, payload.permission, payload.cooldown_global, payload.cooldown_user
    )
    return {"ok": True}


@app.delete("/api/commands/{channel}/{name}", dependencies=[Depends(verify_token)])
async def delete_command(channel: str, name: str):
    channel = channel.lower()
    from jishbot.app.services import commands_service

    await commands_service.delete_command(channel, name)
    return {"ok": True}


@app.get("/api/timers/{channel}", dependencies=[Depends(verify_token)])
async def get_timers(channel: str):
    channel = channel.lower()
    db = await database.get_db()
    import json

    async with db.execute(
        "SELECT id, name, messages_json, interval_minutes, require_chat_activity, enabled FROM timers WHERE channel_id=?",
        (channel,),
    ) as cursor:
        rows = await cursor.fetchall()
        output = []
        for row in rows:
            output.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "messages": json.loads(row["messages_json"]),
                    "interval_minutes": row["interval_minutes"],
                    "require_chat_activity": bool(row["require_chat_activity"]),
                    "enabled": bool(row["enabled"]),
                }
            )
        return output


@app.post("/api/timers/{channel}", dependencies=[Depends(verify_token)])
async def create_timer(channel: str, payload: TimerIn):
    channel = channel.lower()
    db = await database.get_db()
    import json

    await db.execute(
        """
        INSERT INTO timers(channel_id, name, messages_json, interval_minutes, require_chat_activity, enabled)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(channel_id, name) DO UPDATE SET messages_json=excluded.messages_json,
            interval_minutes=excluded.interval_minutes,
            require_chat_activity=excluded.require_chat_activity,
            enabled=excluded.enabled
        """,
        (
            channel,
            payload.name,
            json.dumps(payload.messages),
            payload.interval_minutes,
            1 if payload.require_chat_activity else 0,
            1 if payload.enabled else 0,
        ),
    )
    await db.commit()
    return {"ok": True}


@app.delete("/api/timers/{channel}/{name}", dependencies=[Depends(verify_token)])
async def delete_timer(channel: str, name: str):
    channel = channel.lower()
    db = await database.get_db()
    await db.execute("DELETE FROM timers WHERE channel_id=? AND name=?", (channel, name))
    await db.commit()
    return {"ok": True}


@app.get("/api/filters/{channel}", dependencies=[Depends(verify_token)])
async def get_filters(channel: str):
    channel = channel.lower()
    db = await database.get_db()
    async with db.execute("SELECT id, type, pattern, enabled FROM filters WHERE channel_id=?", (channel,)) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


@app.post("/api/filters/{channel}", dependencies=[Depends(verify_token)])
async def create_filter(channel: str, payload: FilterIn):
    channel = channel.lower()
    db = await database.get_db()
    await db.execute(
        """
        INSERT INTO filters(channel_id, type, pattern, enabled)
        VALUES(?,?,?,?)
        """,
        (channel, payload.type, payload.pattern, 1 if payload.enabled else 0),
    )
    await db.commit()
    return {"ok": True}


@app.delete("/api/filters/{channel}/{filter_id}", dependencies=[Depends(verify_token)])
async def delete_filter(channel: str, filter_id: int):
    channel = channel.lower()
    db = await database.get_db()
    await db.execute("DELETE FROM filters WHERE channel_id=? AND id=?", (channel, filter_id))
    await db.commit()
    return {"ok": True}


@app.get("/api/links/{channel}", dependencies=[Depends(verify_token)])
async def get_links(channel: str):
    channel = channel.lower()
    db = await database.get_db()
    import json

    async with db.execute(
        "SELECT enabled, allow_mod, allow_sub, allow_regular, allowed_domains_json FROM link_settings WHERE channel_id=?",
        (channel,),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return {
            "enabled": True,
            "allow_mod": True,
            "allow_sub": True,
            "allow_regular": True,
            "allowed_domains": [],
        }
        return {
            "enabled": bool(row["enabled"]),
            "allow_mod": bool(row["allow_mod"]),
            "allow_sub": bool(row["allow_sub"]),
            "allow_regular": bool(row["allow_regular"]),
            "allowed_domains": json.loads(row["allowed_domains_json"] or "[]"),
        }


@app.post("/api/links/{channel}", dependencies=[Depends(verify_token)])
async def set_links(channel: str, payload: LinkSettingsIn):
    channel = channel.lower()
    db = await database.get_db()
    import json

    await db.execute(
        """
        INSERT INTO link_settings(channel_id, enabled, allow_mod, allow_sub, allow_regular, allowed_domains_json)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(channel_id) DO UPDATE SET
            enabled=excluded.enabled,
            allow_mod=excluded.allow_mod,
            allow_sub=excluded.allow_sub,
            allow_regular=excluded.allow_regular,
            allowed_domains_json=excluded.allowed_domains_json
        """,
        (
            channel,
            1 if payload.enabled else 0,
            1 if payload.allow_mod else 0,
            1 if payload.allow_sub else 0,
            1 if payload.allow_regular else 0,
            json.dumps(payload.allowed_domains),
        ),
    )
    await db.commit()
    return {"ok": True}


@app.get("/api/giveaways/{channel}", dependencies=[Depends(verify_token)])
async def get_giveaway(channel: str):
    channel = channel.lower()
    return {
        "entries": await giveaways_service.get_entries(channel),
    }


@app.post("/api/giveaways/{channel}/start", dependencies=[Depends(verify_token)])
async def start_giveaway(channel: str, keyword: str):
    channel = channel.lower()
    await giveaways_service.start_giveaway(channel, keyword)
    return {"ok": True}


@app.post("/api/giveaways/{channel}/end", dependencies=[Depends(verify_token)])
async def end_giveaway(channel: str):
    channel = channel.lower()
    await giveaways_service.end_giveaway(channel)
    return {"ok": True}


# ----- HTML form handlers -----


def redirect_to_dashboard(channel: str, notice: Optional[str] = None) -> RedirectResponse:
    url = f"/dashboard?channel={quote_plus(channel)}"
    if notice:
        url += f"&notice={quote_plus(notice)}"
    return RedirectResponse(url, status_code=303)


@app.post("/dashboard/commands/{channel}/save")
async def dashboard_save_command(
    request: Request,
    channel: str,
    name: str = Form(...),
    response: str = Form(...),
    permission: str = Form("everyone"),
    cooldown_global: int = Form(0),
    cooldown_user: int = Form(0),
):
    if not is_authed(request):
        return auth_redirect()
    channel = channel.lower()
    from jishbot.app.services import commands_service

    await commands_service.add_or_update_command(channel, name, response, permission, cooldown_global, cooldown_user)
    return redirect_to_dashboard(channel, f"Command !{name} saved")


@app.post("/dashboard/commands/{channel}/{name}/delete")
async def dashboard_delete_command(request: Request, channel: str, name: str):
    if not is_authed(request):
        return auth_redirect()
    channel = channel.lower()
    from jishbot.app.services import commands_service

    await commands_service.delete_command(channel, name)
    return redirect_to_dashboard(channel, f"Command !{name} deleted")


@app.post("/dashboard/timers/{channel}/save")
async def dashboard_save_timer(
    request: Request,
    channel: str,
    name: str = Form(...),
    interval_minutes: int = Form(...),
    messages: str = Form(...),
    require_chat_activity: Optional[str] = Form(None),
    enabled: Optional[str] = Form(None),
):
    if not is_authed(request):
        return auth_redirect()
    channel = channel.lower()
    import json

    db = await database.get_db()
    msgs = [m.strip() for m in messages.splitlines() if m.strip()]
    await db.execute(
        """
        INSERT INTO timers(channel_id, name, messages_json, interval_minutes, require_chat_activity, enabled)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(channel_id, name) DO UPDATE SET messages_json=excluded.messages_json,
            interval_minutes=excluded.interval_minutes,
            require_chat_activity=excluded.require_chat_activity,
            enabled=excluded.enabled
        """,
        (
            channel,
            name,
            json.dumps(msgs),
            interval_minutes,
            1 if require_chat_activity else 0,
            1 if enabled else 0,
        ),
    )
    await db.commit()
    return redirect_to_dashboard(channel, f"Timer {name} saved")


@app.post("/dashboard/timers/{channel}/{name}/delete")
async def dashboard_delete_timer(request: Request, channel: str, name: str):
    if not is_authed(request):
        return auth_redirect()
    channel = channel.lower()
    db = await database.get_db()
    await db.execute("DELETE FROM timers WHERE channel_id=? AND name=?", (channel, name))
    await db.commit()
    return redirect_to_dashboard(channel, f"Timer {name} deleted")


@app.post("/dashboard/filters/{channel}/save")
async def dashboard_save_filter(
    request: Request,
    channel: str,
    type: str = Form(...),
    pattern: str = Form(...),
    enabled: Optional[str] = Form(None),
):
    if not is_authed(request):
        return auth_redirect()
    channel = channel.lower()
    db = await database.get_db()
    await db.execute(
        "INSERT INTO filters(channel_id, type, pattern, enabled) VALUES(?,?,?,?)",
        (channel, type, pattern, 1 if enabled else 0),
    )
    await db.commit()
    return redirect_to_dashboard(channel, "Filter added")


@app.post("/dashboard/filters/{channel}/{filter_id}/delete")
async def dashboard_delete_filter(request: Request, channel: str, filter_id: int):
    if not is_authed(request):
        return auth_redirect()
    channel = channel.lower()
    db = await database.get_db()
    await db.execute("DELETE FROM filters WHERE channel_id=? AND id=?", (channel, filter_id))
    await db.commit()
    return redirect_to_dashboard(channel, "Filter deleted")


@app.post("/dashboard/links/{channel}/save")
async def dashboard_save_links(
    request: Request,
    channel: str,
    enabled: Optional[str] = Form(None),
    allow_mod: Optional[str] = Form(None),
    allow_sub: Optional[str] = Form(None),
    allow_regular: Optional[str] = Form(None),
    allowed_domains: str = Form(""),
):
    if not is_authed(request):
        return auth_redirect()
    channel = channel.lower()
    import json

    domains = [d.strip() for d in allowed_domains.split(",") if d.strip()]
    db = await database.get_db()
    await db.execute(
        """
        INSERT INTO link_settings(channel_id, enabled, allow_mod, allow_sub, allow_regular, allowed_domains_json)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(channel_id) DO UPDATE SET
            enabled=excluded.enabled,
            allow_mod=excluded.allow_mod,
            allow_sub=excluded.allow_sub,
            allow_regular=excluded.allow_regular,
            allowed_domains_json=excluded.allowed_domains_json
        """,
        (
            channel,
            1 if enabled else 0,
            1 if allow_mod else 0,
            1 if allow_sub else 0,
            1 if allow_regular else 0,
            json.dumps(domains),
        ),
    )
    await db.commit()
    return redirect_to_dashboard(channel, "Link settings saved")


@app.post("/dashboard/giveaway/{channel}/start")
async def dashboard_start_giveaway(request: Request, channel: str, keyword: str = Form(...)):
    if not is_authed(request):
        return auth_redirect()
    channel = channel.lower()
    await giveaways_service.start_giveaway(channel, keyword)
    return redirect_to_dashboard(channel, f"Giveaway started with keyword '{keyword}'")


@app.post("/dashboard/giveaway/{channel}/end")
async def dashboard_end_giveaway(request: Request, channel: str):
    if not is_authed(request):
        return auth_redirect()
    channel = channel.lower()
    await giveaways_service.end_giveaway(channel)
    return redirect_to_dashboard(channel, "Giveaway ended")


@app.post("/dashboard/giveaway/{channel}/pick")
async def dashboard_pick_giveaway(request: Request, channel: str):
    if not is_authed(request):
        return auth_redirect()
    channel = channel.lower()
    winner = await giveaways_service.pick_winner(channel)
    msg = f"Winner: {winner[1]}" if winner else "No entries to pick"
    return redirect_to_dashboard(channel, msg)
