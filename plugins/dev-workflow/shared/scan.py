#!/usr/bin/env python3
"""Run the security slots in scanners.yaml, decide what is new, and gate the push.

    scan.py run --at task|ship|deploy|every [--base SHA] [--url URL]
    scan.py gate                     # push hook: run missing ship slots, exit 2 on a hold
    scan.py baseline                 # install/upgrade: existing findings become backlog
    scan.py record <entry> --findings FILE|-   # a model-run slot's result (change review)
    scan.py status [--one-line]
    scan.py backlog [--count]
    scan.py version-only --base SHA  # exit 1 when a manifest edit is more than a version change

Advisories published against packages a change did not touch are watch.py's (it re-checks the whole
tree on a clock); a push holds only on what the change itself introduced.

Tools find; this file only runs them, reads their output and counts. Whether a finding is
real is the model's call, recorded as a vex.yaml statement. Writes nothing tracked except
scan-baseline.txt (by `baseline` only); results live in the gitignored .claude/scans/.
"""
import argparse
import functools
import importlib.util
import json
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import findings as F  # noqa: E402

TIMEOUT = 240  # per entry; two tries stay under the hook's 600 s


def git(*args, cwd=None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd or ROOT, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


ROOT = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()) or Path.cwd())
# This file lives in <PREFIX>-review/scripts/; its own skill's references hold the slots. Found from
# this path, never by folder name, so a project skill whose name also ends in -review is never read.
REVIEW = HERE.parent / "references"
if not (REVIEW / "scanners.yaml").is_file():
    sys.exit(f"scan.py: no scanners.yaml beside this script ({REVIEW}), so no slot can run. "
             "scan.py belongs in .claude/skills/<PREFIX>-review/scripts/ — re-run /dev-workflow:upgrade.")
SCANS = ROOT / ".claude" / "scans"
BASELINE = REVIEW / "scan-baseline.txt"


@functools.lru_cache(None)
def graph():
    """graph.py's parsers read scanners.yaml, vex.yaml and the path map. Without them no slot can
    be read, so the gate blocks, naming the cause, rather than passing unscanned or crashing."""
    path = ROOT / ".claude" / "graph" / "graph.py"
    if not path.is_file():
        sys.exit("scan.py: .claude/graph/graph.py is missing, so scanners.yaml cannot be read. "
                 "Restore it (git checkout -- .claude/graph/graph.py) or re-run /dev-workflow:upgrade.")
    spec = importlib.util.spec_from_file_location("_graph", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(p: Path) -> str:
    return p.read_text() if p.is_file() else ""


def entries() -> list[dict]:
    out = graph().parse_block_yaml(read(REVIEW / "scanners.yaml"), "name", list_keys=("at",))
    for e in out:
        e["at"] = e["at"] or ["every"]  # an entry from before slots is a cadence scan
    return out


def conf(name: str) -> str:
    # Read as bash reads it: a trailing `# comment` after the closing quote is not part of the value.
    m = re.search(rf"^{name}='([^']*)'\s*(#.*)?$", read(ROOT / ".claude/hooks/governed-paths.conf"), re.M)
    return m.group(1) if m else ""


def exempt(path: str) -> bool:
    """State files (vex.yaml, the logs) never make a stored scan stale."""
    pm = graph().parse_path_map(read(ROOT / ".claude/hooks/governed-paths.conf"))
    return any(re.search(p, path) for p, s in pm if s == "EXEMPT")


def ancestor(a: str, b: str) -> bool:
    return bool(a and b) and subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=ROOT,
                                             capture_output=True).returncode == 0


def changed(base: str, head: str = "HEAD", deleted: bool = False) -> list[str]:
    """Files a tool can scan; with `deleted`, every file the range touched, since removing a
    governed file needs a review and makes a stored result stale just as editing one does."""
    filt = "AMRD" if deleted else "AMR"
    return [f for f in git("diff", "--name-only", f"--diff-filter={filt}", f"{base}..{head}").splitlines() if f]


