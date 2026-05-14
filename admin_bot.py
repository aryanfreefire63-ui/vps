import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

from telethon import Button, TelegramClient, events
from telethon.tl.types import (
    MessageEntityBold,
    MessageEntityCustomEmoji,
    MessageEntityItalic,
    MessageEntityTextUrl,
    MessageEntityUrl,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


API_ID = 34403046
API_HASH = "b7efb741538c92732411867242b93a15"
BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("TG_BOT_TOKEN="):
                BOT_TOKEN = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
USER_SESSION = "premium_account"
DEFAULT_CHANNEL = "@dfsdfdsfvxzz"
JSON_URL = "https://draw.ar-lottery01.com/WinGo/WinGo_1M/GetHistoryIssuePage.json"
CONFIG_PATH = Path("admin_config.json")
STATE_PATH = Path("prediction_state.json")
POLL_SECONDS = 15
OWNER_ID = 6127830285


ENTITY_TYPES = {
    "MessageEntityBold": MessageEntityBold,
    "MessageEntityItalic": MessageEntityItalic,
    "MessageEntityCustomEmoji": MessageEntityCustomEmoji,
    "MessageEntityUrl": MessageEntityUrl,
    "MessageEntityTextUrl": MessageEntityTextUrl,
}


DEFAULT_CONFIG = {
    "owner_id": OWNER_ID,
    "channel": DEFAULT_CHANNEL,
    "channels": {},
    "running": False,
    "mode": "big_small",
    "active_theme": "default",
    "themes": {},
    "admins": {},
}


pending_theme = {}
pending_admin = {}
pending_channel = {}


def now_ts() -> int:
    return int(time.time())


def load_json(path: Path, default):
    if not path.exists():
        return json.loads(json.dumps(default))
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_config() -> dict:
    config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
    for key, value in DEFAULT_CONFIG.items():
        config.setdefault(key, json.loads(json.dumps(value)))
    if not config.get("channels"):
        channel = config.get("channel") or DEFAULT_CHANNEL
        config["channels"] = {
            channel: {
                "label": channel,
                "enabled": True,
            }
        }
    if not config.get("channel") and config["channels"]:
        config["channel"] = next(iter(config["channels"]))
    if not config["themes"] and Path("post_template.json").exists():
        exported = load_json(Path("post_template.json"), {})
        text = exported.get("text", "")
        config["themes"]["default"] = {
            "name": "default",
            "text": text,
            "entities": exported.get("entities", []),
            "period_token": detect_period_token(text) or "1211",
            "prediction_token": detect_prediction_token(text, config["mode"]) or "BIG",
        }
        config["active_theme"] = "default"
        save_config(config)
    return config


def save_config(config: dict) -> None:
    save_json(CONFIG_PATH, config)


def load_sent() -> set[str]:
    data = load_json(STATE_PATH, {"sent_issue_numbers": []})
    return set(data.get("sent_issue_numbers", []))


def save_sent(sent: set[str]) -> None:
    save_json(STATE_PATH, {"sent_issue_numbers": sorted(sent)})


def fetch_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def get_items(payload: dict) -> list[dict]:
    if isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("list"), list):
        return payload["data"]["list"]
    return []


def entity_to_dict(entity) -> dict:
    data = {"type": entity.__class__.__name__, "offset": entity.offset, "length": entity.length}
    if isinstance(entity, MessageEntityCustomEmoji):
        data["document_id"] = str(entity.document_id)
    for attr in ("url", "language"):
        if hasattr(entity, attr):
            value = getattr(entity, attr)
            if value:
                data[attr] = value
    return data


def dict_to_entity(raw):
    entity_type = ENTITY_TYPES.get(raw["type"])
    if not entity_type:
        return None
    if entity_type is MessageEntityCustomEmoji:
        return entity_type(offset=raw["offset"], length=raw["length"], document_id=int(raw["document_id"]))
    if entity_type is MessageEntityTextUrl:
        return entity_type(offset=raw["offset"], length=raw["length"], url=raw["url"])
    return entity_type(offset=raw["offset"], length=raw["length"])


def detect_period_token(text: str) -> str | None:
    period_pos = text.upper().find("PERIOD")
    matches = list(re.finditer(r"\b\d{3,8}\b", text))
    if not matches:
        return None
    if period_pos >= 0:
        matches.sort(key=lambda m: abs(m.start() - period_pos))
        return matches[0].group(0)
    return matches[-1].group(0)


