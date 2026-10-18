"""`secretrun add | rm | ls | sync | check | migrate` — manage stored values by NAME.

Values are typed by the user (prompt.py) and go straight to the store; `check`
resolves each value only to zero it unread; `migrate` moves one store entry to
another inside this process. Output names the NAME, store and id — never a value.
"""
import sys

from names import index_load, index_save, index_update, keychain_dump_names, list_names
from prompt import read_hidden
from manifest import load_manifest, plan, resolve
from stores import (CURRENT_NAMES, DEFAULT_BACKEND, MANIFEST, RESOLVERS,
                    SecretrunError, delete, not_writable, store, zero)


def _parse_name_backend(rest, name_optional=False):
    backend = name = None
    it = iter(rest)
    for t in it:
        if t in ("-b", "--backend"):
            backend = next(it, None)
            if backend is None:
                raise SecretrunError("-b needs a backend name")
        elif t.startswith("-"):
            raise SecretrunError(f"unknown option: {t}")
        elif name is None:
            name = t
        else:
            raise SecretrunError("unexpected extra argument (secrets are added "
                                 "interactively, never on the command line)")
    if name is None and not name_optional:
        raise SecretrunError("a secret NAME is required")
    return name, backend


def cmd_add(rest):
    name, cli_backend = _parse_name_backend(rest)
    CURRENT_NAMES[:] = [name]
    backend, sid = plan(name, cli_backend, load_manifest())
    if backend == "cmd":
        raise not_writable(name)
    vb = read_hidden(name)
    try:
        store(backend, name, sid, vb)
    finally:
        zero(vb)
    if backend == "keychain":
        index_update(sid, add=True)
    print(f"stored {name} in {backend} as {sid}")
    return 0


def cmd_rm(rest):
    name, cli_backend = _parse_name_backend(rest)
    CURRENT_NAMES[:] = [name]
    backend, sid = plan(name, cli_backend, load_manifest())
    delete(backend, name, sid)
    if backend == "keychain":
        index_update(sid, add=False)
    print(f"removed {name} from {backend} ({sid})")
    return 0


def cmd_ls(rest):
    _, backend = _parse_name_backend(rest, name_optional=True)
    backend = backend or DEFAULT_BACKEND
    if backend == "keychain" and index_load() is None:
        sys.stderr.write(
            "secretrun: first run — indexing keychain names once so future `ls` "
            "won't dump the keychain. Run `secretrun sync` if you store secrets "
            "outside secretrun.\n")
    for n in list_names(backend):
        print(n)
    return 0


def cmd_sync(rest):
    _, backend = _parse_name_backend(rest, name_optional=True)
    if (backend or DEFAULT_BACKEND) != "keychain":
        raise SecretrunError("sync applies only to the keychain backend")
    names = keychain_dump_names()
    index_save(names)
    print("synced %d keychain name(s) into the local index" % len(names))
    return 0


def cmd_check(rest):
    """OK/MISS per NAME — the named ones, else every manifest entry. Prints
    names and stores only; a resolved value is zeroed unread."""
    manifest = load_manifest()
    names = _names(rest, manifest)
    if not names:
        print(f"no {MANIFEST} in this project" if not manifest.path
              else f"no secrets declared in {MANIFEST}")
        return 0
    missing = 0
    for name in names:
        b, sid = plan(name, None, manifest)
        where = b if b == "cmd" else f"{b} {sid}"
        CURRENT_NAMES[:] = [name]
        try:
            zero(resolve(name, None, manifest))
            print(f"OK    {name}  ({where})")
        except SecretrunError:
            missing += 1
            print(f"MISS  {name}  ({where})")
    return 1 if missing else 0


def _names(rest, manifest):
    bad = [t for t in rest if t.startswith("-")]
    if bad:
        raise SecretrunError(f"unknown option: {bad[0]}")
    return rest or list(manifest.secrets)


def _move(name, manifest):
    """(status, detail) for moving one keychain value from the bare NAME to its
    namespaced id: resolve old, store new, read new back, delete old."""
    backend, sid = plan(name, None, manifest)
    if backend == "cmd":
        return "skipped", "cmd entry: nothing is stored here"
    if backend != "keychain":     # moving needs create/delete rights there
        return "skipped", f"{backend} store: move it in {backend} itself"
    if (manifest.secrets.get(name) or {}).get("id"):
        return "skipped", f"explicit id {sid}"
    get = RESOLVERS["keychain"]
    try:
        zero(get(name, sid))
        return "kept", f"already under {sid}"     # never clobber a namespaced value
    except SecretrunError:
        pass
    try:
        old = get(name, name)
    except SecretrunError:
        return "not stored", ""
    try:
        store("keychain", name, sid, old)
        new = get(name, sid)
        same = new == old
        zero(new)
    finally:
        zero(old)
    if not same:
        raise SecretrunError(f"moved value did not read back; bare entry kept: {name}")
    delete("keychain", name, name)
    index_update(name, add=False)
    index_update(sid, add=True)
    return "moved", f"-> {sid}"


def cmd_migrate(rest):
    """Move keychain values stored under the bare NAME to <namespace>/NAME, for
    the named NAMEs or every manifest entry."""
    manifest = load_manifest()
    if not manifest.namespace:
        raise SecretrunError(f'no "namespace" in {MANIFEST}; nothing to move')
    for name in _names(rest, manifest):
        CURRENT_NAMES[:] = [name]
        status, detail = _move(name, manifest)
        print(f"{status:<10}  {name}  {detail}".rstrip())
    return 0


COMMANDS = {"add": cmd_add, "rm": cmd_rm, "ls": cmd_ls, "sync": cmd_sync,
            "check": cmd_check, "migrate": cmd_migrate}
