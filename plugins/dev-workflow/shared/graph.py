#!/usr/bin/env python3
"""Delivery graph — projects the project's own records into a queryable edge index.

Copied verbatim into a project at `.claude/graph/graph.py` by dev-workflow install.
No <PREFIX> substitution: skill dirs are glob-discovered, so this file is byte-identical
across every project.

The index is DERIVED and DISPOSABLE. git and the five source artifacts stay canonical;
`build` with no args discards edges.jsonl and reprojects from scratch. Every read site
must fall back to its pre-graph behaviour if this script is absent or exits non-zero.

    graph.py build                   reproject the index from scratch (<1s on a 200-entry log)
    graph.py covers <path>...        verifications whose paths intersect these
    graph.py blast <path>... [--ids <roadmap-id>...]
                                     owning skills - covering verifs - deliveries - deferrals -
                                     affine or named roadmap items - gates holding them; the one
                                     pack a task's qa and pm prompts carry inline
    graph.py history <path>          what has been delivered, verified and reverted here
    graph.py roadmap-open [--for <path>...]   open items, path-affine ones marked ~match
    graph.py open-deferrals [--with-fail] [<path>...]   deferred or blocked, not passing since
    graph.py open-gates              every parking no later decision answered, with its
                                     condition and age in days

Add --json to any query for machine-readable output.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1

# A roadmap item is closed only if it says so. Anything else — including vocabulary this
# project has never seen — counts as still open, so it surfaces instead of disappearing.
TERMINAL_STATUS = {
    "done",
    "closed",
    "removed",
    "resolved",
    "cancelled",
    "canceled",
    "shipped",
}

# --------------------------------------------------------------------------- discovery


def run_git(root: Path, *args: str) -> str:
    """Return git stdout, or '' on any failure — git absence is never fatal."""
    try:
        r = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=60
        )
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def find_root() -> Path:
    top = run_git(Path.cwd(), "rev-parse", "--show-toplevel").strip()
    return Path(top) if top else Path.cwd()


def one(root: Path, pattern: str) -> Path | None:
    """First glob match, or None. Used to locate prefix-named skill dirs."""
    return next(iter(sorted(root.glob(pattern))), None)


class Sources:
    def __init__(self, root: Path):
        self.root = root
        self.log = root / "docs" / "project-log.md"
        self.roadmap = root / "docs" / "roadmap.md"
        self.conf = root / ".claude" / "hooks" / "governed-paths.conf"
        self.tests = one(root, ".claude/skills/*-test/references/custom-tests.yaml")
        self.deploy = one(root, ".claude/skills/*-deploy/references/deploy-config.yaml")
        self.out = root / ".claude" / "graph" / "edges.jsonl"


def read(p: Path | None) -> str:
    if p is None or not p.is_file():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ----------------------------------------------------------------------------- parsing

SLUG_RE = re.compile(r"[^a-z0-9]+")
# Tolerant of every shape long-lived logs actually contain: optional HH:MM (pre-dates the
# current format), several hashes joined by `+` or `,`, and non-commit placeholders such as
# `uncommit` or `<uncommitted>`. Dropping those entries would silently lose real history.
ENTRY_RE = re.compile(
    r"^###\s+(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}))?\s*·\s*(.*?)\s*—\s*(.+?)\s*$"
)
SHA_RE = re.compile(r"^[0-9a-f]{6,40}$")
FIELD_RE = re.compile(r"^\*\*([A-Za-z][A-Za-z -]*?):\*\*\s*(.*)$")
# Same shape, but finds every field on a line — each value stops at the next `**Name:**`.
MULTI_FIELD_RE = re.compile(
    r"\*\*([A-Za-z][A-Za-z -]*?):\*\*\s*(.*?)(?=\s*·\s*\*\*[A-Za-z][A-Za-z -]*?:\*\*|$)"
)
TOKEN_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)+$")
BACKTICK_RE = re.compile(r"`([^`]+)`")
# Name/reason boundary in `UAT-deferred:` — a *spaced* dash. Unspaced hyphens are
# inside verification names themselves, so the spaces are load-bearing.
DEFERRAL_REASON_RE = re.compile(r"\s[—–-]\s")
DEPLOYED_RE = re.compile(r"([A-Za-z0-9_-]+)\s*→\s*([A-Za-z0-9_-]+)\s*·\s*(\S+)")
# `**Decisions:**` is ` · `-separated, so each term is parsed on its own rather than by one
# global scan. A global `findall` demanding a kebab value silently dropped 12% of jobzeeker's
# terms and 19% of portrais's — including `hold-continue-until-check-settles=**KEEP** (user)`,
# an answer that left its gate reading `parked` for a fortnight. The name admits `/` because
# `keep/adopt` is a real gate name; the value is whatever precedes the trailing provenance,
# and the provenance is optional (`defer=none`).
DECISION_TERM_RE = re.compile(r"^([A-Za-z0-9_/-]+)\s*=\s*(.+)$")


def decision_terms(value: str) -> list[str]:
    """Split `**Decisions:**` on `·`, but never on one INSIDE the provenance parentheses.

    A parking's condition is free prose — `parked (human-gated — three of four slots · see
    montage)` is a legal thing for a person to write, and splitting it blindly left the term
    reading `parked (human-gated — three of four slots`, which is not the word `parked`. The
    gate then vanished from `open-gates` entirely; worse, that non-parked value ANSWERED the
    gate, so a malformed re-park silently closed an earlier well-formed parking of the same
    name and the row went to zero. A gate that disappears because someone typed a bracket is
    lost work, not a formatting nit.

    Unbalanced parentheses fall back to the naive split: with no reliable depth there is no
    way to tell a condition's `·` from a term separator, and the old behaviour at least keeps
    the later terms addressable."""
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:  # a stray `)` — depth is no longer trustworthy
                return value.split("·")
        if ch == "·" and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if depth != 0:
        return value.split("·")
    out.append("".join(buf))
    return out


# The second authoring shape: the provenance parenthesis is closed early and the condition
# trails outside it — `parked (human-gated) — keep the hold and fix the inversion`. Rejoined
# into the canonical `<word> — <condition>` so `condition_of` reads it like any other. Measured
# across all 284 entries of this project's log: this rejoins exactly one term, the one it was
# written for, so it widens nothing else.
PROVENANCE_THEN_DASH_RE = re.compile(r"^(.*?)\s*\(([^()]*)\)\s+[—–-]\s+(.+)$")


def split_provenance(rest: str) -> tuple[str, str]:
    """`value (by)` → `(value, by)`, taking `by` as the trailing BALANCED parenthetical.

    Scanned rather than matched because a condition may contain its own parentheses —
    `parked (human-gated — hold until the next set (all four slots) lands)`. A regex demanding
    a paren-free provenance did not match those at all, so the whole term became the value and
    the gate stopped reading as parked."""
    s = rest.rstrip()
    if s.endswith(")"):
        depth = 0
        for i in range(len(s) - 1, -1, -1):
            if s[i] == ")":
                depth += 1
            elif s[i] == "(":
                depth -= 1
                if depth == 0:
                    # An opening paren with nothing before it is not provenance, it IS the value.
                    head = s[:i].strip()
                    if head:
                        return head, s[i + 1 : -1].strip()
                    break
    m = PROVENANCE_THEN_DASH_RE.match(s)
    if m and m.group(1).strip():
        return m.group(1).strip(), f"{m.group(2).strip()} — {m.group(3).strip()}"
    return rest.strip(), ""


def decisions(value: str) -> list[tuple[str, str, str]]:
    """`(gate, value, by)` per term. `value` is normalised — markdown stripped, collapsed —
    because the only test anyone runs on it is `== "parked"`, and `**KEEP**` must not read as
    a different word than `KEEP`. `by` is normalised the same way: the log writes a sha as
    `` commit `<sha>` `` and a reader grepping for `commit <sha>` must find it either way."""
    out = []
    for term in decision_terms(value):
        m = DECISION_TERM_RE.match(term.strip())
        if not m:
            continue
        gate, rest = m.group(1), m.group(2)
        val, by = split_provenance(rest)
        val = " ".join(val.replace("*", "").replace("`", "").split())
        by = " ".join(by.replace("`", "").split())
        if val:
            out.append((gate, val, by or "unstated"))
    return out