def detect_prediction_token(text: str, mode: str) -> str | None:
    if mode == "big_small":
        match = re.search(r"\b(BIG|SMALL)\b", text, re.IGNORECASE)
        return match.group(0) if match else None
    if mode == "red_green":
        match = re.search(r"\b(RED|GREEN|VIOLET)\b", text, re.IGNORECASE)
        return match.group(0) if match else None
    if mode == "number":
        matches = list(re.finditer(r"\b\d\b", text))
        return matches[-1].group(0) if matches else None
    return None


def prediction_for_item(item: dict, mode: str) -> str:
    number = str(item.get("number", "0"))
    if mode == "number":
        return number
    if mode == "red_green":
        color = str(item.get("color") or "").split(",", 1)[0].strip()
        return color.upper() if color else ("RED" if int(number) % 2 == 0 else "GREEN")
    return "SMALL" if int(number) <= 4 else "BIG"


def replace_with_entity_shift(text: str, entities: list[dict], replacements: list[tuple[int, int, str]]):
    replacements = sorted(replacements, key=lambda item: item[0])
    new_text_parts = []
    cursor = 0
    shift_points = []
    for start, old_len, new_value in replacements:
        new_text_parts.append(text[cursor:start])
        new_text_parts.append(new_value)
        cursor = start + old_len
        shift_points.append((start, old_len, len(new_value)))
    new_text_parts.append(text[cursor:])
    new_text = "".join(new_text_parts)

    rebuilt = []
    for raw in entities:
        offset = raw["offset"]
        length = raw["length"]
        for start, old_len, new_len in shift_points:
            old_end = start + old_len
            delta = new_len - old_len
            if offset >= old_end:
                offset += delta
            elif offset < old_end and offset + length > start:
                offset = start
                length = new_len
        updated = dict(raw)
        updated["offset"] = offset
        updated["length"] = length
        rebuilt.append(updated)

    real_entities = [dict_to_entity(raw) for raw in rebuilt]
    return new_text, [entity for entity in real_entities if entity is not None]


def build_post(theme: dict, item: dict, mode: str):
    text = theme["text"]
    period_token = theme["period_token"]
    prediction_token = theme["prediction_token"]
    period = str(item["issueNumber"])[-4:]
    prediction = prediction_for_item(item, mode)

    period_start = text.find(period_token)
    prediction_start = text.find(prediction_token)
    if period_start < 0:
        raise ValueError(f"Theme period token not found: {period_token}")
    if prediction_start < 0:
        raise ValueError(f"Theme prediction token not found: {prediction_token}")

    replacements = [
        (period_start, len(period_token), period),
        (prediction_start, len(prediction_token), prediction),
    ]
    return replace_with_entity_shift(text, theme.get("entities", []), replacements)


def is_admin(config: dict, user_id: int) -> bool:
    if config.get("owner_id") == user_id:
        return True
    admin = config.get("admins", {}).get(str(user_id))
    if not admin:
        return False
    expires_at = admin.get("expires_at")
    if expires_at is None:
        return True
    if int(expires_at) > now_ts():
        return True
    del config["admins"][str(user_id)]
    save_config(config)
    return False


def enabled_channels(config: dict) -> list[str]:
    channels = config.get("channels") or {}
    enabled = [channel for channel, info in channels.items() if info.get("enabled", True)]
    if enabled:
        return enabled
    if config.get("channel"):
        return [config["channel"]]
    return [DEFAULT_CHANNEL]


def channel_lines(config: dict) -> list[str]:
    lines = []
    active = config.get("channel")
    for channel, info in config.get("channels", {}).items():
        marker = "*" if channel == active else "-"
        status = "on" if info.get("enabled", True) else "off"
        lines.append(f"{marker} {channel} [{status}]")
    return lines


def admin_lines(config: dict) -> list[str]:
    lines = [f"Owner: {config.get('owner_id')}"]
    for user_id, admin in config.get("admins", {}).items():
        expires_at = admin.get("expires_at")
        label = "permanent" if expires_at is None else time.strftime("%Y-%m-%d %H:%M", time.localtime(expires_at))
        lines.append(f"{user_id}: {label}")
    return lines


