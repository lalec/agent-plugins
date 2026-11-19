"""`srun import FILE NAME... [-s STORE] [--remove]` — move secrets out of a
dotenv file into the project's store, never printing a value.

Each NAME is read from FILE, stored under its usual id, read back and compared,
and listed in .srun.json. A value already stored under that id is kept when it
matches and refused when it differs, so nothing is overwritten. Only when every
NAME is stored does `--remove` delete their lines from FILE; the rest of the
file — public settings, comments — stays. Output names the NAME, store and id.

The parser follows python-dotenv for the forms a secret takes: `KEY=value`,
`export KEY=value`, single or double quotes, a ` #` comment after an unquoted
value. A value it cannot read for certain — one spanning lines, holding
`${...}`, or a NAME listed twice — is refused: store it with `srun add`.
"""
import os
import re

from base import CURRENT_NAMES, MANIFEST, SrunError, find_manifest, write_atomic, zero
from manifest import add_names, load_manifest, plan
from names import index_update
from stores import RESOLVERS, not_writable, store, writable

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
_DOUBLE = re.compile(r'^"((?:[^"\\]|\\.)*)"\s*(?:#.*)?$')
_SINGLE = re.compile(r"^'([^']*)'\s*(?:#.*)?$")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "'": "'"}


def _value(name, raw):
    m = _DOUBLE.match(raw)
    if m:
        val = re.sub(r"\\(.)", lambda e: _ESCAPES.get(e.group(1), e.group(0)), m.group(1))
        if "${" in m.group(1):
            raise SrunError(f"{name} uses ${{...}} expansion; store it with `srun add {name}`")
        return val
    m = _SINGLE.match(raw)
    if m:
        return m.group(1)
    if raw[:1] in ("'", '"'):
        raise SrunError(f"{name} spans lines or has an unclosed quote; "
                        f"store it with `srun add {name}`")
    val = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
    if "${" in val:
        raise SrunError(f"{name} uses ${{...}} expansion; store it with `srun add {name}`")
    return val


def read_values(path, wanted):
    """NAME -> (bytearray value, line index) for each wanted NAME in a dotenv file."""
    with open(path, newline="") as f:
        lines = f.read().splitlines(keepends=True)
    found = {}
    try:
        for i, line in enumerate(lines):
            m = _LINE.match(line)
            if not m or m.group(1) not in wanted:
                continue
            name = m.group(1)
            if name in found:
                raise SrunError(f"{name} is set more than once in {path}; keep one line")
            val = _value(name, m.group(2))
            if not val:
                raise SrunError(f"{name} is empty in {path}; nothing to store")
            found[name] = (bytearray(val.encode("utf-8")), i)
        missing = [n for n in wanted if n not in found]
        if missing:
            raise SrunError(f"not in {path}: {', '.join(missing)}")
    except SrunError:
        for v, _ in found.values():
            zero(v)
        raise
    return found, lines


def _put(name, cli_store, manifest, value):
    """Store one value unless an equal one is there; read it back. -> status."""
    backend, sid = plan(name, cli_store, manifest)
    if not writable(backend):
        raise not_writable(backend, name, sid)
    try:
        old = RESOLVERS[backend](name, sid)
    except SrunError:
        old = None
    if old is not None:
        same = old == value
        zero(old)
        if not same:
            raise SrunError(f"{name} already holds a different value in {backend} as "
                            f"{sid}; nothing changed. If the file's value is the right "
                            f"one, run `srun rm {name}`, then import again")
        return "kept", backend, sid
    store(backend, name, sid, value)
    back = RESOLVERS[backend](name, sid)
    ok = back == value
    zero(back)
    if not ok:
        raise SrunError(f"{name} did not read back from {backend}; the file is unchanged")
    if backend == "keychain":
        index_update(sid, add=True)
    return "stored", backend, sid


def _parse(rest):
    path, names, cli_store, remove = None, [], None, False
    it = iter(rest)
    for t in it:
        if t in ("-s", "--store"):
            cli_store = next(it, None)
            if cli_store is None:
                raise SrunError("-s needs a store name")
        elif t == "--remove":
            remove = True
        elif t.startswith("-"):
            raise SrunError(f"unknown option: {t}")
        elif path is None:
            path = t
        else:
            names.append(t)
    if not path or not names:
        raise SrunError("usage: srun import FILE NAME... [-s STORE] [--remove]")
    return path, names, cli_store, remove


def cmd_import(rest):
    path, names, cli_store, remove = _parse(rest)
    if not find_manifest():
        raise SrunError(f"no {MANIFEST} in this project; run `srun setup` first so "
                        "the values get the project's own ids")
    if remove and os.path.islink(path):
        raise SrunError(f"refusing --remove on {path}: it is a link")
    found, lines = read_values(path, names)
    manifest = load_manifest()
    try:
        for name in names:
            CURRENT_NAMES[:] = [name]
            status, backend, sid = _put(name, cli_store, manifest, found[name][0])
            print(f"{status:<7} {name}  ({backend} {sid})")
    finally:
        for v, _ in found.values():
            zero(v)
    added = add_names(names)
    if added:
        print(f"listed in {MANIFEST}: {', '.join(added)}")
    if remove:
        drop = {i for _, i in found.values()}
        write_atomic(path, "".join(ln for i, ln in enumerate(lines) if i not in drop))
        print(f"removed {len(drop)} line(s) from {path}")
    return 0