# A parked gate records what would answer it after the provenance word: `parked
# (human-gated — wait for a set that trips 0.05 on its own)`. That text is the only input a
# reader has for deciding whether a gate waits on a person or on evidence, and it is the same
# question `last.reason` answers for a deferral.
CONDITION_RE = re.compile(r"^.*?\s[—–-]\s(.+)$")


def slug(text: str, limit: int = 60) -> str:
    s = SLUG_RE.sub("-", text.strip().lower()).strip("-")
    if len(s) > limit:  # cut on a word boundary — these ids are read by humans
        s = s[:limit].rsplit("-", 1)[0]
    return s.strip("-") or "untitled"


def parse_fields(lines: list[str]) -> dict[str, str]:
    """`**Name:** value` blocks. A value continues onto following lines until a blank
    line, another field, or a new heading — real entries wrap long values that way."""
    fields: dict[str, str] = {}
    current: str | None = None
    for raw in lines:
        line = raw.rstrip()
        m = FIELD_RE.match(line)
        if m:
            current = m.group(1).strip()
            fields[current] = m.group(2).strip()
        elif current and line.strip() and not line.startswith(("###", "---", "#")):
            fields[current] += " " + line.strip()
        else:
            current = None
    return fields


def strip_fences(text: str) -> str:
    """Blank lines inside ``` fences so a documented format example isn't read as data.

    Roadmaps and delivery logs routinely show their own entry shape inside a fence. Without
    this, `### [category] Title` in a roadmap header becomes a permanent phantom open item
    (seen on a real install), and a fenced `### ` example in a log would be counted as an
    entry the parser then fails to read. Lines are blanked rather than removed so line
    offsets stay valid for callers that index into them.
    """
    out, fenced = [], False
    for ln in text.splitlines():
        if ln.lstrip().startswith("```"):
            fenced = not fenced
            out.append("")
        else:
            out.append("" if fenced else ln)
    return "\n".join(out)


def parse_log(text: str) -> list[dict]:
    """Delivery-log entries, newest first (the file is written top-insertion)."""
    entries: list[dict] = []
    lines = strip_fences(text).splitlines()
    starts = [i for i, ln in enumerate(lines) if ENTRY_RE.match(ln)]
    for n, i in enumerate(starts):
        m = ENTRY_RE.match(lines[i])
        if not m:
            continue
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        date, time, hash_region, title = m.groups()
        shas = [
            h[:7] for h in BACKTICK_RE.findall(hash_region) if SHA_RE.match(h.strip())
        ]
        entries.append(
            {
                "shas": shas,  # 0..n — an entry may predate git or name several commits
                "sha": shas[0] if shas else "",
                "title": title,
                "ts": f"{date}T{time or '00:00'}:00",
                "fields": parse_fields(lines[i + 1 : end]),
            }
        )
    return entries


def roadmap_fields(line: str) -> list[tuple[str, str]]:
    """Every `**Name:** value` on one line, not just the first.

    Roadmaps write metadata one-per-line (`- **Status:** open`) *and* packed onto a
    single line (`**Added:** … · **Owner:** … · **Status:** open · 2026-07-29`). Matching
    only the first field makes `Status` invisible and reports the whole roadmap as open.
    Each value runs until the next `**Name:**`, so values keep their own `·` separators.
    """
    return [
        (m.group(1).strip(), m.group(2).strip())
        for m in MULTI_FIELD_RE.finditer(line[2:] if line.startswith("- ") else line)
    ]


