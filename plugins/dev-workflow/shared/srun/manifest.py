"""The project manifest, .srun.json — which store holds each NAME, under
which id. Names, stores and ids only; it never holds a value.

  {"namespace": "<project>",
   "secrets": {"NAME": {"backend": "...", "id": "..."} | {"cmd": "..."}}}

`namespace` keeps projects that share a machine, AWS account or GCP project
apart: an entry without an explicit `id` is stored as <namespace>/NAME
(keychain, aws) or <namespace>_NAME (gcp ids reject "/"). An explicit `id`
always wins — that is how a secret shared on purpose opts out. Without a
namespace the id is NAME. `cmd` entries have no id to namespace.
"""
import json
import os
import re
from collections import namedtuple

from stores import DEFAULT_BACKEND, MANIFEST, RESOLVERS, SrunError, find_manifest

Manifest = namedtuple("Manifest", "secrets namespace path", defaults=(None, None))
_NAMESPACE = re.compile(r"^[A-Za-z0-9_-]+$")
_SEP = {"keychain": "/", "aws": "/", "gcp": "_"}


def _read(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        raise SrunError(f"unreadable manifest: {MANIFEST}")
    if not isinstance(data, dict):
        raise SrunError(f"{MANIFEST} must hold a JSON object")
    return data


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
    secrets = data.get("secrets", {})
    return Manifest(secrets if isinstance(secrets, dict) else {}, ns, path)


def plan(name, cli_backend, manifest):
    """Decide (backend, id) for a NAME. The manifest entry is authoritative; `-b`
    only sets the store for names the manifest doesn't mention. An entry with a
    `cmd` key is the cmd store, and the command is its id."""
    entry = manifest.secrets.get(name) or {}
    if entry.get("cmd"):
        return "cmd", entry["cmd"]
    backend = entry.get("backend") or cli_backend or DEFAULT_BACKEND
    if backend == "cmd":
        raise SrunError(f'the cmd store needs a "cmd" entry for {name} in {MANIFEST}')
    if backend not in RESOLVERS:
        raise SrunError(f"unknown backend '{backend}' for {name}")
    if entry.get("id"):
        return backend, entry["id"]
    ns = manifest.namespace
    return backend, f"{ns}{_SEP[backend]}{name}" if ns else name


def resolve(name, cli_backend, manifest):
    backend, sid = plan(name, cli_backend, manifest)
    return RESOLVERS[backend](name, sid)


def ensure_namespace(root):
    """Give <root>/.srun.json a namespace from the folder name, once —
    creating the manifest when there is none. Returns the namespace written, or
    None when one is already set: an existing namespace is never rewritten."""
    path = os.path.join(root, MANIFEST)
    data = _read(path) if os.path.isfile(path) else {"secrets": {}}
    if "namespace" in data:
        return None
    ns = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.basename(root)).strip("-") or "project"
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"namespace": ns, **data}, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return ns
