"""List stored secret NAMES — never values.

The keychain is listed from a local names-only index so a steady-state `ls`
never dumps the keychain. NAMES are not secret (the manifest commits them), so a
plaintext index is consistent with the threat model; values are never written.
"""
import json
import os
import subprocess

from stores import SERVICE, SecretrunError


def _blob_val(line):
    # line like: "acct"<blob>="NAME"   (or =<NULL>)
    marker = '="'
    i = line.find(marker)
    if i < 0 or not line.endswith('"'):
        return None
    return line[i + len(marker):-1]


def keychain_dump_names():
    """Enumerate secretrun's stored NAMES via a single `security dump-keychain`.
    Endpoint tools flag bulk keychain enumeration, so this runs only on the
    first-run index bootstrap and on an explicit `secretrun sync`."""
    p = subprocess.run(["security", "dump-keychain"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    names, acct = [], None
    for raw in p.stdout.decode("utf-8", "replace").splitlines():
        s = raw.strip()
        if s.startswith('"acct"<blob>='):
            acct = _blob_val(s)
        elif s == '"svce"<blob>="%s"' % SERVICE and acct:
            names.append(acct)
    return sorted(set(names))


def index_path():
    home = os.environ.get("SECRETRUN_HOME") or os.path.expanduser("~/.secretrun")
    return os.path.join(home, "keychain-names.json")


def index_load():
    """The sorted name list, or None if no index exists yet (=> bootstrap)."""
    try:
        with open(index_path()) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None            # missing or corrupt — treat as unbootstrapped
    return sorted(set(data)) if isinstance(data, list) else None


def index_save(names):
    path = index_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sorted(set(names)), f, indent=2)
        f.write("\n")
    os.replace(tmp, path)       # atomic: never leave a half-written index


def index_update(name, add):
    """Add or remove one name — only once the index is bootstrapped; until then
    the next `ls`/`sync` picks the change up from the keychain."""
    names = index_load()
    if names is None:
        return
    if add and name not in names:
        index_save(names + [name])
    elif not add and name in names:
        index_save([n for n in names if n != name])


def list_names(backend):
    if backend == "keychain":
        names = index_load()
        if names is None:               # first run — bootstrap once, then stay quiet
            names = keychain_dump_names()
            index_save(names)
        return sorted(set(names))
    if backend == "aws":
        cmd = ["aws", "secretsmanager", "list-secrets",
               "--query", "SecretList[].Name", "--output", "text"]
    elif backend == "gcp":
        cmd = ["gcloud", "secrets", "list", "--format", "value(name)"]
    else:
        raise SecretrunError(f"cannot list backend: {backend}")
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return sorted(p.stdout.decode().split()) if p.returncode == 0 else []
