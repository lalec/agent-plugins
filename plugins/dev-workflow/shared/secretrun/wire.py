"""`secretrun init [--global]` — wire this folder into Claude Code settings.

Adds three hooks and the read-deny rules, idempotently, without touching
unrelated settings:
  SessionStart  puts this folder on PATH, so `secretrun` works by name
  PreToolUse    guard.py on Bash — denies commands that would print values
  PostToolUse   redact.py — scrubs credential-shaped strings from tool output
  deny          Read of .env files (never .env.example), ~/.aws, ~/.ssh, gcloud

Project scope (default) writes <repo>/.claude/settings.json with paths relative
to $CLAUDE_PROJECT_DIR, so a committed settings file works in every clone.
--global writes ~/.claude/settings.json with absolute paths and backs it up.
Nothing here restricts reading session transcripts.
"""
import json
import os
import shutil
import subprocess
import time

HERE = os.path.dirname(os.path.realpath(__file__))
ENV_FILES = [".env", ".env.local", ".env.development", ".env.development.local",
             ".env.test", ".env.test.local", ".env.production",
             ".env.production.local"]
DENY = ([f"Read(**/{f})" for f in ENV_FILES]
        + ["Read(~/.aws/**)", "Read(~/.ssh/**)", "Read(~/.config/gcloud/**)"])


def _repo_root():
    p = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else os.getcwd()


def _folder_ref(root):
    """How a hook command names this folder: project-relative when inside the
    project, absolute otherwise."""
    if root:
        rel = os.path.relpath(HERE, root)
        if not rel.startswith(".."):
            return '"$CLAUDE_PROJECT_DIR"/' + rel
    return '"%s"' % HERE


def hook_entries(ref):
    path_cmd = ('[ -z "$CLAUDE_ENV_FILE" ] || printf \'export PATH="%%s:$PATH"\\n\' '
                '%s >> "$CLAUDE_ENV_FILE"' % ref)
    return {
        "SessionStart": {"hooks": [{"type": "command", "command": path_cmd}]},
        "PreToolUse": {"matcher": "Bash", "hooks": [
            {"type": "command", "command": f"python3 {ref}/guard.py", "timeout": 5}]},
        "PostToolUse": {"matcher": "Bash|Read|Grep|WebFetch", "hooks": [
            {"type": "command", "command": f"python3 {ref}/redact.py", "timeout": 5}]},
    }


def merge(settings, ref):
    """Merge hooks + deny rules into a settings dict. Returns what changed."""
    changed = []
    hooks = settings.setdefault("hooks", {})
    for event, entry in hook_entries(ref).items():
        cur = hooks.setdefault(event, [])
        have = {h.get("command") for e in cur for h in e.get("hooks", [])}
        if entry["hooks"][0]["command"] not in have:
            cur.append(entry)
            changed.append(f"hooks.{event} += {entry['hooks'][0]['command']}")
    deny = settings.setdefault("permissions", {}).setdefault("deny", [])
    for rule in DENY:
        if rule not in deny:
            deny.append(rule)
            changed.append(f"permissions.deny += {rule}")
    return changed


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def init(args):
    unknown = [a for a in args if a != "--global"]
    if unknown:
        print(f"secretrun init: unknown argument {unknown[0]}")
        return 1
    if "--global" in args:
        path, ref = os.path.expanduser("~/.claude/settings.json"), _folder_ref(None)
    else:
        root = _repo_root()
        path, ref = os.path.join(root, ".claude", "settings.json"), _folder_ref(root)
    try:
        settings = _load(path)
    except (OSError, ValueError) as e:
        print(f"secretrun init: cannot read {path}: {e}")
        return 1
    changed = merge(settings, ref)
    if not changed:
        print(f"already wired: {path}")
        return 0
    if "--global" in args and os.path.isfile(path):
        shutil.copy2(path, f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    print(f"wired {path}:")
    for c in changed:
        print(f"  + {c}")
    print("Applies to new sessions.")
    return 0