def in_scope(e: dict, files: list[str]) -> list[str]:
    """`paths:` is an ERE, or `$NAME` for a governed-paths.conf variable, so a pattern the
    hooks already keep (the dependency manifests) lives in one place."""
    pat = e.get("paths", "")
    pat = conf(pat[1:]) if pat.startswith("$") else pat
    return [f for f in files if not pat or re.search(pat, f)]


# ------------------------------------------------------------------ running


def launch(e: dict, outdir: Path, rng: str, files: list[str], url: str):
    out = outdir / f"{e['name']}.out"
    out.unlink(missing_ok=True)  # a tool that fails without writing must never leave the last run's output to be read as this one's
    cmd = (e["command"].replace("{out}", shlex.quote(str(out))).replace("{range}", shlex.quote(rng))
           .replace("{files}", " ".join(map(shlex.quote, files)) or ".").replace("{url}", shlex.quote(url)))
    log = open(outdir / f"{e['name']}.log", "w")
    # The command is a scanners.yaml template (committed repo config) with every value shlex-quoted.
    return subprocess.Popen(cmd, shell=True, cwd=ROOT, stdout=log, stderr=log), out  # nosemgrep: python.lang.security.audit.subprocess-shell-true.subprocess-shell-true


def run_entries(sel: list[dict], at: str, base: str, url: str, whole: bool) -> dict:
    head = git("rev-parse", "HEAD")
    outdir = SCANS / head[:7]
    outdir.mkdir(parents=True, exist_ok=True)
    # Tool output can quote a redacted secret's surroundings: never let it be committed,
    # whatever the project's own .gitignore says.
    (SCANS / ".gitignore").write_text("*\n")
    rng = base if whole else f"{base}..{head}"
    files = git("ls-files").splitlines() if whole else changed(base)
    state, todo = {}, []
    for e in sel:
        scope = in_scope(e, files)
        rec = {"slot": e.get("slot", ""), "at": at, "base": base, "head": head, "findings": []}
        if e.get("skill"):
            continue  # a model-run slot reports through `record`
        if whole and not e.get("paths"):
            scope = []  # whole tree, no filter: the command gets `.` rather than every file
        if not e.get("command"):
            state[e["name"]] = {**rec, "state": "empty"}
        elif not whole and not scope:
            state[e["name"]] = {**rec, "state": "ran", "seconds": 0, "skipped": True}  # nothing in its scope changed
        else:
            todo.append((e, rec, scope))
    for attempt in (1, 2):  # one retry: a network blip is not a hold
        procs = [(e, rec, scope, time.time(), *launch(e, outdir, rng, scope, url)) for e, rec, scope in todo]
        todo = []
        while procs:  # poll, so each slot's own time and timeout are its own
            time.sleep(0.2)
            for item in list(procs):
                e, rec, scope, t0, p, out = item
                secs = round(time.time() - t0, 1)
                if p.poll() is None and secs < int(e.get("timeout") or TIMEOUT):
                    continue
                procs.remove(item)
                try:
                    if p.poll() is None:
                        p.kill()
                        raise TimeoutError(f"over {e.get('timeout') or TIMEOUT}s")
                    found = F.read(out, e.get("format", "sarif"), e.get("slot", ""), ROOT)
                    if (not whole or e.get("paths")) and "{range}" not in e["command"]:
                        # A tool that scans the tree reports old lines too; keep the changed files.
                        # Range tools (commits) and package-level findings (no line) are already scoped.
                        found = [f for f in found if not f["line"] or f["file"] in scope]
                    state[e["name"]] = {**rec, "state": "ran", "seconds": secs, "findings": found}
                except Exception as err:  # timeout, missing or unreadable output
                    state[e["name"]] = {**rec, "state": "errored", "seconds": secs,
                                        "error": f"{type(err).__name__}: see .claude/scans/{head[:7]}/{e['name']}.log"}
                    if attempt == 1:
                        todo.append((e, rec, scope))
        if not todo:
            break
    for e in sel:  # the SBOM rides along with a ship run of the slot that declares one
        if at == "ship" and e.get("sbom") and state.get(e["name"], {}).get("state") == "ran":
            sbom = outdir / "sbom.cdx.json"
            r = subprocess.run(e["sbom"].replace("{out}", shlex.quote(str(sbom))), shell=True, cwd=ROOT,  # nosemgrep: python.lang.security.audit.subprocess-shell-true.subprocess-shell-true
                               capture_output=True, timeout=int(e.get("timeout") or TIMEOUT))
            state[e["name"]]["sbom"] = str(sbom.relative_to(ROOT)) if r.returncode == 0 and sbom.exists() else "failed"
    if not whole:
        save(outdir, state)
    return state


