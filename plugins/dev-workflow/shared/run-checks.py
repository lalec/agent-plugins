#!/usr/bin/env python3
"""Batch execution and outcome recording for typed verifications.

Copied **verbatim** into a project at `.claude/skills/<PREFIX>-test/scripts/run-checks.py`
by dev-workflow install — no substitution, so it stays byte-identical across projects.
Fix the plugin, never the copy.

    run-checks.py run    [--timeout 30] [--jobs 4] [--head 400] < manifest.json
    run-checks.py record < results.json

`run` executes resolved commands and reports what happened. `record` writes each
verification's `last:` block and commits it.

`run` executes a chunk concurrently (`--jobs`) with a short per-command `--timeout`, so a
chunk of ten finishes inside the single Bash tool call that invoked it — the caller's own
call times out at 120 s by default, and one hung target run sequentially at 120 s each
used to take every other observation in the chunk down with it. Output stays in manifest
order whatever finished first.

THE INVARIANT THIS FILE EXISTS TO HOLD: **`run` never emits a verdict.** It reports an
exit code, a duration and the head of the output; the caller decides `pass | fail |
blocked`. A verification `pass` means the assertion was *exercised and held*, and a
scripted verdict cannot know that — a check whose condition never arose looks identical
to a clean one in the output, and recording it `pass` discharges the deferral forever.
So there is no status field here to fill in, by construction rather than by instruction.

Both subcommands read JSON on stdin and write text (or `--json`) on stdout: no temp
files, nothing to gitignore, and no question about who owns the path.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ("pass", "fail", "blocked")
NEEDS_REASON = ("fail", "blocked")
COMMIT_MSG = "test: record verification outcomes"
LOCK_TRIES, LOCK_BACKOFF = 5, 0.4

NAME_RE = re.compile(r"^(\s*)- name:\s*(.+?)\s*$")


def find_root() -> Path:
    """Repo root, or the cwd when git is absent — same rule as graph.py."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except OSError:
        pass
    return Path.cwd()


def find_tests(root: Path) -> Path:
    """`custom-tests.yaml` by glob, the same discovery graph.py uses — the `<PREFIX>` is
    in the path and never in this file, which is what keeps the copy byte-identical."""
    hits = sorted(root.glob(".claude/skills/*-test/references/custom-tests.yaml"))
    if not hits:
        die("no .claude/skills/*-test/references/custom-tests.yaml under " + str(root))
    return hits[0]


def die(msg: str, code: int = 2) -> None:
    print(f"run-checks: {msg}", file=sys.stderr)
    raise SystemExit(code)


def read_stdin() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        die("expected JSON on stdin")
    try:
        payload = json.loads(raw)
    except ValueError as e:
        die(f"stdin is not valid JSON: {e}")
    if not isinstance(payload, dict):
        die("stdin must be a JSON object")
    return payload


def clip(text: str, n: int) -> str:
    """Head of the output, whitespace-collapsed. The point of batching is that bodies do
    not land in the transcript; a `--head` big enough to hold one defeats it."""
    flat = " ".join(text.split())
    return flat if len(flat) <= n else flat[:n] + f"… (+{len(flat) - n} chars)"


# ------------------------------------------------------------------------------- run


def run_cmd(cmd: str, timeout: int, head: int) -> dict:
    """One observation. Never a verdict — see the module docstring."""
    started = time.monotonic()
    try:
        p = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        secs = round(time.monotonic() - started, 1)
        # Both streams: a failing command routinely prints partial output on stdout and
        # the reason on stderr, and `stdout or stderr` dropped the reason whenever the
        # partial output was non-empty.
        body = p.stdout or ""
        if p.stderr and p.stderr.strip():
            body = f"{body} [stderr] {p.stderr}" if body.strip() else p.stderr
        return {"exit": p.returncode, "secs": secs, "observed": clip(body, head)}
    except subprocess.TimeoutExpired:
        return {
            "exit": None,
            "secs": round(time.monotonic() - started, 1),
            "observed": f"timed out after {timeout}s",
        }
    except OSError as e:  # cannot even start it — still an observation
        return {"exit": None, "secs": 0.0, "observed": f"could not execute: {e}"}