def headless_roadmap_items(text: str) -> list[tuple[str, int]]:
    """Headings that contain more than one `**Category:**` — a headless item is hiding there.

    An item written without its `### ` heading is not a parse error: its fields are quietly
    absorbed by the preceding item (and dropped, since that item already has them), so it
    vanishes from `roadmap-open` and has no id for the log's `**Addresses:**` to cite. Two
    such items sat invisible in a real roadmap for weeks.

    Category is the signal, not Status: an item declares its category exactly once, whereas
    real roadmaps stack several `**Status:**` lines on one item to keep superseded history.
    Measured across four roadmaps, Category flagged both headless items and nothing else;
    Status produced two false positives on exactly that history-keeping pattern.
    """
    lines = strip_fences(text).splitlines()
    idx = [n for n, ln in enumerate(lines) if ln.strip().startswith("### ")]
    out = []
    for k, n in enumerate(idx):
        end = idx[k + 1] if k + 1 < len(idx) else len(lines)
        count = sum(
            1
            for ln in lines[n + 1 : end]
            if re.match(r"^-?\s*\*\*Category:\*\*", ln.strip())
        )
        if count > 1:
            out.append((lines[n].strip()[4:], count))
    return out


def parse_roadmap(text: str) -> list[dict]:
    """`### title` items carrying `- **Field:** value` lines, grouped under `## Section`."""
    items: list[dict] = []
    section = ""
    cur: dict | None = None
    for raw in strip_fences(text).splitlines():
        line = raw.strip()
        if line.startswith("## ") and not line.startswith("### "):
            section = line[3:].strip()
            cur = None
        elif line.startswith("### "):
            cur = {"title": line[4:].strip(), "section": section, "fields": {}}
            items.append(cur)
        elif cur is not None:
            # Metadata is written as a list item (`- **Status:** open`), bare, and packed
            # several-to-a-line — the documented format mandates none of these.
            for k, v in roadmap_fields(line):
                cur["fields"].setdefault(k, v)
    # Statuses the file itself spells with a hyphen. A multi-word status written with a
    # space is the same status — `in progress` is `in-progress` — but joining words
    # unconditionally would turn `blocked on the API` into a status of its own. So the
    # project's own vocabulary decides: a spaced form is joined only when the joined form
    # is one this roadmap already uses hyphenated somewhere. Observed: 2 of 13 in-progress
    # items on a real install were bucketed as a status `in` and vanished from started work.
    vocab = {
        m.group(0)
        for it in items
        if (m := re.match(r"[a-z]+(?:-[a-z]+)+", it["fields"].get("Status", "").strip().lower()))
    }
    for it in items:
        # **Id:** is authoritative once present; fall back to the title slug so this
        # works on installs that predate the field and on items not yet backfilled.
        it["id"] = it["fields"].get("Id") or slug(it["title"])
        # Status values trail free text in several shapes — `done · 2026-07-30`,
        # `closed — superseded by …`, `in-progress · 2026-07-29 (abc1234) — …`. Only the
        # leading token is the status; splitting on one separator misses the others.
        text = it["fields"].get("Status", "open").strip().lower()
        head = re.match(r"[a-z-]+", text)
        raw = head.group(0) if head else "open"
        words = re.match(r"[a-z-]+(?:\s+[a-z-]+){0,2}", text)
        if words:
            parts = words.group(0).split()
            for n in range(len(parts), 1, -1):  # longest match wins
                joined = "-".join(parts[:n])
                if joined in vocab:
                    raw = joined
                    break
        it["status"] = raw
        # Terminal statuses are blacklisted rather than active ones whitelisted: real
        # roadmaps carry `reopened`, `awaiting`, `blocked` and other local vocabulary,
        # and an unrecognised status must stay VISIBLE rather than silently vanish.
        it["open"] = raw.rstrip(".") not in TERMINAL_STATUS
        it["priority"] = it["fields"].get("Priority", "").strip().lower()
    return items


def _scalar(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        inner = v[1:-1]
        return inner.replace("''", "'") if v[0] == "'" else inner
    return v


def _quote_open(v: str) -> bool:
    """True when `v` opens a single-quoted scalar that has not closed yet — a `'` at the
    start and no lone `'` after it (doubled `''` is an escaped quote, not a close)."""
    return v.startswith("'") and "'" not in v[1:].replace("''", "")


def parse_custom_tests(text: str) -> list[dict]:
    """Minimal reader for the fixed, machine-written custom-tests.yaml shape.

    Handles `paths:` as a block list or an inline flow list, the optional `last:` block,
    and a single-quoted scalar that spans lines. Deliberately not a general YAML parser —
    the schema is fixed.

    The multi-line case matters: a hand-shaped `reason:` routinely wraps, and reading only
    its first physical line handed `open-deferrals` a truncated reason — while a wrapped
    line that happened to contain a `:` was parsed as a new key. The continuation lines
    are joined with single spaces until the closing quote arrives.
    """
    tests: list[dict] = []
    cur: dict | None = None
    key: str | None = None
    pending: tuple[dict, str, list[str]] | None = None  # (target, key, pieces) of an open '…'
    for raw in text.splitlines():
        if pending is not None:
            target, k, pieces = pending
            pieces.append(raw.strip())
            joined = " ".join(p for p in pieces if p)
            if not _quote_open(joined):
                target[k] = _scalar(joined)
                pending = None
            continue
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())
        if stripped.startswith("- name:"):
            cur = {"name": _scalar(stripped[7:]), "paths": [], "last": {}}
            tests.append(cur)
            key = None
            continue
        if cur is None:
            continue
        if stripped.startswith("- ") and key == "paths":
            cur["paths"].append(_scalar(stripped[2:]))
            continue
        if ":" not in stripped:
            continue
        k, _, v = stripped.partition(":")
        k, v = k.strip(), v.strip()
        if k == "paths":
            key = "paths"
            if v.startswith("["):
                cur["paths"] = [
                    _scalar(p) for p in v.strip("[]").split(",") if p.strip()
                ]
            continue
        if k == "last":
            key = "last"
            continue
        target = cur["last"] if key == "last" and indent >= 6 else cur
        if target is cur:
            key = None
        if _quote_open(v):
            pending = (target, k, [v])
        else:
            target[k] = _scalar(v)
    return tests