def admin_buttons():
    return [
        [Button.inline("Start", b"start_posting"), Button.inline("Stop", b"stop_posting")],
        [Button.inline("Status", b"status"), Button.inline("Force 5", b"force5")],
        [Button.inline("Mode", b"mode_menu"), Button.inline("Themes", b"themes")],
        [Button.inline("Add Theme", b"add_theme"), Button.inline("Channels", b"channels_menu")],
        [Button.inline("Admins", b"admins_menu")],
    ]


def channel_buttons(config: dict):
    buttons = [[Button.inline("Add Channel", b"add_channel")]]
    for channel in config.get("channels", {}):
        encoded = channel.encode("utf-8")[:40]
        buttons.append([
            Button.inline(f"Use {channel}", b"channel:set:" + encoded),
            Button.inline("Remove", b"channel:remove:" + encoded),
        ])
    buttons.append([Button.inline("Back", b"panel")])
    return buttons


def admin_manage_buttons(config: dict):
    buttons = [[Button.inline("Add Admin", b"add_admin_flow")]]
    for user_id in config.get("admins", {}):
        buttons.append([Button.inline(f"Remove {user_id}", f"admin:remove:{user_id}".encode("utf-8"))])
    buttons.append([Button.inline("Back", b"panel")])
    return buttons


def add_admin_duration_buttons(user_id: int):
    return [
        [Button.inline("24 hours", f"admin:add:{user_id}:24h".encode("utf-8"))],
        [Button.inline("Permanent", f"admin:add:{user_id}:permanent".encode("utf-8"))],
        [Button.inline("Cancel", b"admin:cancel")],
    ]


def mode_buttons():
    return [
        [Button.inline("Number", b"mode:number"), Button.inline("BIG/SMALL", b"mode:big_small")],
        [Button.inline("RED/GREEN", b"mode:red_green")],
        [Button.inline("Back", b"panel")],
    ]


async def send_item(user_client: TelegramClient, config: dict, item: dict) -> list[str]:
    theme = config["themes"][config["active_theme"]]
    text, entities = build_post(theme, item, config["mode"])
    logs = []
    for channel in enabled_channels(config):
        message = await user_client.send_message(channel, text, formatting_entities=entities)
        logs.append(f"{channel}:msg={message.id}")
        await asyncio.sleep(0.5)
    return logs


async def post_latest(user_client: TelegramClient, config: dict, limit: int, force: bool) -> list[str]:
    payload = await asyncio.to_thread(fetch_json, JSON_URL)
    items = get_items(payload)[:limit]
    sent = load_sent()
    logs = []
    for item in reversed(items):
        issue = str(item["issueNumber"])
        if issue in sent and not force:
            continue
        message_logs = await send_item(user_client, config, item)
        sent.add(issue)
        save_sent(sent)
        logs.append(f"{issue[-4:]} -> {prediction_for_item(item, config['mode'])} {' '.join(message_logs)}")
        await asyncio.sleep(1)
    return logs


