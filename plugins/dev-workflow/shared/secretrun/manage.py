"""`secretrun add | rm | ls | sync | check` — manage stored values by NAME.

Values are typed by the user (prompt.py) and go straight to the store; `check`
resolves each value only to zero it unread. Nothing here prints a value.
"""
import sys

from names import index_load, index_save, index_update, keychain_dump_names, list_names
from prompt import read_hidden
from stores import (CURRENT_NAMES, DEFAULT_BACKEND, SecretrunError, delete,
                    load_manifest, not_writable, plan, resolve, store, zero)


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
        index_update(name, add=True)
    print(f"stored {name} in {backend}")
    return 0


def cmd_rm(rest):
    name, cli_backend = _parse_name_backend(rest)
    CURRENT_NAMES[:] = [name]
    backend, sid = plan(name, cli_backend, load_manifest())
    delete(backend, name, sid)
    if backend == "keychain":
        index_update(name, add=False)
    print(f"removed {name} from {backend}")
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
    names = [t for t in rest if not t.startswith("-")] or list(manifest)
    if not names:
        print("no .secretrun.json manifest found in this project")
        return 0
    missing = 0
    for name in names:
        b, _ = plan(name, None, manifest)
        CURRENT_NAMES[:] = [name]
        try:
            zero(resolve(name, None, manifest))
            print(f"OK    {name}  ({b})")
        except SecretrunError:
            missing += 1
            print(f"MISS  {name}  ({b})")
    return 1 if missing else 0


COMMANDS = {"add": cmd_add, "rm": cmd_rm, "ls": cmd_ls, "sync": cmd_sync,
            "check": cmd_check}