def strip_comment(line: str) -> str:
    """Drop a trailing `#` comment, ignoring `#` inside quotes (deploy commands have them)."""
    out, quote = [], ""
    for ch in line:
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "#":
            break
        out.append(ch)
    return "".join(out).rstrip()


def parse_deploy_config(text: str) -> list[tuple[str, str, dict]]:
    """-> [(component, env, {url, kind}), ...] from the components:/envs: nesting."""
    envs: list[tuple[str, str, dict]] = []
    comp = env = None
    in_components = False
    for raw in text.splitlines():
        line = strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        s = line.strip()
        if indent == 0:
            in_components = s.startswith("components:")
            comp = env = None
            continue
        if not in_components or ":" not in s:
            continue
        k, _, v = s.partition(":")
        k, v = k.strip(), v.strip()
        if indent == 2 and not v:
            comp, env = k, None
        elif indent == 6 and not v and comp:
            env = k
            envs.append((comp, env, {}))
        elif indent >= 8 and env and envs:
            if k in ("url", "run", "deploy", "trigger", "gate"):
                envs[-1][2][k] = _scalar(v)
    for _, _, props in envs:
        props["kind"] = (
            "serve" if "run" in props else "ship" if "deploy" in props else "?"
        )
    return envs


def parse_path_map(text: str) -> list[tuple[str, str]]:
    """PATH_MAP=( 'PATTERN:SKILL' ... ) — ordered, first match wins."""
    m = re.search(r"PATH_MAP=\((.*?)\n\)", text, re.S)
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        e = line.strip().strip("'\"")
        if not e or e.startswith("#") or ":" not in e:
            continue
        out.append((e[: e.rfind(":")], e[e.rfind(":") + 1 :]))
    return out


def git_touches(root: Path, shas: set[str]) -> dict[str, list[str]]:
    """One `git log --name-only` pass over the whole history, filtered to the delivery
    commits. One subprocess call regardless of history size — never one per commit."""
    raw = run_git(
        root, "log", "--no-merges", "--format=%x00%h", "--name-only", "--no-renames"
    )
    touches: dict[str, list[str]] = {}
    for block in raw.split("\0"):
        if not block.strip():
            continue
        lines = block.splitlines()
        sha = lines[0].strip()[:7]
        if sha in shas:
            touches[sha] = [ln.strip() for ln in lines[1:] if ln.strip()]
    return touches


def git_reverts(root: Path) -> list[tuple[str, str]]:
    raw = run_git(root, "log", "--format=%x00%h%x1f%B", "--grep=^Revert")
    out = []
    for block in raw.split("\0"):
        if "\x1f" not in block:
            continue
        sha, _, body = block.partition("\x1f")
        m = re.search(r"This reverts commit ([0-9a-f]{7,40})", body)
        if m:
            out.append((sha.strip()[:7], m.group(1)[:7]))
    return out


# ------------------------------------------------------------------------- projection


def edge(etype: str, frm: str, to: str, src: str, commit: str = "", **props) -> dict:
    e = {"e": etype, "from": frm, "to": to, "src": src}
    if commit:
        e["commit"] = commit
    if props:
        e["props"] = {k: v for k, v in props.items() if v not in ("", None)}
    return e


def tokens(value: str) -> list[str]:
    """Kebab tokens from a `·`-separated or prose field, ignoring italic annotations."""
    return [
        t
        for t in (p.strip().strip("`*_") for p in value.split("·"))
        if TOKEN_RE.match(t)
    ]


