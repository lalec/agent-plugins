"""Nightly unattended scan — what the launchd job runs, and its run records.

`run` owns the "silence means clean" guarantee: every way a run can die ends
in a posted `scan incomplete` line (when Discord is configured) and a run
record that the next interactive `/edr:macos` surfaces. The launchd plist and
shim live in `launchd_job.py`.

CLI: `edr schedule install | uninstall | status | run`
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.resolve()))

import alerts  # noqa: E402
import launchd_job  # noqa: E402
import ledger  # noqa: E402
import notify  # noqa: E402
import paths  # noqa: E402
import pending  # noqa: E402
from collectors._base import read_json, write_json  # noqa: E402

CLAUDE_TIMEOUT = 3 * 3600
KEEP_RUNS = 14
LIMIT_RE = re.compile(r"hit your (session|weekly|opus|sonnet)?\s*limit|usage limit reached", re.I)
FAIL_SUBTYPES = {"error_max_budget_usd", "error_max_turns", "error_during_execution"}


def cfg() -> dict[str, Any]:
    raw = paths.load_config().get("schedule") or {}
    return {"at": str(raw.get("at") or "22:00"), "model": str(raw.get("model") or "opus"),
            "budget_usd": float(raw.get("budget_usd") or 2),
            "reply_window": pending.secs(str(raw.get("reply_window") or "20m"))}


def run() -> int:
    os.environ["EDR_HEADLESS"] = "1"
    paths.ensure()
    start = time.time()
    conf = cfg()
    notify.log(f"run start (model={conf['model']}, budget={conf['budget_usd']})")
    try:
        pending.drain()  # replies that arrived since last run; root actions stay queued
    except Exception as e:  # never let the drain stop the scan
        notify.log(f"pre-drain failed: {type(e).__name__}: {e}")

    _intel_sync()
    ended, reason, data = _scan(conf)
    batch = alerts.since(start)
    if ended == "ok" and batch is None:
        ended, reason = "incomplete", "no alerts file written"
    findings = len(batch.get("findings") or []) if batch else 0

    posted = False
    if notify.configured():
        if ended != "ok":
            posted = bool(notify.post(f"⚠️ edr · scan incomplete · {reason}"))
        elif findings:
            posted = bool(alerts.post_batch(batch))
            if posted:
                pending.drain(wait=conf["reply_window"])
        elif _heartbeat_due():
            posted = bool(notify.post(f"🟢 edr · {_clean_streak() + 1} nights clean"))

    _append_run({"ts": time.strftime(alerts.TS_FORMAT, time.gmtime(start)), "ended": ended,
                 "reason": reason, "cost_usd": data.get("total_cost_usd"),
                 "turns": data.get("num_turns"), "findings": findings, "posted": posted,
                 "seen": False})
    notify.log(f"run end: {ended} {reason} findings={findings} posted={posted}")
    return 0 if ended == "ok" else 1


def _intel_sync() -> None:
    """Refresh IOC feeds; a failure is logged, never fatal."""
    try:
        proc = subprocess.run([sys.executable, str(paths.RUNTIME_DIR / "intel" / "sync.py")],
                              capture_output=True, text=True, timeout=180)
        notify.log(f"intel-sync rc={proc.returncode}: {(proc.stdout or proc.stderr).strip().splitlines()[-1:]}")
    except (subprocess.TimeoutExpired, OSError) as e:
        notify.log(f"intel-sync failed: {e}")


def _scan(conf: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """(ended, reason, result json) for one headless `claude -p /edr:macos headless`."""
    claude = shutil.which("claude")
    if not claude:
        return "incomplete", "claude not on PATH", {}
    cmd = [claude, "-p", "/edr:macos headless", "--model", conf["model"], "--output-format", "json",
           "--max-budget-usd", str(conf["budget_usd"]), "--permission-mode", "bypassPermissions",
           "--settings", '{"askUserQuestionTimeout":"60s"}']
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT,
                              cwd=str(Path.home()))
    except subprocess.TimeoutExpired:
        return "incomplete", f"timed out after {CLAUDE_TIMEOUT // 3600}h", {}
    except OSError as e:
        return "incomplete", f"could not start claude: {e}", {}
    try:
        data = json.loads(proc.stdout)
        data = data if isinstance(data, dict) else {}
    except ValueError:
        data = {}
    text = str(data.get("result", "")) + proc.stdout[-2000:] + proc.stderr[-2000:]
    if LIMIT_RE.search(text):
        return "limit", "usage limit reached", data
    if data.get("subtype") in FAIL_SUBTYPES:
        return "incomplete", f"{data['subtype']} after {data.get('num_turns')} turns", data
    if proc.returncode != 0 or data.get("is_error"):
        return "incomplete", f"claude exit {proc.returncode}: {proc.stderr.strip()[-200:]}", data
    return "ok", "", data


def status() -> int:
    print(json.dumps({"loaded": launchd_job.loaded(), "plist": str(launchd_job.PLIST),
                      "plist_exists": launchd_job.PLIST.exists(), "at": cfg()["at"],
                      "notify": notify.why_not() or "configured",
                      "queued_root_actions": len(ledger.queued()),
                      "recent_runs": _runs()[-3:]}, indent=2))
    return 0


def _runs() -> list[dict[str, Any]]:
    st = read_json(paths.SCHEDULE_STATE, default={}) or {}
    return list(st.get("runs") or [])


def _append_run(record: dict[str, Any]) -> None:
    write_json(paths.SCHEDULE_STATE, {"runs": (_runs() + [record])[-KEEP_RUNS:]})


def _clean_streak() -> int:
    n = 0
    for r in reversed(_runs()):
        if r.get("ended") != "ok" or r.get("findings"):
            break
        n += 1
    return n


def _heartbeat_due() -> bool:
    hb = (paths.load_config().get("notify") or {}).get("heartbeat", "weekly")
    return hb == "weekly" and date.today().weekday() == 6


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "install":
        return launchd_job.install(cfg()["at"], notify.why_not() or "configured")
    if cmd == "uninstall":
        return launchd_job.uninstall()
    if cmd == "status":
        return status()
    if cmd == "run":
        return run()
    print("usage: edr schedule install | uninstall | status | run")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