def save(outdir: Path, state: dict):
    p = outdir / "state.json"
    old = json.loads(read(p) or "{}")
    p.write_text(json.dumps({**old, **state}, indent=1))


# ------------------------------------------------------------------ deciding


def decisions() -> dict:
    """vex.yaml statements by key. A dependency keys on id + package without the version,
    so a bump never turns a decided advisory into a hold; /audit re-opens it by version."""
    out = {}
    for s in graph().parse_vex(read(REVIEW / "vex.yaml")):
        pkg = s.get("package", "")
        out[f"{s['id']}@{pkg.rsplit('@', 1)[0]}" if pkg else s["id"]] = s
    return out


def baseline_keys() -> set[str]:
    return {ln.split()[1] for ln in read(BASELINE).splitlines() if len(ln.split()) > 1}


def at_commit(sha: str, sel: list[dict]) -> dict:
    """Run `sel` on the whole tree at `sha`, on a temporary checkout; HEAD's tree is never touched."""
    global ROOT
    keep, tmp = ROOT, str(Path(tempfile.mkdtemp(prefix="scan-at-")).resolve())  # resolved: tools report /private/var, not /var
    git("worktree", "add", "--detach", tmp, sha)
    try:
        ROOT = Path(tmp)
        return run_entries(sel, "every", sha, "", whole=True)
    finally:
        ROOT = keep
        git("worktree", "remove", "--force", tmp)


@functools.lru_cache(None)
def deps_before(base: str, fresh: bool = False) -> frozenset | None:
    """Advisory keys the dependency slot finds at `base`, cached per commit; None when it cannot say.
    The cache only ever answers "present": an advisory published since it was written is missing from
    it, so a miss re-scans (`fresh`) before anything holds."""
    if not base or subprocess.run(["git", "rev-parse", "-q", "--verify", f"{base}^{{commit}}"], cwd=ROOT,
                                  capture_output=True).returncode:
        return None
    cache = SCANS / base[:7] / "deps-before.json"
    if cache.is_file() and not fresh:
        return frozenset(json.loads(cache.read_text()))
    sel = [e for e in entries() if e.get("slot") == "dependencies" and e.get("command")]
    state = at_commit(base, sel) if sel else {}
    if not state or any(r["state"] != "ran" for r in state.values()):
        return None
    keys = sorted({f["key"] for r in state.values() for f in r["findings"]})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(keys))
    return frozenset(keys)


def introduced(f: dict, r: dict) -> bool:
    """Whether this change brought the advisory in: the dependency slot does not find it at the range's
    base. One already there was published on its own clock — the watch counts it and /audit owns it,
    never this push. Asked of a review (task, ship) only; base unreadable or its scan failed → introduced."""
    if r.get("at") not in ("task", "ship"):
        return True
    before = deps_before(r.get("base", ""))
    if before is not None and f["key"] in before:
        return False
    before = deps_before(r.get("base", ""), fresh=True)
    return before is None or f["key"] not in before