def cmd_run(payload: dict, argv: list[str]) -> int:
    timeout = int(opt(argv, "--timeout", "30"))
    jobs = max(1, int(opt(argv, "--jobs", "4")))
    head = int(opt(argv, "--head", "400"))
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        die('expected {"entries": [{"name": …, "cmd": …}, …]}')
    for e in entries:
        if not isinstance(e, dict) or not e.get("name") or not e.get("cmd"):
            die(f"every entry needs a name and a cmd: {e!r}")

    # Concurrent, order-preserving: `map` yields results in manifest order regardless of
    # completion order, so the evidence lines line up with the entries the caller sent.
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        observations = list(
            pool.map(lambda e: run_cmd(e["cmd"], timeout, head), entries)
        )
    rows = [
        {"name": e["name"], "cmd": e["cmd"], **obs}
        for e, obs in zip(entries, observations)
    ]

    if "--json" in argv:
        print(json.dumps({"observations": rows}, indent=2))
    else:
        # The evidence-trace line format, minus the verdict the caller supplies:
        # command → observed result. These lines flow into the qa handoff verbatim.
        for r in rows:
            code = "timeout/none" if r["exit"] is None else f"exit {r['exit']}"
            print(f"{r['name']}: $ {r['cmd']} → {code} · {r['secs']}s · {r['observed']}")
    # Exit 0 even when a command failed: a failing check is data, not a script error.
    return 0


# ---------------------------------------------------------------------------- record


def entry_spans(lines: list[str]) -> dict[str, tuple[int, int, str]]:
    """name → (first line, one-past-last, field indent). Entry ends at the next `- name:`
    at the same indent, so a `last:` block belongs to the entry above it."""
    starts = []
    for n, ln in enumerate(lines):
        m = NAME_RE.match(ln)
        if m:
            starts.append((n, len(m.group(1)), m.group(2).strip("'\"")))
    spans: dict[str, tuple[int, int, str]] = {}
    for i, (n, indent, name) in enumerate(starts):
        end = len(lines)
        for n2, indent2, _ in starts[i + 1 :]:
            if indent2 <= indent:
                end = n2
                break
        field_indent = " " * (indent + 2)
        for ln in lines[n + 1 : end]:
            if ln.strip() and not ln.lstrip().startswith("#"):
                field_indent = ln[: len(ln) - len(ln.lstrip())]
                break
        spans[name] = (n, end, field_indent)
    return spans


def quote(text: str) -> str:
    """Single-quoted YAML scalar, the convention `assert` and `reason` already use —
    they routinely contain colons, braces and double quotes, which break the other two
    forms. A newline would break this one, so `record` refuses it upstream."""
    return "'" + text.replace("'", "''") + "'"


def last_block(result: dict, commit: str, indent: str) -> list[str]:
    sub = indent + "  "
    out = [f"{indent}last:", f"{sub}status: {result['status']}"]
    if result.get("reason"):
        out.append(f"{sub}reason: {quote(result['reason'])}")
    # Quoted: roughly one sha7 in 25 is all digits, which YAML reads as an integer (and
    # a leading zero as octal). graph.py's parser strips the quotes either way.
    out.append(f"{sub}commit: '{commit}'")
    out.append(f"{sub}ts: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    return out


def splice(lines: list[str], span: tuple[int, int, str], block: list[str]) -> list[str]:
    """Replace this entry's `last:` block, or insert one after its last field. Surgical
    on purpose: the file is hand-shaped (comments, quoted paragraphs, flow lists), so a
    parse-and-re-emit would reformat every line to change one."""
    start, end, indent = span
    body = lines[start:end]
    depth = len(indent)
    at = next(
        (
            i
            for i, ln in enumerate(body)
            if ln.strip() == "last:" and len(ln) - len(ln.lstrip()) == depth
        ),
        None,
    )
    if at is None:
        stop = len(body)
        while stop > 0 and not body[stop - 1].strip():
            stop -= 1
        return lines[: start + stop] + block + lines[start + stop : end] + lines[end:]
    stop = at + 1
    while stop < len(body):
        ln = body[stop]
        if ln.strip() and len(ln) - len(ln.lstrip()) <= depth:
            break
        stop += 1
    return lines[: start + at] + block + lines[start + stop : end] + lines[end:]


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )


def git_commit(root: Path, path: Path) -> str:
    """Pathspec-scoped, and patient about `index.lock`. Scoped because the tree can hold
    in-flight work that must not ride along in a bookkeeping commit; patient because
    parallel verification children commit concurrently, and exiting on the first lock
    would silently drop that child's record."""
    rel = str(path.relative_to(root))
    for attempt in range(LOCK_TRIES):
        add = git(root, "add", "--", rel)
        if add.returncode == 0:
            done = git(root, "commit", "-m", COMMIT_MSG, "--", rel)
            if done.returncode == 0:
                return "committed"
            if "nothing to commit" in (done.stdout + done.stderr):
                return "unchanged"
            err = done.stdout + done.stderr
        else:
            err = add.stdout + add.stderr
        if "index.lock" not in err:
            return f"NOT COMMITTED — {clip(err, 120)}"
        time.sleep(LOCK_BACKOFF * (attempt + 1))
    return "NOT COMMITTED — index.lock held"


def names_in(text: str) -> list[str]:
    """Post-write check. Prefers the projector's own parser so this file and the graph
    cannot disagree about what an entry is; falls back to a name scan when the graph is
    absent, which is a documented state, never a gate."""
    root = find_root()
    graph = root / ".claude" / "graph" / "graph.py"
    if graph.exists():
        try:
            import importlib.util

            # No __pycache__ in someone's repo as a side effect of a verification run.
            sys.dont_write_bytecode = True
            spec = importlib.util.spec_from_file_location("_graph", graph)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return [t["name"] for t in mod.parse_custom_tests(text)]
        except Exception:
            pass
    else:
        # Documented state, never a gate: say so once, and keep the weaker check.
        if not getattr(names_in, "warned", False):
            print("run-checks: no .claude/graph/graph.py — validation degraded to a "
                  "name scan", file=sys.stderr)
            names_in.warned = True
    return [m.group(2).strip("'\"") for m in map(NAME_RE.match, text.splitlines()) if m]


def cmd_record(payload: dict, argv: list[str]) -> int:
    commit = str(payload.get("commit", "")).strip()
    results = payload.get("results")
    if not re.fullmatch(r"[0-9a-f]{7,40}", commit):
        die('"commit" must be the run\'s pinned sha (7-40 hex chars)')
    if not isinstance(results, list) or not results:
        die('expected {"commit": …, "results": [{"name","status","reason"}, …]}')

    path = find_tests(find_root())
    original = path.read_text()
    spans = entry_spans(original.splitlines())

    # Validate everything before writing anything: a refusal must leave the file alone.
    for r in results:
        if not isinstance(r, dict):
            die(f"result is not an object: {r!r}")
        name, status, reason = r.get("name"), r.get("status"), r.get("reason", "")
        if name not in spans:
            die(f"no verification named {name!r} in {path.name} — nothing written")
        if status not in STATUSES:
            die(f"{name}: status must be one of {', '.join(STATUSES)} — nothing written")
        if status in NEEDS_REASON and not str(reason).strip():
            die(f"{name}: {status} needs a reason — nothing written")
        if "\n" in str(reason):
            die(f"{name}: reason must be one line — nothing written")

    before = names_in(original)
    root, lines, done = find_root(), original.splitlines(), []
    for r in results:
        name = r["name"]
        spans = entry_spans(lines)  # line numbers move as blocks grow or shrink
        block = last_block(r, commit, spans[name][2])
        lines = splice(lines, spans[name], block)
        text = "\n".join(lines) + ("\n" if original.endswith("\n") else "")
        if names_in(text) != before:
            # Nothing is committed until the whole batch is written, so a refusal
            # restores the pre-batch file and the tree is exactly as it was.
            path.write_text(original)
            die(f"{name}: write changed the entry set — batch rolled back, nothing written")
        path.write_text(text)
        done.append((name, r["status"]))

    # One commit per call, not per result: the batch is the unit the caller chose to be
    # willing to lose, and a sweep of ~200 verifications must not leave ~200 bookkeeping
    # commits in the history (observed: 335 of 358 commits in two days were these).
    state = git_commit(root, path)

    if "--json" in argv:
        print(json.dumps({"recorded": [dict(zip(("name", "status"), d)) for d in done], "git": state}, indent=2))
    else:
        for name, status in done:
            print(f"{name}: {status} @ {commit}")
        print(f"{len(done)} recorded · {state}")
    return 1 if state.startswith("NOT COMMITTED") else 0


# ------------------------------------------------------------------------------- cli


def opt(argv: list[str], flag: str, default: str) -> str:
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "run":
        return cmd_run(read_stdin(), rest)
    if cmd == "record":
        return cmd_record(read_stdin(), rest)
    die(f"unknown command {cmd!r} — expected run or record")
    return 2


if __name__ == "__main__":
    os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
    sys.exit(main(sys.argv[1:]))
