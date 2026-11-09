"""Secret stores — resolve, store and delete values by NAME.

Every resolver returns a bytearray (zeroable) or raises SrunError. Only a
secret's NAME/id ever reaches a subprocess argv; values come back on the child's
stdout pipe, or go in on its stdin, and stay inside the srun process.

Stores: keychain (default, macOS), aws (Secrets Manager), gcp (Secret Manager),
the password managers in managers.py (1password, dashlane, lastpass), and cmd —
any command that prints the value, declared per NAME in .srun.json.
"""
import json
import os
import subprocess

import managers
from base import (CURRENT_NAMES, DEFAULT_STORE, MANIFEST, SrunError,  # noqa: F401
                  find_manifest, strip_nl, zero)

SERVICE = "srun"        # dedicated Keychain generic-password service


# --------------------------------------------------------------- resolvers -- #
def _resolve_keychain(name, sid):
    p = subprocess.run(
        ["security", "find-generic-password", "-s", SERVICE, "-a", sid, "-w"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        raise SrunError(f"not found in keychain: {name}")
    return bytearray(strip_nl(p.stdout))    # `security -w` appends one newline


def _resolve_aws(name, sid):
    p = subprocess.run(
        ["aws", "secretsmanager", "get-secret-value", "--secret-id", sid,
         "--output", "json"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        raise SrunError(f"aws resolve failed: {name}")
    try:
        s = json.loads(p.stdout).get("SecretString")
    except ValueError:
        raise SrunError(f"aws returned unparseable payload: {name}")
    if s is None:
        raise SrunError(f"aws secret has no SecretString: {name}")
    return bytearray(s.encode("utf-8"))


def _resolve_gcp(name, sid):
    p = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", "--secret", sid],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        raise SrunError(f"gcp resolve failed: {name}")
    return bytearray(p.stdout)     # gcloud emits the exact payload, no newline


def _resolve_cmd(name, sid):
    # The command comes from the committed manifest — the same trust as a
    # package.json script. It runs from the manifest's directory so relative
    # paths (an env file) work; stderr is discarded so an error cannot echo it.
    path = find_manifest()
    p = subprocess.run(["sh", "-c", sid],
                       cwd=os.path.dirname(path) if path else None,
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    out = strip_nl(p.stdout)
    if p.returncode != 0 or not out:
        raise SrunError(f"command printed no value: {name}")
    return bytearray(out)


RESOLVERS = {
    "keychain": _resolve_keychain,
    "aws": _resolve_aws,
    "gcp": _resolve_gcp,
    **managers.RESOLVERS,
    "cmd": _resolve_cmd,
}

# Each value goes in on stdin; `security -w` with no value prompts twice, so
# it gets the value and its retype. Special chars survive (unlike `security -i`).
# `security` reads those prompts from the terminal when it has one, so store()
# detaches it from the terminal to make it read stdin.
_WRITE = {
    "keychain": (lambda sid: ["security", "add-generic-password", "-U", "-s",
                              SERVICE, "-a", sid, "-w"],
                 lambda vb: bytes(vb) + b"\n" + bytes(vb) + b"\n"),
    "aws": (lambda sid: ["aws", "secretsmanager", "put-secret-value", "--secret-id",
                         sid, "--secret-string", "file:///dev/stdin"], bytes),
    "gcp": (lambda sid: ["gcloud", "secrets", "versions", "add", sid,
                         "--data-file=-"], bytes),
    **managers.WRITE,
}
_DELETE = {
    "keychain": lambda sid: ["security", "delete-generic-password", "-s", SERVICE,
                             "-a", sid],
    "aws": lambda sid: ["aws", "secretsmanager", "delete-secret", "--secret-id", sid],
    "gcp": lambda sid: ["gcloud", "secrets", "delete", sid, "--quiet"],
    **managers.DELETE,
}


def writable(store):
    return store in _WRITE


def not_writable(store, name, sid):
    if store == "cmd":
        return SrunError(f"{name} is read by a command in {MANIFEST}; store or "
                         "remove it in that secret manager, not here")
    return SrunError(f"{name} lives in {managers.LABEL[store]}: "
                     f"{managers.WHERE[store].format(sid=sid)}")


# -------------------------------------------------------------- store/delete -- #
def store(backend, name, sid, vb):
    """Write a value without it ever appearing in any process argv."""
    if backend not in _WRITE:
        if backend not in RESOLVERS:
            raise SrunError(f"unknown store: {backend}")
        raise not_writable(backend, name, sid)
    managers.READY.get(backend, lambda n: None)(name)
    argv, blob = _WRITE[backend]
    p = subprocess.run(argv(sid), input=blob(vb), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,
                       start_new_session=backend == "keychain")
    if p.returncode != 0:
        hint = f" (does secret '{sid}' exist?)" if backend in ("aws", "gcp") else ""
        raise SrunError(f"{backend} store failed{hint}: {name}")


def delete(backend, name, sid):
    if backend not in _DELETE:
        if backend not in RESOLVERS:
            raise SrunError(f"unknown store: {backend}")
        raise not_writable(backend, name, sid)
    managers.READY.get(backend, lambda n: None)(name)
    p = subprocess.run(_DELETE[backend](sid), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        raise SrunError(f"delete failed: {name}")
