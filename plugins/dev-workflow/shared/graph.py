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
    graph.py blast <path>...         owning skills - covering verifs - deliveries - deferrals
    graph.py history <path>          what has been delivered, verified and reverted here
    graph.py roadmap-open [--for <path>...]   open items, path-affine ones marked ~match
    graph.py open-deferrals [<path>...]       deferred and never since passed

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
TOKEN_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)+$")
BACKTICK_RE = re.compile(r"`([^`]+)`")
DEPLOYED_RE = re.compile(r"([A-Za-z0-9_-]+)\s*→\s*([A-Za-z0-9_-]+)\s*·\s*(\S+)")
DECISION_RE = re.compile(r"([a-z_-]+)\s*=\s*([A-Za-z0-9_-]+)\s*\(([^)]*)\)")


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


def parse_log(text: str) -> list[dict]:
    """Delivery-log entries, newest first (the file is written top-insertion)."""
    entries: list[dict] = []
    lines = text.splitlines()
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


def parse_roadmap(text: str) -> list[dict]:
    """`### title` items carrying `- **Field:** value` lines, grouped under `## Section`."""
    items: list[dict] = []
    section = ""
    cur: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## ") and not line.startswith("### "):
            section = line[3:].strip()
            cur = None
        elif line.startswith("### "):
            cur = {"title": line[4:].strip(), "section": section, "fields": {}}
            items.append(cur)
        elif cur is not None and line.startswith("- "):
            m = FIELD_RE.match(line[2:])
            if m:
                cur["fields"][m.group(1).strip()] = m.group(2).strip()
    for it in items:
        # **Id:** is authoritative once present; fall back to the title slug so this
        # works on installs that predate the field and on items not yet backfilled.
        it["id"] = it["fields"].get("Id") or slug(it["title"])
        it["status"] = it["fields"].get("Status", "open").split("·")[0].strip().lower()
        it["priority"] = it["fields"].get("Priority", "").strip().lower()
    return items


def _scalar(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        inner = v[1:-1]
        return inner.replace("''", "'") if v[0] == "'" else inner
    return v


def parse_custom_tests(text: str) -> list[dict]:
    """Minimal reader for the fixed, machine-written custom-tests.yaml shape.

    Handles `paths:` as a block list or an inline flow list, and the optional
    `last:` block. Deliberately not a general YAML parser — the schema is fixed.
    """
    tests: list[dict] = []
    cur: dict | None = None
    key: str | None = None
    for raw in text.splitlines():
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
        if key == "last" and indent >= 6:
            cur["last"][k] = _scalar(v)
            continue
        key = None
        cur[k] = _scalar(v)
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
        props["kind"] = "serve" if "run" in props else "ship" if "deploy" in props else "?"
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
    return [t for t in (p.strip().strip("`*_") for p in value.split("·")) if TOKEN_RE.match(t)]


def project(src: Sources) -> list[dict]:
    """Full reprojection. There is deliberately no incremental mode: a full build is
    under a second on the largest real corpus, and an append path would leave deleted
    verifications and retired path patterns lingering in the index."""
    edges: list[dict] = []
    entries = parse_log(read(src.log))

    for e in entries:
        sha, f = e["sha"], e["fields"]
        task = f"task:{slug(e['title'])}"
        where = f"project-log.md#{sha or slug(e['title'], 20)}"

        for rid in (r.strip() for r in f.get("Addresses", "").split(",")):
            if rid and TOKEN_RE.match(rid.strip("`")):
                edges.append(
                    edge("ADDRESSES", task, f"road:{rid.strip('`')}", f"{where}.Addresses")
                )

        # An entry may name several commits (older multi-hash entries) or none at all
        # (`uncommit`, `<uncommitted>`). Commit-keyed edges only exist when a sha does.
        for s in e["shas"]:
            edges.append(edge("LANDED_AS", task, f"commit:{s}", where))
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

        decisions = dict(
            (gate, by.strip()) for gate, _v, by in DECISION_RE.findall(f.get("Decisions", ""))
        )

        deferred = f.get("UAT-deferred", "")
        if deferred and not deferred.lower().startswith("none"):
            # `**Decisions:** defer=…` is the structured record and wins. The prose scan is
            # only a fallback for entries written before that field existed.
            accepted = decisions.get("defer") or (
                "timeout"
                if "timeout" in deferred.lower()
                else "user" if "user-confirmed" in deferred.lower() else "unstated"
            )
            for name in BACKTICK_RE.findall(deferred):
                if TOKEN_RE.match(name.strip()):
                    edges.append(
                        edge(
                            "DEFERRED",
                            f"commit:{sha}",
                            f"verif:{name.strip()}",
                            f"{where}.UAT-deferred",
                            accepted_by=accepted,
                        )
                    )

        for gate, value, by in DECISION_RE.findall(f.get("Decisions", "")):
            edges.append(
                edge(
                    "DECIDED",
                    f"commit:{sha}",
                    f"dec:{sha}/{gate}",
                    f"{where}.Decisions",
                    value=value,
                    by=by.strip(),
                )
            )

    shas = {s for e in entries for s in e["shas"]}
    for sha, paths in git_touches(src.root, shas).items():
        for p in paths:
            edges.append(edge("TOUCHES", f"commit:{sha}", f"path:{p}", "git log --name-only"))

    for newer, older in git_reverts(src.root):
        edges.append(
            edge("SUPERSEDES", f"commit:{newer}", f"commit:{older}", "git log --grep=^Revert")
        )

    for t in parse_custom_tests(read(src.tests)):
        name = t.get("name", "")
        if not name:
            continue
        for p in t.get("paths", []):
            edges.append(
                edge("COVERS", f"verif:{name}", f"path:{p}", f"custom-tests.yaml#{name}.paths")
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
                )
            )

    for pattern, owner in parse_path_map(read(src.conf)):
        edges.append(edge("OWNED_BY", f"path:{pattern}", f"skill:{owner}", "governed-paths.conf"))

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
    stale = not edges or meta.get("version") != VERSION or meta.get("head") != head_sha(src.root)
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
        if c.startswith(pattern.rstrip("/") + "/") or pattern.startswith(c.rstrip("/") + "/"):
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
    return out


