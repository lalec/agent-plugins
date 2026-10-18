"""Secret stores — resolve, store, list and delete values by NAME.

Every resolver returns a bytearray (zeroable) or raises SecretrunError. Only a
secret's NAME/id ever reaches a subprocess argv; values come back on the child's
stdout pipe, which stays inside the secretrun process.

Stores: keychain (default, macOS), aws (Secrets Manager), gcp (Secret Manager),
and cmd — any command that prints the value (an env file, AWS Parameter Store,
1Password, Vault, Doppler, ...), declared per NAME in .secretrun.json.
"""
import json
import os
import subprocess

SERVICE = "secretrun"        # dedicated Keychain generic-password service
DEFAULT_BACKEND = "keychain"
MANIFEST = ".secretrun.json"


# Names of the secret(s) in flight — the ONLY value-adjacent detail the scrubbing
# excepthook is allowed to print.
CURRENT_NAMES = []


class SecretrunError(Exception):
    """Carries a name-only, value-free message that is safe to print."""


def zero(buf):
    if isinstance(buf, bytearray):
        for i in range(len(buf)):
            buf[i] = 0


def _strip_nl(out):
    return out[:-1] if out.endswith(b"\n") else out


# --------------------------------------------------------------- resolvers -- #
def _resolve_keychain(name, sid):
    p = subprocess.run(
        ["security", "find-generic-password", "-s", SERVICE, "-a", sid, "-w"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        raise SecretrunError(f"not found in keychain: {name}")
    return bytearray(_strip_nl(p.stdout))   # `security -w` appends one newline


def _resolve_aws(name, sid):
    p = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value", "--secret-id", sid,
         "--output", "json"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        raise SecretrunError(f"aws resolve failed: {name}")
    try:
        s = json.loads(p.stdout).get("SecretString")
    except ValueError:
        raise SecretrunError(f"aws returned unparseable payload: {name}")
    if s is None:
        raise SecretrunError(f"aws secret has no SecretString: {name}")
    return bytearray(s.encode("utf-8"))


def _resolve_gcp(name, sid):
    p = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", "--secret", sid],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        raise SecretrunError(f"gcp resolve failed: {name}")
    return bytearray(p.stdout)     # gcloud emits the exact payload, no newline


def _resolve_cmd(name, sid):
    # The command comes from the committed manifest — the same trust as a
    # package.json script. It runs from the manifest's directory so relative
    # paths (an env file) work; stderr is discarded so an error cannot echo it.
    path = find_manifest()
    p = subprocess.run(["sh", "-c", sid],
                       cwd=os.path.dirname(path) if path else None,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    out = _strip_nl(p.stdout)
    if p.returncode != 0 or not out:
        raise SecretrunError(f"command printed no value: {name}")
    return bytearray(out)


RESOLVERS = {
    "keychain": _resolve_keychain,
    "aws": _resolve_aws,
    "gcp": _resolve_gcp,
    "cmd": _resolve_cmd,
}


def not_writable(name):
    return SecretrunError(
        f"{name} is read by a command in {MANIFEST}; store or remove it in that "
        "secret manager, not here")


# -------------------------------------------------------------- store/delete -- #
def store(backend, name, sid, vb):
    """Write a value without it ever appearing in any process argv."""
    if backend == "keychain":
        # `-w` (no value) reads the password from stdin, prompting twice; feed
        # the value + retype. Special chars survive (unlike `security -i`).
        cmd = ["security", "add-generic-password", "-U", "-s", SERVICE, "-a", sid, "-w"]
        blob = bytes(vb) + b"\n" + bytes(vb) + b"\n"
    elif backend == "aws":
        cmd = ["aws", "secretsmanager", "put-secret-value", "--secret-id", sid,
               "--secret-string", "file:///dev/stdin"]
        blob = bytes(vb)
    elif backend == "gcp":
        cmd = ["gcloud", "secrets", "versions", "add", sid, "--data-file=-"]
        blob = bytes(vb)
    elif backend == "cmd":
        raise not_writable(name)
    else:
        raise SecretrunError(f"unknown backend: {backend}")
    p = subprocess.run(cmd, input=blob, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        hint = "" if backend == "keychain" else f" (does secret '{sid}' exist?)"
        raise SecretrunError(f"{backend} store failed{hint}: {name}")


def delete(backend, name, sid):
    if backend == "keychain":
        cmd = ["security", "delete-generic-password", "-s", SERVICE, "-a", sid]
    elif backend == "aws":
        cmd = ["aws", "secretsmanager", "delete-secret", "--secret-id", sid]
    elif backend == "gcp":
        cmd = ["gcloud", "secrets", "delete", sid, "--quiet"]
    elif backend == "cmd":
        raise not_writable(name)
    else:
        raise SecretrunError(f"unknown backend: {backend}")
    p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        raise SecretrunError(f"delete failed: {name}")


# ---------------------------------------------------------------- manifest -- #
def find_manifest(start=None):
    d = os.path.abspath(start or os.getcwd())
    while True:
        cand = os.path.join(d, MANIFEST)
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_manifest():
    """{NAME: entry} from the nearest .secretrun.json — names and stores only,
    never values."""
    path = find_manifest()
    if not path:
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        raise SecretrunError(f"unreadable manifest: {MANIFEST}")
    secrets = data.get("secrets", {}) if isinstance(data, dict) else {}
    return secrets if isinstance(secrets, dict) else {}


def plan(name, cli_backend, manifest):
    """Decide (backend, id) for a NAME. The manifest entry is authoritative; `-b`
    only sets the store for names the manifest doesn't mention. An entry with a
    `cmd` key is the cmd store, and the command is its id."""
    entry = manifest.get(name) or {}
    if entry.get("cmd"):
        return "cmd", entry["cmd"]
    backend = entry.get("backend") or cli_backend or DEFAULT_BACKEND
    sid = entry.get("id") or name
    if backend not in RESOLVERS:
        raise SecretrunError(f"unknown backend '{backend}' for {name}")
    return backend, sid


def resolve(name, cli_backend, manifest):
    backend, sid = plan(name, cli_backend, manifest)
    return RESOLVERS[backend](name, sid)