@functools.lru_cache(None)
def roadmap_status() -> dict:
    """Roadmap id → its status word, one item per heading block."""
    out = {}
    for block in re.split(r"\n(?=#{2,4} )", read(ROOT / "docs" / "roadmap.md")):
        i = re.search(r"\*\*Id:\*\*\s*`?([\w.-]+)", block)
        st = re.search(r"\*\*Status:\*\*\s*`?([\w-]+)", block)
        if i:
            out[i.group(1)] = (st.group(1) if st else "").lower()
    return out


def filed_item(ids: str) -> bool:
    """`addressed:` names roadmap items still to do (open, in progress, parked or blocked). A name nobody
    filed, or an item marked done while the advisory is still found, never stands in for a decision."""
    want = [i for i in re.split(r"[,\s]+", str(ids)) if i]
    live = ("open", "in-progress", "parked", "blocked")
    return bool(want) and all(roadmap_status().get(i) in live for i in want)


def version_only(base: str) -> list[str]:
    """Lines a range added to a non-lock dependency manifest that are not an existing line with only
    its version changed — a package added, or anything else edited. Lockfiles are regenerated by their
    tool, so they are not read. Empty means the range only moved versions."""
    pat = conf("DEPENDENCY_MANIFESTS")
    files = [f for f in changed(base) if pat and re.search(pat, f) and not re.search(r"lock|\.sum$", Path(f).name, re.I)]
    # A version is a number not glued to a name, so h2 → h11 or psycopg2 → psycopg3 is a different package.
    norm = lambda ln: re.sub(r"(?<![A-Za-z0-9_-])\d[\w.+-]*", "V", ln).strip()
    bad = []
    for f in files:
        diff = git("diff", "-U0", f"{base}..HEAD", "--", f).splitlines()
        gone = {norm(ln[1:]) for ln in diff if ln.startswith("-") and not ln.startswith("---")}
        bad += [f"{f}: {ln[1:].strip()}" for ln in diff if ln.startswith("+") and not ln.startswith("+++")
                and ln[1:].strip() and norm(ln[1:]) not in gone]
    return bad


def verdict(state: dict) -> dict:
    dec, old = decisions(), baseline_keys()
    v = {"undecided": [], "held": [], "errored": [], "empty": [], "ran": [], "skipped": [], "decided": 0}
    for name, r in state.items():
        v[r["state"] if r["state"] in ("errored", "empty") else "skipped" if r.get("skipped") else "ran"].append(name)
        for f in r.get("findings", []):
            # An advisory's aliases (GHSA, CVE, PYSEC) are one flaw: a statement under any of them counts.
            ids = (f.get("dep") or {}).get("aliases") or []
            found = [dec[k] for k in [f["key"]] + [f"{i}@{f['dep']['package']}" for i in ids] if k in dec]
            s = next((c for c in found if c.get("status") != "under_investigation"), found[0] if found else None)
            if s and s.get("status") == "fixed":
                v["held"].append(f)  # `fixed` yet still found is not fixed — backlog or not, it came back
                continue
            if f["key"] in old:
                continue  # existed before the slots ran: /audit's backlog, never a hold
            if f.get("dep") and not introduced(f, r):
                continue  # published against a package this change left alone: the watch's, not this push's
            if s is None or s.get("status") == "under_investigation":
                v["undecided"].append(f)  # seen is not decided
                continue
            v["decided"] += 1
            if s.get("status") == "affected" and f["severity"] != "low":
                v["held"].append(f)
    return v


def line(f: dict) -> str:
    return f"{f['severity']:<8} {f['slot']:<14} {f['file']}:{f['line']}  {f['rule']}  key={f['key']}"


def summary(v: dict) -> str:
    s = f"security: {len(v['ran'])} ran"
    s += f" ({len(v['skipped'])} with nothing in scope: {', '.join(v['skipped'])})" if v.get("skipped") else ""
    s += f" · empty: {', '.join(v['empty'])}" if v["empty"] else ""
    s += f" · errored: {', '.join(v['errored'])}" if v["errored"] else ""
    return s + f" · new {len(v['undecided']) + v['decided']}: {v['decided']} decided, {len(v['undecided'])} undecided, {len(v['held'])} held"