async def monitor_loop(user_client: TelegramClient):
    while True:
        await asyncio.sleep(POLL_SECONDS)
        config = load_config()
        if not config.get("running"):
            continue
        try:
            logs = await post_latest(user_client, config, limit=10, force=False)
            for line in logs:
                print(f"posted {line}")
        except Exception as exc:
            print(f"{time.strftime('%H:%M:%S')} monitor error: {exc}")


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Set bot token first: $env:TG_BOT_TOKEN='123:ABC'; python admin_bot.py")

    user_client = TelegramClient(USER_SESSION, API_ID, API_HASH)
    bot_client = TelegramClient("admin_panel_bot", API_ID, API_HASH)
    await user_client.start()
    await bot_client.start(bot_token=BOT_TOKEN)

    @bot_client.on(events.NewMessage(pattern=r"^/start$"))
    async def start_handler(event):
        config = load_config()
        if config.get("owner_id") is None:
            config["owner_id"] = event.sender_id
            save_config(config)
            await event.respond("Owner set to this Telegram ID.")
        if not is_admin(config, event.sender_id):
            await event.respond("Access denied.")
            return
        await event.respond("Admin Panel", buttons=admin_buttons())

    @bot_client.on(events.NewMessage(pattern=r"^/status$"))
    async def status_handler(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        await event.respond(
            f"Active channel: {config['channel']}\n"
            f"Enabled channels: {', '.join(enabled_channels(config))}\n"
            f"Running: {config['running']}\n"
            f"Mode: {config['mode']}\n"
            f"Theme: {config['active_theme']}\n"
            f"Themes: {', '.join(config['themes']) or 'none'}"
        )

    @bot_client.on(events.NewMessage(pattern=r"^/startposting$"))
    async def start_posting(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        config["running"] = True
        save_config(config)
        await event.respond("Posting started.")

    @bot_client.on(events.NewMessage(pattern=r"^/stopposting$"))
    async def stop_posting(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        config["running"] = False
        save_config(config)
        await event.respond("Posting stopped.")

    @bot_client.on(events.NewMessage(pattern=r"^/mode (number|big_small|red_green)$"))
    async def mode_handler(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        config["mode"] = event.pattern_match.group(1)
        save_config(config)
        await event.respond(f"Mode set: {config['mode']}")

    @bot_client.on(events.NewMessage(pattern=r"^/channel (.+)$"))
    async def channel_handler(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        channel = event.pattern_match.group(1).strip()
        config["channel"] = channel
        config.setdefault("channels", {})[channel] = {"label": channel, "enabled": True}
        save_config(config)
        await event.respond(f"Channel set: {config['channel']}")

    @bot_client.on(events.NewMessage(pattern=r"^/addchannel (.+)$"))
    async def add_channel_handler(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        channel = event.pattern_match.group(1).strip()
        config.setdefault("channels", {})[channel] = {"label": channel, "enabled": True}
        config["channel"] = channel
        save_config(config)
        await event.respond(f"Channel added and selected: {channel}")

    @bot_client.on(events.NewMessage(pattern=r"^/removechannel (.+)$"))
    async def remove_channel_handler(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        channel = event.pattern_match.group(1).strip()
        config.setdefault("channels", {}).pop(channel, None)
        if config.get("channel") == channel:
            config["channel"] = next(iter(config["channels"]), DEFAULT_CHANNEL)
        save_config(config)
        await event.respond(f"Channel removed: {channel}")

    @bot_client.on(events.NewMessage(pattern=r"^/channels$"))
    async def channels_handler(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        await event.respond("\n".join(channel_lines(config)) or "No channels.", buttons=channel_buttons(config))

    @bot_client.on(events.NewMessage(pattern=r"^/addadmin (\d+) (24h|permanent)$"))
    async def add_admin(event):
        config = load_config()
        if config.get("owner_id") != event.sender_id:
            await event.respond("Only owner can add admins.")
            return
        user_id = event.pattern_match.group(1)
        duration = event.pattern_match.group(2)
        expires_at = None if duration == "permanent" else now_ts() + 24 * 60 * 60
        config["admins"][user_id] = {"expires_at": expires_at}
        save_config(config)
        await event.respond(f"Admin added: {user_id} ({duration})")

    @bot_client.on(events.NewMessage(pattern=r"^/removeadmin (\d+)$"))
    async def remove_admin(event):
        config = load_config()
        if config.get("owner_id") != event.sender_id:
            await event.respond("Only owner can remove admins.")
            return
        user_id = event.pattern_match.group(1)
        config["admins"].pop(user_id, None)
        save_config(config)
        await event.respond(f"Admin removed: {user_id}")

    @bot_client.on(events.NewMessage(pattern=r"^/admins$"))
    async def admins_handler(event):
        config = load_config()
        if config.get("owner_id") != event.sender_id:
            return
        await event.respond("\n".join(admin_lines(config)), buttons=admin_manage_buttons(config))

    @bot_client.on(events.NewMessage(pattern=r"^/addtheme(?:\s+(\S+))?(?:\s+(\S+)\s+(\S+))?$"))
    async def add_theme(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        name = event.pattern_match.group(1) or f"theme{len(config['themes']) + 1}"
        period_token = event.pattern_match.group(2)
        prediction_token = event.pattern_match.group(3)
        pending_theme[event.sender_id] = {
            "name": name,
            "period_token": period_token,
            "prediction_token": prediction_token,
        }
        await event.respond(
            "Forward/send one demo prediction post now.\n"
            "I will detect period and prediction token, then ask for confirmation.\n\n"
            "Manual format also works:\n/addtheme name period_token prediction_token"
        )

    @bot_client.on(events.NewMessage(pattern=r"^/confirmtheme$"))
    async def confirm_theme(event):
        data = pending_theme.get(event.sender_id)
        config = load_config()
        if not data or "theme" not in data:
            await event.respond("No pending theme. Use /addtheme first.")
            return
        theme = data["theme"]
        config["themes"][theme["name"]] = theme
        config["active_theme"] = theme["name"]
        save_config(config)
        pending_theme.pop(event.sender_id, None)
        await event.respond(f"Theme saved and selected: {theme['name']}")

    @bot_client.on(events.NewMessage(pattern=r"^/canceltheme$"))
    async def cancel_theme(event):
        pending_theme.pop(event.sender_id, None)
        await event.respond("Theme add cancelled.")

    @bot_client.on(events.NewMessage(pattern=r"^/themes$"))
    async def themes_handler(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        lines = [f"{'* ' if name == config['active_theme'] else '- '}{name}" for name in config["themes"]]
        await event.respond("\n".join(lines) or "No themes.")

    @bot_client.on(events.NewMessage(pattern=r"^/settheme (\S+)$"))
    async def set_theme(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        name = event.pattern_match.group(1)
        if name not in config["themes"]:
            await event.respond("Theme not found.")
            return
        config["active_theme"] = name
        save_config(config)
        await event.respond(f"Theme selected: {name}")

    @bot_client.on(events.NewMessage(pattern=r"^/removetheme (\S+)$"))
    async def remove_theme(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        name = event.pattern_match.group(1)
        if name == config.get("active_theme"):
            await event.respond("Select another theme before removing active theme.")
            return
        config["themes"].pop(name, None)
        save_config(config)
        await event.respond(f"Theme removed: {name}")

    @bot_client.on(events.NewMessage(pattern=r"^/force5$"))
    async def force5_handler(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            return
        logs = await post_latest(user_client, config, limit=5, force=True)
        await event.respond("Posted:\n" + ("\n".join(logs) or "No items found."))

    @bot_client.on(events.CallbackQuery)
    async def callback_handler(event):
        config = load_config()
        if not is_admin(config, event.sender_id):
            await event.answer("Access denied", alert=True)
            return
        data = event.data.decode("utf-8")
        if data == "panel":
            await event.edit("Admin Panel", buttons=admin_buttons())
        elif data == "start_posting":
            config["running"] = True
            save_config(config)
            await event.edit("Posting started.", buttons=admin_buttons())
        elif data == "stop_posting":
            config["running"] = False
            save_config(config)
            await event.edit("Posting stopped.", buttons=admin_buttons())
        elif data == "status":
            await event.edit(
                f"Active channel: {config['channel']}\n"
                f"Enabled: {', '.join(enabled_channels(config))}\n"
                f"Running: {config['running']}\n"
                f"Mode: {config['mode']}\n"
                f"Theme: {config['active_theme']}",
                buttons=admin_buttons(),
            )
        elif data == "force5":
            logs = await post_latest(user_client, config, limit=5, force=True)
            await event.edit("Posted:\n" + ("\n".join(logs) or "No items found."), buttons=admin_buttons())
        elif data == "mode_menu":
            await event.edit("Choose prediction mode", buttons=mode_buttons())
        elif data.startswith("mode:"):
            config["mode"] = data.split(":", 1)[1]
            save_config(config)
            await event.edit(f"Mode set: {config['mode']}", buttons=admin_buttons())
        elif data == "themes":
            lines = [f"{'* ' if name == config['active_theme'] else '- '}{name}" for name in config["themes"]]
            await event.edit("\n".join(lines) or "No themes.", buttons=admin_buttons())
        elif data == "add_theme":
            pending_theme[event.sender_id] = {"name": f"theme{len(config['themes']) + 1}"}
            await event.respond("Forward/send one demo prediction post now. Then use /confirmtheme after preview.")
            await event.answer()
        elif data == "channels_menu":
            await event.edit("\n".join(channel_lines(config)) or "No channels.", buttons=channel_buttons(config))
        elif data == "add_channel":
            pending_channel[event.sender_id] = True
            await event.respond("Send channel username or ID now, example @yourchannel")
            await event.answer()
        elif data.startswith("channel:set:"):
            channel = event.data[len(b"channel:set:"):].decode("utf-8")
            if channel not in config.get("channels", {}):
                await event.answer("Channel not found", alert=True)
                return
            config["channel"] = channel
            config["channels"][channel]["enabled"] = True
            save_config(config)
            await event.edit(f"Selected channel: {channel}", buttons=channel_buttons(config))
        elif data.startswith("channel:remove:"):
            channel = event.data[len(b"channel:remove:"):].decode("utf-8")
            config.setdefault("channels", {}).pop(channel, None)
            if config.get("channel") == channel:
                config["channel"] = next(iter(config["channels"]), DEFAULT_CHANNEL)
            save_config(config)
            await event.edit(f"Removed channel: {channel}\n\n" + ("\n".join(channel_lines(config)) or "No channels."), buttons=channel_buttons(config))
        elif data == "admins_menu":
            if config.get("owner_id") != event.sender_id:
                await event.answer("Only owner can manage admins", alert=True)
                return
            await event.edit("\n".join(admin_lines(config)), buttons=admin_manage_buttons(config))
        elif data == "add_admin_flow":
            if config.get("owner_id") != event.sender_id:
                await event.answer("Only owner can add admins", alert=True)
                return
            pending_admin[event.sender_id] = {"step": "id"}
            await event.respond("Send admin Telegram numeric ID now.")
            await event.answer()
        elif data.startswith("admin:add:"):
            if config.get("owner_id") != event.sender_id:
                await event.answer("Only owner can add admins", alert=True)
                return
            _, _, user_id, duration = data.split(":", 3)
            expires_at = None if duration == "permanent" else now_ts() + 24 * 60 * 60
            config["admins"][user_id] = {"expires_at": expires_at}
            save_config(config)
            pending_admin.pop(event.sender_id, None)
            await event.edit(f"Admin added: {user_id} ({duration})", buttons=admin_manage_buttons(config))
        elif data.startswith("admin:remove:"):
            if config.get("owner_id") != event.sender_id:
                await event.answer("Only owner can remove admins", alert=True)
                return
            user_id = data.split(":", 2)[2]
            config["admins"].pop(user_id, None)
            save_config(config)
            await event.edit(f"Admin removed: {user_id}", buttons=admin_manage_buttons(config))
        elif data == "admin:cancel":
            pending_admin.pop(event.sender_id, None)
            await event.edit("Admin add cancelled.", buttons=admin_manage_buttons(config))

    @bot_client.on(events.NewMessage)
    async def pending_theme_message(event):
        config = load_config()
        admin_flow = pending_admin.get(event.sender_id)
        if admin_flow and not event.raw_text.startswith("/"):
            if config.get("owner_id") != event.sender_id:
                return
            user_id = event.raw_text.strip()
            if not user_id.isdigit():
                await event.respond("Send numeric Telegram ID only.")
                return
            pending_admin[event.sender_id] = {"step": "duration", "user_id": user_id}
            await event.respond(f"Choose duration for admin {user_id}", buttons=add_admin_duration_buttons(int(user_id)))
            return

        if pending_channel.get(event.sender_id) and not event.raw_text.startswith("/"):
            if not is_admin(config, event.sender_id):
                return
            channel = event.raw_text.strip()
            if not channel:
                await event.respond("Send channel username or ID, example @yourchannel")
                return
            config.setdefault("channels", {})[channel] = {"label": channel, "enabled": True}
            config["channel"] = channel
            save_config(config)
            pending_channel.pop(event.sender_id, None)
            await event.respond(f"Channel added and selected: {channel}", buttons=channel_buttons(config))
            return

        data = pending_theme.get(event.sender_id)
        if not data or event.raw_text.startswith("/"):
            return
        if not is_admin(config, event.sender_id):
            return
        text = event.raw_text or ""
        period_token = data.get("period_token") or detect_period_token(text)
        prediction_token = data.get("prediction_token") or detect_prediction_token(text, config["mode"])
        if not period_token or not prediction_token:
            await event.respond(
                "Could not detect period/prediction token.\n"
                "Use manual command like:\n/addtheme name 1211 BIG"
            )
            return
        theme = {
            "name": data["name"],
            "text": text,
            "entities": [entity_to_dict(entity) for entity in (event.message.entities or [])],
            "period_token": period_token,
            "prediction_token": prediction_token,
        }
        data["theme"] = theme
        pending_theme[event.sender_id] = data
        await event.respond(
            f"Detected theme: {theme['name']}\n"
            f"Period token: {period_token}\n"
            f"Prediction token: {prediction_token}\n"
            f"Current mode: {config['mode']}\n\n"
            "Send /confirmtheme to save, or /canceltheme."
        )

    print("Admin bot running.")
    asyncio.create_task(monitor_loop(user_client))
    await bot_client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
