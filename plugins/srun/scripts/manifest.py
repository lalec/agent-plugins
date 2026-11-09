"""The project manifest, .srun.json — the project's secret NAMES and where they
live. Names, stores and ids only; it never holds a value.

  {"namespace": "<project>", "store": "<store>", "secrets": ["NAME", ...]}

`store` is optional: without it each NAME lives in the personal default store
(`srun default`), else the keychain. `secrets` may instead map a NAME to an
override, `{"store": "...", "id": "..."}` or `{"cmd": "..."}`, for the rare
secret kept somewhere else. Older manifests say `backend` for `store`; they load
as is and `srun setup` rewrites them.

`namespace` keeps projects that share a machine or a store apart: a NAME without
an explicit `id` is stored as <namespace>/NAME (gcp: <namespace>_NAME, its ids
reject "/"). Without a namespace the id is NAME. `cmd` entries have no id.
"""
import json
import os
import re
from collections import namedtuple

from base import (DEFAULT_STORE, MANIFEST, SrunError, find_manifest, srun_home,
                  write_atomic)
from stores import RESOLVERS

Manifest = namedtuple("Manifest", "secrets namespace path store",
                      defaults=(None, None, None))
_NAMESPACE = re.compile(r"^[A-Za-z0-9_-]+$")


def _read(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        raise SrunError(f"unreadable manifest: {MANIFEST}")
    if not isinstance(data, dict):
        raise SrunError(f"{MANIFEST} must hold a JSON object")
    return data


def _write(path, data):
    write_atomic(path, json.dumps(data, indent=2) + "\n")


def _entries(raw):
    """NAME -> override dict, from the list form or the (legacy) dict form."""
    if isinstance(raw, list):
        return {n: {} for n in raw if isinstance(n, str)}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for name, e in raw.items():
        e = dict(e) if isinstance(e, dict) else {}
        if "backend" in e:
            e.setdefault("store", e.pop("backend"))
        out[name] = e
    return out


def check_store(store, what):
    if store not in RESOLVERS or store == "cmd":
        raise SrunError(f"unknown store '{store}' for {what}; use one of "
                        + ", ".join(s for s in RESOLVERS if s != "cmd"))
    return store


def load_manifest():
    """The nearest .srun.json, walking up from the working directory."""
    path = find_manifest()
    if not path:
        return Manifest({})
    data = _read(path)
    ns = data.get("namespace")
    if ns is not None and not (isinstance(ns, str) and _NAMESPACE.match(ns)):
        raise SrunError(f'invalid "namespace" in {MANIFEST}: use only '
                        "letters, digits, _ and -")
    store = data.get("store")
    if store is not None:
        check_store(store, MANIFEST)
    return Manifest(_entries(data.get("secrets")), ns, path, store)


# ------------------------------------------------------- personal default -- #
def _config_path():
    return os.path.join(srun_home(), "config.json")


def default_store():
    """The personal default store, or None when never set."""
    try:
        with open(_config_path()) as f:
            store = json.load(f).get("store")
    except (OSError, ValueError, AttributeError):
        return None
    return store if store in RESOLVERS and store != "cmd" else None


def set_default_store(store):
    check_store(store, "srun default")
    os.makedirs(srun_home(), exist_ok=True)
    _write(_config_path(), {"store": store})


# ------------------------------------------------------------------- plan -- #
def store_for(cli_store, manifest):
    """The store for a NAME with no override of its own: the command line, then
    the project, then the personal default, then the keychain."""
    return cli_store or manifest.store or default_store() or DEFAULT_STORE


def plan(name, cli_store, manifest):
    """Decide (store, id) for a NAME. A NAME's own override is authoritative;
    an entry with a `cmd` key is the cmd store, and the command is its id."""
    entry = manifest.secrets.get(name) or {}
    if entry.get("cmd"):
        return "cmd", entry["cmd"]
    store = entry.get("store") or store_for(cli_store, manifest)
    if store == "cmd":
        raise SrunError(f'the cmd store needs a "cmd" entry for {name} in {MANIFEST}')
    check_store(store, name)
    if entry.get("id"):
        return store, entry["id"]
    ns = manifest.namespace
    return store, f"{ns}{'_' if store == 'gcp' else '/'}{name}" if ns else name


def resolve(name, cli_store, manifest):
    store, sid = plan(name, cli_store, manifest)
    return RESOLVERS[store](name, sid)


# ------------------------------------------------------------------ setup -- #
def _compact(data):
    """The manifest in its short form: `backend` read as `store`; a store every
    entry names explicitly hoisted to the project; per-entry stores equal to
    the project's dropped; the plain name list when no override is left."""
    entries = _entries(data.get("secrets", {}))
    store = data.get("store")
    named = [e.get("store") for e in entries.values() if not e.get("cmd")]
    if store is None and named and None not in named and len(set(named)) == 1:
        store = named[0]
    for e in entries.values():
        if store and e.get("store") == store:
            del e["store"]
    secrets = list(entries) if not any(entries.values()) else entries
    head = {k: v for k, v in (("namespace", data.get("namespace")), ("store", store)) if v}
    rest = {k: v for k, v in data.items() if k not in ("namespace", "store", "secrets")}
    return {**head, "secrets": secrets, **rest}


def tidy(root, store=None):
    """Prepare <root>/.srun.json, idempotently: create it when missing, set a
    namespace from the folder name once (never rewritten), set the project
    store when one is given, and rewrite it in the short form. Returns
    (namespace written or None, whether the file changed)."""
    path = os.path.join(root, MANIFEST)
    data = _read(path) if os.path.isfile(path) else {}
    ns = None
    if "namespace" not in data:
        ns = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.basename(root)).strip("-") or "project"
        data = {"namespace": ns, **data}
    if store:
        data["store"] = check_store(store, "srun setup")
    new = _compact(data)
    changed = not os.path.isfile(path) or new != _read(path)
    if changed:
        _write(path, new)
    return ns, changed
