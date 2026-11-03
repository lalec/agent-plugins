"""`srun setup` — prepare the current project for srun, idempotently.

  .srun.json   gets a namespace from the repo folder name, once (created when
               missing) — committed, so every clone and worktree uses the same
               store ids; an existing namespace is never rewritten. `--store`
               sets the project's store; the file is kept in its short form
  CLAUDE.md    gets the `## Secrets` section from secrets-rule.md, replacing an
               older copy so rule edits reach projects on the next setup

The hooks come from the plugin itself; nothing here touches settings.
"""
import os
import re
import subprocess

from base import MANIFEST, SrunError
from manifest import tidy

HERE = os.path.dirname(os.path.realpath(__file__))
RULE = os.path.join(HERE, "secrets-rule.md")
_SECTION = re.compile(r"^## Secrets[ \t]*\n.*?(?=^## |\Z)", re.M | re.S)


def _repo_root():
    p = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else os.getcwd()


def upsert_rule(path):
    """Put the current Secrets section into a CLAUDE.md. Returns 'added',
    'updated' or None (already current)."""
    with open(RULE) as f:
        rule = f.read().strip() + "\n"
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    m = _SECTION.search(text)
    if m:
        if m.group(0).strip() == rule.strip():
            return None
        rest = text[m.end():]
        new, how = text[:m.start()] + rule + ("\n" + rest if rest else ""), "updated"
    else:
        new, how = (text.rstrip() + "\n\n" if text.strip() else "") + rule, "added"
    with open(path, "w") as f:
        f.write(new)
    return how


def _parse(args):
    if not args:
        return None
    if len(args) == 2 and args[0] == "--store":
        return args[1]
    raise SrunError("usage: srun setup [--store STORE]")


def setup(args):
    root = _repo_root()
    try:
        ns, changed = tidy(root, _parse(args))
    except (SrunError, OSError) as e:
        print(f"srun setup: {e}")
        return 1
    if ns:
        print(f'set "namespace": "{ns}" in {os.path.join(root, MANIFEST)} — '
              f"store ids are {ns}/NAME (gcp: {ns}_NAME).")
    else:
        print(f"updated {MANIFEST}" if changed else f"{MANIFEST} is current")
    how = upsert_rule(os.path.join(root, "CLAUDE.md"))
    print(f"{how} the Secrets section in CLAUDE.md" if how
          else "CLAUDE.md Secrets section is current")
    if changed or how:
        print(f"Commit {MANIFEST} and CLAUDE.md.")
    return 0