def latest(head: str, matters=lambda f: not exempt(f)) -> dict:
    """Stored results this HEAD can reuse: same head, or an older head where nothing that
    `matters` changed since — for a tool, anything but a state file; for a model review,
    the governed and deploy paths it was asked to read (today's review-mark rule)."""
    best = {}
    for p in sorted(SCANS.glob("*/state.json"), key=lambda p: p.stat().st_mtime):
        for name, r in json.loads(read(p) or "{}").items():
            h = r.get("head", "")
            if h == head or (ancestor(h, head) and not any(matters(f) for f in changed(h, head, deleted=True))):
                best[name] = r
    return best


# ------------------------------------------------------------------ commands


def cmd_run(a):
    sel = [e for e in entries() if a.at in e["at"]]
    whole = a.at in ("every", "deploy")
    base = a.base or git("rev-parse", "origin/HEAD" if a.at == "ship" else "HEAD")
    if a.at == "task" and not a.base:
        sys.exit("run --at task needs --base <the task's first parent>")
    state = run_entries(sel, a.at, base, a.url or "", whole=whole)
    v = verdict(state)
    print(summary(v))
    for f in v["undecided"]:
        print("NEW", line(f))
    for f in v["held"]:
        print("HELD", line(f))
    watch = HERE / "watch.py"
    if watch.is_file() and a.at in ("task", "ship"):
        # Advisories are published on their own clock: refresh the whole-tree check beside the work
        # (detached, never waited on), and print the open count the last check left.
        subprocess.run([sys.executable, str(watch), "refresh", "--if-older", "--background"], cwd=ROOT)
        print(subprocess.run([sys.executable, str(watch), "open", "--line"], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip())


def cmd_gate(a):
    origin, head = git("rev-parse", "origin/HEAD"), git("rev-parse", "HEAD")
    if not origin:
        print("security gate: no origin/HEAD — run `git remote set-head origin -a`", file=sys.stderr)
        sys.exit(2)
    ship = [e for e in entries() if "ship" in e["at"]]
    pats = [p for p in (conf("GOVERNED_ROOTS"), conf("DEPLOY_PATHS")) if p]
    risky_file = lambda f: any(re.search(p, f) for p in pats)
    have = latest(head)
    have.update({e["name"]: r for e in ship if e.get("skill")
                 for n, r in latest(head, risky_file).items() if n == e["name"]})
    # A stored result counts only if it was a ship run whose range reaches back to origin:
    # a task review's narrower range never stands in for what is about to be pushed.
    valid = {n: r for n, r in have.items() if r.get("at") == "ship" and ancestor(r.get("base", ""), origin)}
    state = {e["name"]: valid[e["name"]] for e in ship if e["name"] in valid}
    missing = [e for e in ship if not e.get("skill") and e["name"] not in valid]
    if missing:
        state.update(run_entries(missing, "ship", origin, "", whole=False))
    reasons = []
    risky = any(risky_file(f) for f in changed(origin, head, deleted=True))
    for e in ship:
        if e.get("skill") and risky and e["name"] not in state:
            reasons.append(f"{e['name']} has not reviewed this range — use the `{e['skill']}` skill, then `scan.py record {e['name']}`")
    v = verdict(state)
    reasons += [f"slot errored twice: {n} (see its log under .claude/scans/)" for n in v["errored"]]
    if v["undecided"]:
        reasons.append(f"{len(v['undecided'])} new finding(s) need a vex.yaml decision — `scan.py status` lists them")
    if v["held"]:
        reasons.append(f"{len(v['held'])} finding(s) hold the ship (affected, not low) — fix or file them")
    print(summary(v), file=sys.stderr)
    if reasons:
        print("security gate:\n  " + "\n  ".join(reasons), file=sys.stderr)
        sys.exit(2)


def cmd_baseline(a):
    """Existing findings at origin/HEAD become backlog, so the first push still reviews the
    unpushed work instead of baselining it."""
    origin = git("rev-parse", "origin/HEAD") or git("rev-parse", "HEAD")
    sel = [e for e in entries() if {"task", "ship"} & set(e["at"]) and e.get("command")]
    state = at_commit(origin, sel)
    rows = sorted({f"{f['slot']} {f['key']} {f['severity']} {f['rule']} {f['file']}"
                   for r in state.values() for f in r["findings"]})
    BASELINE.write_text("# scan-baseline.txt — findings that existed before the slots ran; backlog for /audit, never a hold.\n"
                        "# <slot> <key> <severity> <rule> <file>. Written only by `scan.py baseline`.\n" + "\n".join(rows) + "\n")
    for n, r in state.items():
        print(f"{n}: {r['state']} {r.get('seconds', 0)}s {len(r['findings'])} findings")


def cmd_record(a):
    e = next((x for x in entries() if x["name"] == a.entry), None)
    if e is None:
        sys.exit(f"no scanners.yaml entry named {a.entry}")
    raw = json.loads(sys.stdin.read() if a.findings == "-" else Path(a.findings).read_text())
    head = git("rev-parse", "HEAD")
    found = [{"slot": e.get("slot", ""), "rule": x.get("category", "-"), "file": x.get("file", "-"), "line": int(x.get("line") or 0),
              "severity": (x.get("severity") or "unrated").lower(), "cwe": x.get("cwe", ""), "dep": None,
              "key": f"{e.get('slot', '')}/{x.get('category', '-')}/{x.get('file', '-')}:{x.get('line', 0)}"} for x in raw]
    outdir = SCANS / head[:7]
    outdir.mkdir(parents=True, exist_ok=True)
    save(outdir, {e["name"]: {"slot": e.get("slot", ""), "at": "ship", "base": git("rev-parse", "origin/HEAD"),
                              "head": head, "state": "ran", "findings": found}})
    print(summary(verdict({e["name"]: {"state": "ran", "findings": found}})))


def cmd_status(a):
    v = verdict(latest(git("rev-parse", "HEAD")))
    print(summary(v))
    if not a.one_line:
        for f in v["undecided"]:
            print("NEW", line(f))
        for f in v["held"]:
            print("HELD", line(f))


def cmd_backlog(a):
    dec = decisions()
    rows = [ln.split(None, 4) for ln in read(BASELINE).splitlines() if ln and not ln.startswith("#")]
    open_ = [r for r in rows if r[1] not in dec]
    counted = [r for r in open_ if r[2] != "low"]
    if a.count:
        print(f"{len(counted)} backlog finding(s) above low, {len(open_) - len(counted)} low")
    else:
        for r in counted:
            print(" ".join(r))


def cmd_version_only(a):
    bad = version_only(a.base)
    for b in bad:
        print("NOT A VERSION CHANGE", b)
    print(f"manifests: {'version changes only' if not bad else f'{len(bad)} other line(s)'}")
    sys.exit(1 if bad else 0)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--at", required=True, choices=["task", "ship", "deploy", "every"])
    r.add_argument("--base")
    r.add_argument("--url")
    sub.add_parser("gate")
    sub.add_parser("baseline")
    rc = sub.add_parser("record")
    rc.add_argument("entry")
    rc.add_argument("--findings", required=True)
    s = sub.add_parser("status")
    s.add_argument("--one-line", action="store_true")
    b = sub.add_parser("backlog")
    b.add_argument("--count", action="store_true")
    vo = sub.add_parser("version-only")
    vo.add_argument("--base", required=True)
    a = p.parse_args()
    {"run": cmd_run, "gate": cmd_gate, "baseline": cmd_baseline, "record": cmd_record,
     "status": cmd_status, "backlog": cmd_backlog, "version-only": cmd_version_only}[a.cmd](a)


if __name__ == "__main__":
    main()