def project(src: Sources) -> list[dict]:
    """Full reprojection. There is deliberately no incremental mode: a full build is
    under a second on the largest real corpus, and an append path would leave deleted
    verifications and retired path patterns lingering in the index."""
    edges: list[dict] = []
    entries = parse_log(read(src.log))

    tests = parse_custom_tests(read(src.tests))

    for e in entries:
        sha, f = e["sha"], e["fields"]
        task = f"task:{slug(e['title'])}"
        where = f"project-log.md#{sha or slug(e['title'], 20)}"

        for rid in (r.strip() for r in f.get("Addresses", "").split(",")):
            if rid and TOKEN_RE.match(rid.strip("`")):
                edges.append(
                    edge(
                        "ADDRESSES",
                        task,
                        f"road:{rid.strip('`')}",
                        f"{where}.Addresses",
                        ts=e["ts"],
                    )
                )

        # An entry may name several commits (older multi-hash entries) or none at all
        # (`uncommit`, `<uncommitted>`). Commit-keyed edges only exist when a sha does.
        for s in e["shas"]:
            edges.append(edge("LANDED_AS", task, f"commit:{s}", where))

        # Gates are keyed by the gate, never by the commit — `dec:{sha}/{gate}` gave every
        # entry its own unrelated node, so two entries deciding one gate could not be
        # ordered and "the latest decision wins" was not expressible. That also puts this
        # above the no-sha guard: the edge only *sources* from a commit now, and a gate is
        # most often parked by a read-only dry run, which is exactly an entry with no sha.
        #
        # `from` is the **task**, never the commit, so a gate joins to the roadmap items its
        # entry addresses — `ADDRESSES` is task-keyed, and a mixed key silently returned
        # nothing for every gate whose entry had a sha. The sha rides along as `commit`.
        for gate, value, by in decisions(f.get("Decisions", "")):
            edges.append(
                edge(
                    "DECIDED",
                    task,
                    f"gate:{gate}",
                    f"{where}.Decisions",
                    commit=sha,
                    value=value,
                    by=by.strip(),
                    ts=e["ts"],
                )
            )

        if not sha:
            continue

        for s in tokens(f.get("Skills", "")):
            edges.append(edge("USED", f"commit:{sha}", f"skill:{s}", f"{where}.Skills"))

        for comp, env, url in DEPLOYED_RE.findall(f.get("Deployed", "")):
            edges.append(
                edge(
                    "DEPLOYED_TO",
                    f"commit:{sha}",
                    f"env:{comp}/{env}",
                    f"{where}.Deployed",
                    url=url,
                )
            )

        decided_by = dict(
            (gate, by.strip()) for gate, _v, by in decisions(f.get("Decisions", ""))
        )

        deferred = f.get("UAT-deferred", "")
        if deferred and not deferred.lower().startswith("none"):
            # `**Decisions:** defer=…` is the structured record and wins. The prose scan is
            # only a fallback for entries written before that field existed.
            accepted = decided_by.get("defer") or (
                "timeout"
                if "timeout" in deferred.lower()
                else "user"
                if "user-confirmed" in deferred.lower()
                else "unstated"
            )
            # `UAT-deferred:` is `<names> — <reason>`, optionally repeated with `·`.
            # Reasons routinely quote their own tokens (a repo, a branch, a command), and
            # `TOKEN_RE` accepts any kebab word — so scanning the whole line minted a
            # phantom verification from `agent-plugins` inside a trigger description, which
            # then read as a real open deferral forever. The name/reason boundary is the
            # spaced dash, so only scan ahead of it. Membership in `custom-tests.yaml` is
            # NOT a usable guard here: a deferral may legitimately name work that was never
            # captured as a typed verification, and those are exactly the ones that must
            # not be lost.
            # The tail after that boundary is the reason the check could not run — the
            # only place a log-route deferral records *why*. Dropping it (as this did)
            # left `open-deferrals` unable to classify the log-sourced half of a backlog:
            # 42 of 62 rows on one install carried no reason at all, so the
            # structural-vs-closable split could not see them.
            for chunk in deferred.split("·"):
                parts = DEFERRAL_REASON_RE.split(chunk, maxsplit=1)
                head = parts[0]
                why = parts[1].strip() if len(parts) > 1 else ""
                for name in BACKTICK_RE.findall(head):
                    if TOKEN_RE.match(name.strip()):
                        edges.append(
                            edge(
                                "DEFERRED",
                                f"commit:{sha}",
                                f"verif:{name.strip()}",
                                f"{where}.UAT-deferred",
                                accepted_by=accepted,
                                reason=why,
                            )
                        )


    shas = {s for e in entries for s in e["shas"]}
    for sha, paths in git_touches(src.root, shas).items():
        for p in paths:
            edges.append(
                edge("TOUCHES", f"commit:{sha}", f"path:{p}", "git log --name-only")
            )

    for newer, older in git_reverts(src.root):
        edges.append(
            edge(
                "SUPERSEDES",
                f"commit:{newer}",
                f"commit:{older}",
                "git log --grep=^Revert",
            )
        )

    for t in tests:
        name = t.get("name", "")
        if not name:
            continue
        for p in t.get("paths", []):
            edges.append(
                edge(
                    "COVERS",
                    f"verif:{name}",
                    f"path:{p}",
                    f"custom-tests.yaml#{name}.paths",
                )
            )
        last = t.get("last") or {}
        if last.get("status") and last.get("commit"):
            edges.append(
                edge(
                    "VERIFIED",
                    f"commit:{last['commit'][:7]}",
                    f"verif:{name}",
                    f"custom-tests.yaml#{name}.last",
                    status=last["status"],
                    ts=last.get("ts", ""),
                    # `reason` is written only alongside `status: blocked`. It is projected
                    # because a bare `blocked` in the open-work query says nothing about
                    # whether the block is transient or structural — the reason names the
                    # trigger that would close it, which is what makes the row actionable.
                    reason=last.get("reason", ""),
                )
            )

    for pattern, owner in parse_path_map(read(src.conf)):
        edges.append(
            edge("OWNED_BY", f"path:{pattern}", f"skill:{owner}", "governed-paths.conf")
        )

    for comp, env, props in parse_deploy_config(read(src.deploy)):
        edges.append(
            edge(
                "HAS_ENV",
                f"comp:{comp}",
                f"env:{comp}/{env}",
                "deploy-config.yaml",
                url=props.get("url", ""),
                kind=props.get("kind", ""),
            )
        )

    return edges


# ------------------------------------------------------------------------------- store


def head_sha(root: Path) -> str:
    return run_git(root, "rev-parse", "--short", "HEAD").strip()


def write_index(src: Sources, edges: list[dict]) -> None:
    src.out.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "_meta": {
            "version": VERSION,
            "head": head_sha(src.root),
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "edges": len(edges),
        }
    }
    with src.out.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(meta, sort_keys=True) + "\n")
        for e in edges:
            fh.write(json.dumps(e, sort_keys=True) + "\n")


def load(src: Sources) -> list[dict]:
    """Read the index, rebuilding first when it is missing or behind HEAD."""
    edges, meta = [], {}
    if src.out.is_file():
        for line in read(src.out).splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "_meta" in obj:
                meta = obj["_meta"]
            else:
                edges.append(obj)
    stale = (
        not edges
        or meta.get("version") != VERSION
        or meta.get("head") != head_sha(src.root)
    )
    if stale:
        edges = project(src)
        write_index(src, edges)
    return edges


# ----------------------------------------------------------------------------- queries


def path_hits(pattern: str, changed: list[str]) -> bool:
    """A stored path matches a changed path by equality, glob, or directory prefix."""
    for c in changed:
        if pattern == c or fnmatch.fnmatch(c, pattern) or fnmatch.fnmatch(pattern, c):
            return True
        if c.startswith(pattern.rstrip("/") + "/") or pattern.startswith(
            c.rstrip("/") + "/"
        ):
            return True
    return False


def node_id(node: str) -> str:
    """Strip the `<type>:` prefix. Never hand-count prefix lengths — `comp:`, `verif:`
    and `commit:` differ by one character each and the slices silently mis-cut."""
    return node.partition(":")[2]


def by_kind(edges: list[dict], kind: str) -> list[dict]:
    return [e for e in edges if e["e"] == kind]


