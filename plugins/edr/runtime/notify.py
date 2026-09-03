"""Discord transport for unattended runs — stdlib only, no gateway, no MCP.

Posts to one guild text channel and reads replies back from it. The bot token
is a declared dependency (`notify.token_file` / `notify.token_key` in
config.yaml), never a silent reach into another plugin's `.env`.

Every public call is a no-op with a logged reason when notify is not
configured or Discord is unreachable. A broken transport must never abort a
scan; findings then wait on disk for the next interactive `/edr:macos`.

CLI: `edr notify test` · `edr notify send <ts>`
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.resolve()))

import paths  # noqa: E402
from collectors._base import read_json, write_json  # noqa: E402

API = "https://discord.com/api/v10"
MAX_LEN = 1900  # Discord caps at 2000
_bot_id: str | None = None


def _cfg() -> dict[str, Any]:
    return paths.load_config().get("notify") or {}


def user_id() -> str:
    return str(_cfg().get("user_id") or "")


def token() -> str | None:
    cfg = _cfg()
    path = Path(str(cfg.get("token_file") or "")).expanduser()
    key = str(cfg.get("token_key") or "DISCORD_BOT_TOKEN")
    try:
        for line in path.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'") or None
    except OSError:
        return None
    return None


def why_not() -> str | None:
    """Reason notify is off, or None when fully configured."""
    cfg = _cfg()
    if cfg.get("channel", "none") != "discord":
        return "notify.channel is not discord"
    if not cfg.get("channel_id"):
        return "notify.channel_id is empty"
    if not user_id():
        return "notify.user_id is empty"
    if token() is None:
        return f"token not readable at {cfg.get('token_file')}"
    return None


def configured() -> bool:
    return why_not() is None


def log(msg: str) -> None:
    paths.LAUNCHD_LOG.parent.mkdir(parents=True, exist_ok=True)
    with paths.LAUNCHD_LOG.open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} notify: {msg}\n")


def _request(method: str, path: str, body: Any = None) -> Any:
    tok = token()
    if tok is None:
        return None
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={"Authorization": f"Bot {tok}", "Content-Type": "application/json",
                 "User-Agent": "edr-notify (https://github.com/lalec/agent-plugins, 0.2)"},
    )
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                time.sleep(min(float(e.headers.get("Retry-After", "1") or 1), 10))
                continue
            log(f"{method} {path} -> HTTP {e.code}")
            return None
        except (urllib.error.URLError, OSError, ValueError) as e:
            log(f"{method} {path} failed: {e}")
            return None
    return None


def post(text: str) -> str | None:
    """Post one message; returns its id, or None (reason logged)."""
    reason = why_not()
    if reason:
        log(f"skipped post: {reason}")
        return None
    if len(text) > MAX_LEN:
        text = text[: MAX_LEN - 1] + "…"
    resp = _request("POST", f"/channels/{_cfg()['channel_id']}/messages", {"content": text})
    return str(resp["id"]) if isinstance(resp, dict) and "id" in resp else None


def fetch(after_id: str | None) -> list[dict[str, str]]:
    """Messages newer than `after_id`, oldest first. [] when not configured."""
    if not configured():
        return []
    query = "?limit=100" + (f"&after={after_id}" if after_id else "")
    resp = _request("GET", f"/channels/{_cfg()['channel_id']}/messages{query}")
    if not isinstance(resp, list):
        return []
    rows = [{"id": str(m.get("id")), "author_id": str((m.get("author") or {}).get("id")),
             "content": str(m.get("content") or "")} for m in resp if isinstance(m, dict)]
    return sorted(rows, key=lambda r: int(r["id"]))


def bot_id() -> str | None:
    global _bot_id
    if _bot_id is None:
        resp = _request("GET", "/users/@me")
        _bot_id = str(resp["id"]) if isinstance(resp, dict) and "id" in resp else None
    return _bot_id


# --- transport state: last message seen + which posts belong to which batch ---

def state() -> dict[str, Any]:
    data = read_json(paths.NOTIFY_STATE, default={})
    return data if isinstance(data, dict) else {}


def save_state(**fields: Any) -> None:
    st = state()
    st.update(fields)
    write_json(paths.NOTIFY_STATE, st)


def remember_post(message_id: str, batch_ts: str) -> None:
    posts = dict(state().get("posts") or {})
    posts[message_id] = batch_ts
    save_state(posts=posts)


def batch_for(message_id: str) -> str | None:
    """The batch whose post is the newest one older than this message (snowflake order)."""
    posts = state().get("posts") or {}
    older = [int(mid) for mid in posts if int(mid) < int(message_id)]
    return posts[str(max(older))] if older else None


def main(argv: list[str]) -> int:
    paths.ensure()
    cmd = argv[0] if argv else "test"
    if cmd == "test":
        reason = why_not()
        if reason:
            print(json.dumps({"posted": None, "reason": reason}))
            return 0
        mid = post("🧪 edr · notify test")
        print(json.dumps({"posted": mid}))
        return 0 if mid else 1
    if cmd == "send" and len(argv) > 1:
        import alerts
        batch = alerts.load(argv[1])
        if batch is None:
            print(json.dumps({"error": f"no batch {argv[1]}"}))
            return 1
        print(json.dumps({"posted": alerts.post_batch(batch), "reason": why_not()}))
        return 0
    print("usage: edr notify test | send <ts>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
