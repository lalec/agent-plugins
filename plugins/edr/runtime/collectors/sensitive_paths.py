"""Sensitive-path file collector.

Hashes a curated set of high-value files (SSH, shell rcs, cred dirs, system
configs) and emits one Evidence per file. Diff naturally surfaces additions,
modifications, and deletions. Also emits crontab + at queue evidence.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from collectors._base import Collector, CollectorContext, Evidence
from collectors._util import run_cmd, sha256_file

SHELL_RCS = [
    "~/.zshrc", "~/.zprofile", "~/.zshenv",
    "~/.bashrc", "~/.bash_profile", "~/.profile",
]
SSH_FILES = ["~/.ssh/authorized_keys", "~/.ssh/known_hosts", "~/.ssh/config", "~/.ssh/allowed_signers"]
# Curated high-signal credential files only — NOT blanket recursion (gcloud cache is 70MB+).
# Long-lived credentials only. Short-lived token caches (gcloud access_tokens.db,
# azure accessTokens.json) are rewritten on every CLI call and would alert daily;
# a stolen or swapped identity shows up in the long-term store, which stays listed.
CRED_FILES = [
    "~/.aws/credentials", "~/.aws/config",
    "~/.kube/config",
    "~/.gcloud/application_default_credentials.json",
    "~/.config/gcloud/application_default_credentials.json",
    "~/.config/gcloud/credentials.db",
    "~/.config/gcloud/active_config",
    "~/.azure/azureProfile.json",
    "~/.azure/credentials",
    "~/.docker/config.json",
    "~/.gnupg/pubring.kbx", "~/.gnupg/pubring.gpg",
    "~/.netrc", "~/.npmrc", "~/.pypirc", "~/.envrc",
]
# Cred subdirs where a *manifest* (not contents) is the right granularity —
# detects new private keys without ever reading the secret material.
CRED_DIR_MANIFESTS = [
    "~/.gnupg/private-keys-v1.d",
    "~/.gcloud/legacy_credentials",
    "~/.config/gcloud/legacy_credentials",
]
SYSTEM_CONFIGS = ["/etc/hosts", "/etc/sudoers"]
SUDOERS_DIR = "/etc/sudoers.d"

CURL_PIPE_SH = re.compile(r"(curl|wget)[^\n|]*\|\s*(sh|bash|zsh)|eval\s+\"\$\(curl", re.IGNORECASE)


class SensitivePathsCollector(Collector):
    name = "sensitive_paths"
    tier = "T"
    maturity = "stable"
    version = 1
    mitre = ["T1098.004", "T1546.004", "T1574", "T1053.003"]
    # mtime changes on touch; sha256 is the real identity.
    volatile_attrs = ["mtime"]

    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        out: list[Evidence] = []

        for raw in SHELL_RCS:
            ev = self._hash_file(raw, kind="shell_rc")
            if ev:
                # Annotate if curl|sh / eval pattern is present in the body.
                p = Path(os.path.expanduser(raw))
                try:
                    body = p.read_text(errors="replace")
                except OSError:
                    body = ""
                ev.attrs["has_curl_pipe_sh"] = bool(CURL_PIPE_SH.search(body))
                ev.attrs["content"] = body[-2000:] if body else ""  # last 2KB for diff context
                out.append(ev)

        for raw in SSH_FILES:
            ev = self._hash_file(raw, kind="ssh_file")
            if ev:
                p = Path(os.path.expanduser(raw))
                try:
                    line_count = sum(1 for _ in p.open())
                except OSError:
                    line_count = 0
                ev.attrs["line_count"] = line_count
                out.append(ev)

        for raw in SYSTEM_CONFIGS:
            ev = self._hash_file(raw, kind="system_config")
            if ev:
                out.append(ev)

        for raw in CRED_FILES:
            ev = self._hash_file(raw, kind="cred_file")
            if ev:
                out.append(ev)

        for raw in CRED_DIR_MANIFESTS:
            ev = self._dir_manifest(raw)
            if ev:
                out.append(ev)

        # /etc/sudoers.d/* enumeration
        sd = Path(SUDOERS_DIR)
        if sd.is_dir():
            try:
                for child in sorted(sd.iterdir()):
                    if child.is_file():
                        ev = self._hash_file(str(child), kind="sudoers_d")
                        if ev:
                            out.append(ev)
            except PermissionError:
                pass

        out.extend(self._crontab())
        out.extend(self._at_queue())
        return out

    def _hash_file(self, raw_path: str, kind: str) -> Evidence | None:
        path = Path(os.path.expanduser(raw_path))
        if not path.is_file():
            return None
        digest = sha256_file(path)
        try:
            mtime = int(path.stat().st_mtime)
            size = path.stat().st_size
        except OSError:
            mtime = size = 0
        return Evidence(
            collector=self.name,
            kind=kind,
            key=str(path),
            attrs={
                "path": str(path),
                "sha256": digest,
                "mtime": mtime,
                "size": size,
            },
        )

    def _dir_manifest(self, raw_dir: str) -> Evidence | None:
        """Manifest of (filename, mtime, size) — never reads file contents.

        Detects new keys / config additions in cred subdirs without leaking secret material.
        """
        d = Path(os.path.expanduser(raw_dir))
        if not d.is_dir():
            return None
        entries: list[dict[str, Any]] = []
        try:
            for child in sorted(d.iterdir()):
                if not child.is_file() or child.name.startswith("."):
                    continue
                try:
                    st = child.stat()
                    entries.append({"name": child.name, "size": st.st_size, "mtime": int(st.st_mtime)})
                except OSError:
                    continue
        except (OSError, PermissionError):
            return None
        return Evidence(
            collector=self.name,
            kind="cred_dir_manifest",
            key=str(d),
            attrs={"path": str(d), "entries": entries, "entry_count": len(entries)},
        )

    def _crontab(self) -> list[Evidence]:
        rc, out, _ = run_cmd(["crontab", "-l"], timeout=5)
        if rc != 0 or not out.strip():
            return []
        lines = [l for l in out.splitlines() if l.strip() and not l.strip().startswith("#")]
        return [Evidence(
            collector=self.name,
            kind="cron_or_at_added" if lines else "crontab_empty",
            key="crontab:user",
            attrs={"line_count": len(lines), "entries": lines[:20]},
        )]

    def _at_queue(self) -> list[Evidence]:
        rc, out, _ = run_cmd(["atq"], timeout=5)
        if rc != 0 or not out.strip():
            return []
        jobs = [l for l in out.splitlines() if l.strip()]
        if not jobs:
            return []
        return [Evidence(
            collector=self.name,
            kind="cron_or_at_added",
            key="atq",
            attrs={"job_count": len(jobs), "jobs": jobs[:20]},
        )]