def covering(edges: list[dict], changed: list[str]) -> list[str]:
    return sorted(
        {
            node_id(e["from"])
            for e in by_kind(edges, "COVERS")
            if path_hits(node_id(e["to"]), changed)
        }
    )


def last_status(edges: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in by_kind(edges, "VERIFIED"):
        p = e.get("props", {})
        name = node_id(e["to"])
        if p.get("ts", "") >= out.get(name, {}).get("ts", ""):
            out[name] = {
                "status": p.get("status", "?"),
                "ts": p.get("ts", ""),
                "commit": node_id(e["from"]),
            }
            if p.get("reason"):
                out[name]["reason"] = p["reason"]
    return out


def open_gates(edges: list[dict]) -> list[dict]:
    """Every parking of a gate that no later decision has answered.

    The closing rule is unchanged — a later entry deciding the same gate closes it, with no
    separate closing action — but it is applied *per parking* rather than by keeping one
    newest edge per name. Keeping only the newest hid real work: portrais parks `keep/adopt`
    on every `/tune` run, and four unanswered parkings collapsed into one node while three
    disappeared. A name is closed by a **newer non-parked** decision on that name, so an
    unanswered parking survives however many times the name repeats.

    The rule has one hard dependency the projector cannot enforce: **the entry that answers
    a gate must repeat its name verbatim.** A renamed gate is a new node, so the old one
    stays parked forever and this query over-reports — the direction that matters, because a
    stale `parked` reads as outstanding work. `<PREFIX>-log`'s field guidance carries that
    rule; without it a closed gate and a drifted name are indistinguishable from here.

    `condition` is what would answer the parking, taken from the text after the provenance
    word (`parked (human-gated — <condition>)`). It is what separates a gate waiting on a
    person from one waiting on evidence that has not arrived, and it is the same question
    `last.reason` answers for a deferral — so one reader can consume both stores. Empty when
    the entry did not record one; the reader falls back to the entry prose.

    `releases` is the join that makes a gate rankable: the roadmap items its own entry
    addressed. A gate holding the blocked half of started work is the cheapest way back
    into that work, and without this the report can only call it a chore."""
    addressed: dict[str, list[str]] = {}
    for a in by_kind(edges, "ADDRESSES"):
        addressed.setdefault(a["from"], []).append(node_id(a["to"]))

    decided = by_kind(edges, "DECIDED")
    answered: dict[str, str] = {}  # gate -> newest ts carrying a non-parked value
    settled: set[tuple[str, str]] = set()  # (task, gate) answered by that entry itself
    for d in decided:
        p = d.get("props", {})
        if p.get("value") != "parked":
            gate = node_id(d["to"])
            settled.add((d["from"], gate))
            if p.get("ts", "") > answered.get(gate, ""):
                answered[gate] = p.get("ts", "")

    today = datetime.now(timezone.utc).date()
    out = []
    for d in decided:
        p = d.get("props", {})
        gate = node_id(d["to"])
        ts = p.get("ts", "")
        if p.get("value") != "parked":
            continue
        # Strictly older than the answer, or answered by this very entry. A *tie* keeps the
        # parking open: entries written before the format carried `HH:MM` all collapse to
        # 00:00, so same-day ordering is not knowable, and a gate re-parked the day it was
        # answered is real work that must not vanish into a timestamp collision.
        if ts < answered.get(gate, "") or (d["from"], gate) in settled:
            continue
        out.append(
            {
                "gate": gate,
                "value": "parked",
                "by": p.get("by", "unstated"),
                "condition": condition_of(p.get("by", "")),
                "ts": ts,
                "age_days": days_since(ts, today),
                "at": d.get("commit") or node_id(d["from"]),
                "releases": addressed.get(d["from"], []),
                "src": d["src"],
            }
        )
    return sorted(out, key=lambda g: (g["ts"], g["gate"]))


def condition_of(by: str) -> str:
    """What would answer this parking, from `human-gated — <condition>`. Empty when the
    entry recorded only the provenance word."""
    m = CONDITION_RE.match(by.strip())
    return m.group(1).strip() if m else ""


def days_since(ts: str, today) -> int | str:
    """Whole days between an entry timestamp and today. `?` rather than a wrong number when
    the entry's date cannot be read — a fabricated age is worse than a visible gap."""
    try:
        return (today - datetime.strptime(ts[:10], "%Y-%m-%d").date()).days
    except (ValueError, TypeError):
        return "?"


def gate_line(g: dict) -> str:
    rel = f" · releases {', '.join(g['releases'])}" if g.get("releases") else ""
    cond = f" · awaits {g['condition']}" if g.get("condition") else ""
    return (
        f"{g['gate']} — parked {g['ts'][:10]} ({g['age_days']}d) · "
        f"{g['at']} ({g['by']}){cond}{rel}"
    )


def open_verifications(
    edges: list[dict], changed: list[str] | None, with_fail: bool = False
) -> list[dict]:
    """Unproven, with nothing watching: formally deferred in the delivery log, or recorded
    `blocked` by the last run that touched it. Two ways in, one row out.

    `blocked` belongs here because the vacuous-pass rule makes it the honest outcome when
    an assertion never got exercised, and only some of those are also written up as a log
    deferral — the rest were invisible to every standing query. Both states close the same
    way: a later `pass` and nothing else, which is why chronology is `last_status` (newest
    VERIFIED edge wins) for both. A **never-run** verification is deliberately not open
    work — it has no recorded outcome to act on, and surfacing every one would bury the
    entries that do.

    A recorded `fail` is excluded by default and admitted by `with_fail`. It is not a
    deferral — something ran and did not hold — and the close-out puts it in Open, where
    the next run's Step 0 has no reason to re-raise it. But an Open row dies with its
    session, so the one caller that runs in a *fresh* session and asks what is outstanding
    would otherwise never see it. That caller passes the flag; the lanes that open a task
    do not."""
    stat = last_status(edges)
    rows: dict[str, dict] = {}

    def row(name: str) -> dict | None:
        if stat.get(name, {}).get("status") == "pass":
            return None
        if changed and not path_hits_verif(edges, name, changed):
            return None
        return rows.setdefault(name, {"verification": name})

    for e in by_kind(edges, "DEFERRED"):
        r = row(node_id(e["to"]))
        if r is not None and "deferred_at" not in r:
            r["deferred_at"] = node_id(e["from"])
            r["accepted_by"] = e.get("props", {}).get("accepted_by", "unstated")
            # Entries written before reasons were required have none. Leave the key
            # absent rather than inventing one — a caller counts these as unclassified.
            if e.get("props", {}).get("reason"):
                r.setdefault("reason", e["props"]["reason"])
            r["src"] = e["src"]
    for name, v in stat.items():
        if v["status"] not in ("blocked", "fail"):
            continue
        if v["status"] == "fail" and not with_fail:
            continue
        r = row(name)
        if r is not None:
            r["failed_at" if v["status"] == "fail" else "blocked_at"] = v["commit"]
            # Don't clobber a reason the log route already supplied: a `blocked` row
            # recorded before reasons were required has none, and the deferral's is then
            # the only explanation there is.
            if v.get("reason") or not r.get("reason"):
                r["reason"] = v.get("reason", "")
            r.setdefault("src", f"custom-tests.yaml#{name}.last")
    return list(rows.values())


def clip(text: str, n: int = 160) -> str:
    """One line's worth. The full reason stays in --json and in custom-tests.yaml."""
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    cut = text.rfind(" ", 0, n)
    return text[: cut if cut > 0 else n] + "…"


def open_line(r: dict) -> str:
    bits = []
    if r.get("deferred_at"):
        # Render the reason here only when a route below won't — otherwise the same
        # sentence prints twice on a row that came in by more than one route.
        dup = r.get("blocked_at") or r.get("failed_at")
        why = f" — {clip(r['reason'])}" if r.get("reason") and not dup else ""
        bits.append(f"deferred {r['deferred_at']} ({r['accepted_by']}){why}")
    if r.get("blocked_at"):
        why = f" — {clip(r['reason'])}" if r.get("reason") else ""
        bits.append(f"blocked {r['blocked_at']}{why}")
    if r.get("failed_at"):
        why = f" — {clip(r['reason'])}" if r.get("reason") else ""
        bits.append(f"FAILED {r['failed_at']}{why}")
    return f"{r['verification']} — {' · '.join(bits)}"


def path_hits_verif(edges: list[dict], name: str, changed: list[str]) -> bool:
    return any(
        node_id(e["from"]) == name and path_hits(node_id(e["to"]), changed)
        for e in by_kind(edges, "COVERS")
    )


def owner_of(edges: list[dict], path: str) -> str:
    """First matching PATH_MAP pattern wins — the same rule the hooks apply."""
    for e in by_kind(edges, "OWNED_BY"):
        try:
            if re.search(node_id(e["from"]), path):
                return node_id(e["to"])
        except re.error:
            continue
    return "—"


def deliveries(edges: list[dict], changed: list[str]) -> list[dict]:
    task_of = {e["to"]: node_id(e["from"]) for e in by_kind(edges, "LANDED_AS")}
    hits = {}
    for e in by_kind(edges, "TOUCHES"):
        if path_hits(node_id(e["to"]), changed):
            hits.setdefault(e["from"], task_of.get(e["from"], "—"))
    return [{"commit": node_id(c), "task": t} for c, t in hits.items()]


def roadmap_open(edges: list[dict], src: "Sources", changed: list[str]) -> dict:
    """Every open roadmap item with its prior tasks, the newest log entry citing it, and a
    status breakdown of the total. `changed` marks items *affine* to those paths — ones
    whose prior delivered tasks touched them.

    Read from the roadmap file directly rather than the index: the file is the store and
    the edge index carries only the `ADDRESSES` half of the join."""
    addressed: dict[str, list[str]] = {}
    latest_addr: dict[str, str] = {}
    for e in by_kind(edges, "ADDRESSES"):
        rid = node_id(e["to"])
        addressed.setdefault(rid, []).append(node_id(e["from"]))
        ts = e.get("props", {}).get("ts", "")
        if ts > latest_addr.get(rid, ""):
            latest_addr[rid] = ts
    items, counts = [], {}
    for it in parse_roadmap(read(src.roadmap)):
        if not it["open"]:
            continue
        # A bare total is not trustworthy: an item with no `**Status:**` line defaults to
        # open, and on one real roadmap that is a third of the file. Dropping those would
        # be breaking — an item must surface rather than disappear — so the count is
        # reported broken down instead, and the caller prints what it is made of.
        counts_key = it["status"] if "Status" in it["fields"] else "no status line"
        counts[counts_key] = counts.get(counts_key, 0) + 1
        prior = addressed.get(it["id"], [])
        items.append(
            {
                "id": it["id"],
                "title": it["title"],
                "status": it["status"],
                "priority": it["priority"],
                "prior_tasks": prior,
                "last_addressed": latest_addr.get(it["id"], ""),
                "affine": bool(changed and prior),
            }
        )
    lead = ["open", "in-progress", "no status line"]
    ranked = [(k, counts[k]) for k in lead if k in counts] + sorted(
        ((k, v) for k, v in counts.items() if k not in lead),
        key=lambda kv: (-kv[1], kv[0]),
    )
    return {"open": len(items), "status_counts": dict(ranked), "items": items}


def emit(payload, as_json: bool, lines: list[str]) -> None:
    print(json.dumps(payload, indent=2) if as_json else "\n".join(lines) or "(none)")


# --------------------------------------------------------------------------------- cli


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    as_json = "--json" in rest
    rest = [a for a in rest if a != "--json"]
    src = Sources(find_root())

    if cmd == "build":
        edges = project(src)
        write_index(src, edges)
        # Report parse coverage: a heading the parser cannot read is delivery history lost
        # silently, which is exactly the failure this index exists to prevent.
        text = read(src.log)
        # Count on the fence-stripped text, or a documented format example inside a fence
        # reports as an entry the parser "missed" and raises a permanent false WARNING.
        headings = sum(
            1 for ln in strip_fences(text).splitlines() if ln.startswith("### ")
        )
        parsed = len(parse_log(text))
        print(
            f"{len(edges)} edges · {parsed}/{headings} log entries parsed "
            f"→ {src.out.relative_to(src.root)}"
        )
        if parsed < headings:
            missed = headings - parsed
            print(
                f"WARNING: {missed} log {'entry' if missed == 1 else 'entries'} did not parse "
                f"and contribute nothing to the graph — check the `### ` heading format",
                file=sys.stderr,
            )
        for title, n in headless_roadmap_items(read(src.roadmap)):
            print(
                f"WARNING: {n} `**Category:**` lines under one roadmap heading "
                f"({title!r}) — an item below it is missing its `### ` heading, so it is "
                f"invisible to roadmap-open and has no id the delivery log can cite",
                file=sys.stderr,
            )
        return 0

    edges = load(src)

    if cmd == "covers":
        names = covering(edges, rest)
        emit({"verifications": names}, as_json, names)

    elif cmd == "blast":
        # `blast <paths…> [--ids <roadmap-id>…]` — one composed pack per task, resolved
        # once at the top level and pasted into the qa and pm prompts, so the agents read
        # it from the cached prefix instead of each spending a turn on its own query.
        ids: list[str] = []
        if "--ids" in rest:
            at = rest.index("--ids")
            ids, rest = rest[at + 1 :], rest[:at]
        stat = last_status(edges)
        roadmap = roadmap_open(edges, src, rest)["items"]
        affine_ids = {i["id"] for i in roadmap if i["affine"]} | set(ids)
        report = {
            "owners": sorted({owner_of(edges, p) for p in rest}),
            "verifications": [
                {"name": n, **stat.get(n, {"status": "never-run"})}
                for n in covering(edges, rest)
            ],
            "recent_deliveries": deliveries(edges, rest)[:5],
            "open_deferrals": open_verifications(edges, rest),
            # Named ids first, then path-affine items: the pm step decides `Addresses:`
            # from exactly this set, and the qa step sees what the task claims to close.
            "roadmap": [
                {k: i[k] for k in ("id", "title", "status", "priority", "last_addressed")}
                for i in roadmap
                if i["id"] in affine_ids
            ],
            # Gates whose entry addressed one of those ids: the decisions holding this
            # work, which is what a task touching it needs to know before it re-opens one.
            "gates": [
                {k: g[k] for k in ("gate", "condition", "age_days", "releases")}
                for g in open_gates(edges)
                if set(g.get("releases", [])) & affine_ids
            ],
        }
        # Text form is what gets pasted into a prompt, so it folds: passing verifications
        # and path-affine items are one line of names each — the reader needs the set,
        # not a row per member — while anything unproven or named keeps its own row.
        passing = [v["name"] for v in report["verifications"] if v["status"] == "pass"]
        affine_only = [i for i in report["roadmap"] if i["id"] not in ids]
        emit(
            report,
            as_json,
            [f"owners: {', '.join(report['owners'])}"]
            + ([f"verif (pass, {len(passing)}): {', '.join(passing)}"] if passing else [])
            + [
                f"verif: {v['name']} [{v['status']}]"
                + (f" — {clip(v['reason'], 100)}" if v.get("reason") else "")
                for v in report["verifications"]
                if v["status"] != "pass"
            ]
            + [
                f"delivered: {d['commit']} {d['task']}"
                for d in report["recent_deliveries"]
            ]
            + [f"open: {open_line(d)}" for d in report["open_deferrals"]]
            + [
                f"roadmap: {i['id']} [{i['status']}] {clip(i['title'], 90)}"
                for i in report["roadmap"]
                if i["id"] in ids
            ]
            + (
                [
                    f"roadmap (affine, {len(affine_only)}): "
                    + ", ".join(i["id"] for i in affine_only)
                ]
                if affine_only
                else []
            )
            + [
                f"gate: {g['gate']} ({g['age_days']}d)"
                + (f" · awaits {clip(g['condition'], 80)}" if g["condition"] else "")
                + f" · releases {', '.join(g['releases'])}"
                for g in report["gates"]
            ],
        )

    elif cmd == "history":
        if not rest:
            print("history needs a path", file=sys.stderr)
            return 2
        reverted = {node_id(e["to"]) for e in by_kind(edges, "SUPERSEDES")}
        items = [
            {**d, "reverted": d["commit"] in reverted}
            for d in deliveries(edges, rest[:1])
        ]
        report = {
            "path": rest[0],
            "owner": owner_of(edges, rest[0]),
            "deliveries": items,
        }
        emit(
            report,
            as_json,
            [f"owner: {report['owner']}"]
            + [
                f"{d['commit']} {d['task']}{' (REVERTED)' if d['reverted'] else ''}"
                for d in items
            ],
        )

    elif cmd == "roadmap-open":
        changed = rest[rest.index("--for") + 1 :] if "--for" in rest else []
        report = roadmap_open(edges, src, changed)
        emit(
            report,
            as_json,
            [
                f"{report['open']} open — "
                + " · ".join(f"{v} {k}" for k, v in report["status_counts"].items())
            ]
            + [
                f"{'~match ' if i['affine'] else ''}{i['id']} [{i['priority'] or '?'}] {i['title']}"
                for i in report["items"]
            ],
        )

    elif cmd == "open-gates":
        gates = open_gates(edges)
        emit({"gates": gates}, as_json, [gate_line(g) for g in gates])

    elif cmd == "open-deferrals":
        with_fail = "--with-fail" in rest
        rest = [a for a in rest if a != "--with-fail"]
        rows = open_verifications(edges, rest or None, with_fail)
        emit({"deferrals": rows}, as_json, [open_line(r) for r in rows])

    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BrokenPipeError:
        os._exit(0)
