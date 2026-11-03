"""Password-manager stores — 1Password (`op`), Dashlane (`dcli`), LastPass (`lpass`).

One item per secret, titled with its store id (`myapp/API_KEY`), the value in
the item's password field: the item type every manager has. Each read matches
the title exactly in this process, because the CLIs match loosely (Dashlane by
substring) or print the wrong thing on duplicates (LastPass exits 0 with a
"Multiple matches" listing). Only titles and ids reach argv; values arrive on
stdout or go in on stdin. stdin is closed on every read, so a locked manager
fails instead of waiting for a prompt nobody sees.

Writes: LastPass only (`lpass edit --non-interactive` reads the value on stdin
and creates the item when missing). Dashlane's CLI cannot write, and 1Password's
update-from-stdin is not documented well enough to trust with a value — create
those items in the app.
"""
import json
import subprocess

from base import SrunError, strip_nl

LABEL = {"1password": "1Password", "dashlane": "Dashlane", "lastpass": "LastPass"}
WHERE = {
    "1password": "create a Password item titled {sid} in the 1Password app; srun "
                 "reads its password field",
    "dashlane": "create a login titled {sid} in the Dashlane app; srun reads its "
                "password (Dashlane's CLI cannot write)",
}


def _run(store, argv, name, stdin=subprocess.DEVNULL):
    try:
        return subprocess.run(argv, stdin=stdin, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise SrunError(f"{LABEL[store]} CLI `{argv[0]}` is not installed: {name}")


def _json(store, p, name):
    if p.returncode != 0:
        raise SrunError(f"{LABEL[store]} lookup failed (signed in?): {name}")
    try:
        data = json.loads(p.stdout)
    except ValueError:
        raise SrunError(f"{LABEL[store]} returned unparseable output: {name}")
    return data if isinstance(data, list) else []


def _one(store, items, key, sid, name):
    hits = [i for i in items if isinstance(i, dict) and i.get(key) == sid]
    if not hits:
        raise SrunError(f"not found in {LABEL[store]} (no item titled {sid}): {name}")
    if len(hits) > 1:
        raise SrunError(f"{len(hits)} items titled {sid} in {LABEL[store]}; keep one: {name}")
    return hits[0]


# --------------------------------------------------------------- 1Password -- #
def _resolve_1password(name, sid):
    # `op read` cannot name an item whose title holds "/", so find it in the
    # value-free item list and read it by vault and item id.
    item = _one("1password", _json("1password", _run(
        "1password", ["op", "item", "list", "--format", "json"], name), name),
        "title", sid, name)
    vault = (item.get("vault") or {}).get("id")
    p = _run("1password", ["op", "read", f"op://{vault}/{item.get('id')}/password"], name)
    out = strip_nl(p.stdout)
    if p.returncode != 0 or not vault or not out:
        raise SrunError(f"1Password item {sid} has no password field: {name}")
    return bytearray(out)


# ---------------------------------------------------------------- Dashlane -- #
def _resolve_dashlane(name, sid):
    # `-o json` always: the default output is the clipboard.
    item = _one("dashlane", _json("dashlane", _run(
        "dashlane", ["dcli", "password", "-o", "json", f"title={sid}"], name), name),
        "title", sid, name)
    if not item.get("password"):
        raise SrunError(f"Dashlane login {sid} has no password: {name}")
    return bytearray(item["password"].encode("utf-8"))


# ---------------------------------------------------------------- LastPass -- #
def _lastpass_ready(name):
    # Any other lpass command prompts for the master password once its agent
    # has expired — and could read that from the stdin carrying a value.
    if _run("lastpass", ["lpass", "status", "-q"], name).returncode != 0:
        raise SrunError(f"LastPass is locked: run `lpass login` in your terminal: {name}")


def _resolve_lastpass(name, sid):
    _lastpass_ready(name)
    p = _run("lastpass", ["lpass", "show", "--json", "--expand-multi", sid], name)
    if p.returncode != 0:              # signed in (checked above), so: no such item
        raise SrunError(f"not found in LastPass (no item {sid}): {name}")
    item = _one("lastpass", _json("lastpass", p, name), "fullname", sid, name)
    if not item.get("password"):
        raise SrunError(f"LastPass item {sid} has no password: {name}")
    return bytearray(item["password"].encode("utf-8"))


RESOLVERS = {"1password": _resolve_1password, "dashlane": _resolve_dashlane,
             "lastpass": _resolve_lastpass}
# `lpass edit` creates the item when missing; `lpass add` would duplicate it.
WRITE = {"lastpass": (lambda sid: ["lpass", "edit", "--non-interactive", "--password",
                                   sid], bytes)}
DELETE = {"lastpass": lambda sid: ["lpass", "rm", sid]}
READY = {"lastpass": _lastpass_ready}