def open_deferrals(edges: list[dict], changed: list[str] | None) -> list[dict]:
    """Deferred at some point and not passing since. Chronology is the log's own order
    (newest first), so a DEFERRED edge is open unless a later VERIFIED pass exists."""
    passed = {n for n, v in last_status(edges).items() if v["status"] == "pass"}
    seen, out = set(), []
    for e in by_kind(edges, "DEFERRED"):
        name = node_id(e["to"])
        if name in passed or name in seen:
            continue
        if changed and not path_hits_verif(edges, name, changed):
            continue
        seen.add(name)
        out.append(
            {
                "verification": name,
                "deferred_at": node_id(e["from"]),
                "accepted_by": e.get("props", {}).get("accepted_by", "unstated"),
                "src": e["src"],
            }
        )
    return out


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
        headings = sum(1 for ln in text.splitlines() if ln.startswith("### "))
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
        return 0

    edges = load(src)

    if cmd == "covers":
        names = covering(edges, rest)
        emit({"verifications": names}, as_json, names)

    elif cmd == "blast":
        stat = last_status(edges)
        report = {
            "owners": sorted({owner_of(edges, p) for p in rest}),
            "verifications": [
                {"name": n, **stat.get(n, {"status": "never-run"})} for n in covering(edges, rest)
            ],
            "recent_deliveries": deliveries(edges, rest)[:5],
            "open_deferrals": open_deferrals(edges, rest),
        }
        emit(
            report,
            as_json,
            [f"owners: {', '.join(report['owners'])}"]
            + [f"verif: {v['name']} [{v['status']}]" for v in report["verifications"]]
            + [f"delivered: {d['commit']} {d['task']}" for d in report["recent_deliveries"]]
            + [f"deferred: {d['verification']} ({d['accepted_by']})" for d in report["open_deferrals"]],
        )

    elif cmd == "history":
        if not rest:
            print("history needs a path", file=sys.stderr)
            return 2
        reverted = {node_id(e["to"]) for e in by_kind(edges, "SUPERSEDES")}
        items = [
            {**d, "reverted": d["commit"] in reverted} for d in deliveries(edges, rest[:1])
        ]
        report = {"path": rest[0], "owner": owner_of(edges, rest[0]), "deliveries": items}
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
        addressed: dict[str, list[str]] = {}
        for e in by_kind(edges, "ADDRESSES"):
            addressed.setdefault(node_id(e["to"]), []).append(node_id(e["from"]))
        items = []
        for it in parse_roadmap(read(src.roadmap)):
            if it["status"] not in ("open", "in-progress"):
                continue
            prior = addressed.get(it["id"], [])
            items.append(
                {
                    "id": it["id"],
                    "title": it["title"],
                    "status": it["status"],
                    "priority": it["priority"],
                    "prior_tasks": prior,
                    "affine": bool(changed and prior),
                }
            )
        emit(
            {"items": items},
            as_json,
            [
                f"{'~match ' if i['affine'] else ''}{i['id']} [{i['priority'] or '?'}] {i['title']}"
                for i in items
            ],
        )

    elif cmd == "open-deferrals":
        rows = open_deferrals(edges, rest or None)
        emit(
            {"deferrals": rows},
            as_json,
            [f"{r['verification']} — deferred {r['deferred_at']} ({r['accepted_by']})" for r in rows],
        )

    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BrokenPipeError:
        os._exit(0)
