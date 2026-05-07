"""Network state collector.

Listeners (TCP) are individually baselined — each is a stable identity worth
diffing. Established connections are aggregated into a summary so per-connection
churn doesn't flood the diff stream.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from collectors._base import Collector, CollectorContext, Evidence
from collectors._util import run_cmd


class NetworkCollector(Collector):
    name = "network"
    tier = "T"
    maturity = "stable"
    version = 1
    mitre = ["T1571", "T1095", "T1049"]
    # pid changes when a process restarts; established_summary attrs all churn per-tick.
    volatile_attrs = ["pid", "total", "top_remotes", "top_commands"]

    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        evidences: list[Evidence] = []
        evidences.extend(self._listeners())
        evidences.extend(self._established_summary())
        return evidences

    def _listeners(self) -> list[Evidence]:
        rc, out, err = run_cmd(
            ["lsof", "-iTCP", "-sTCP:LISTEN", "-nP", "+c", "0"], timeout=10
        )
        if rc != 0:
            return [Evidence(collector=self.name, kind="error", key="lsof_listen_failed",
                             attrs={"error": err.strip()[:500]})]

        # Dedupe across IPv4/IPv6 dual-stack rows for the same socket.
        by_key: dict[str, Evidence] = {}
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 9:
                continue
            command, pid, user, _, family, *_ = parts
            name_field = " ".join(parts[8:])
            ip, port = self._split_listen(name_field)
            if port is None:
                continue
            key = f"tcp|{ip}|{port}|{command}"
            if key in by_key:
                fams = by_key[key].attrs.setdefault("ip_families", [])
                if family not in fams:
                    fams.append(family)
                continue
            by_key[key] = Evidence(
                collector=self.name,
                kind="tcp_listener",
                key=key,
                attrs={
                    "command": command,
                    "pid": int(pid) if pid.isdigit() else pid,
                    "user": user,
                    "bind_addr": ip,
                    "port": port,
                    "loopback_only": ip in ("127.0.0.1", "::1"),
                    "ip_families": [family],
                },
            )
        return list(by_key.values())

    def _established_summary(self) -> list[Evidence]:
        rc, out, _ = run_cmd(
            ["lsof", "-iTCP", "-sTCP:ESTABLISHED", "-nP", "+c", "0"], timeout=10
        )
        if rc != 0:
            return []
        remote_counter: Counter[str] = Counter()
        per_command: Counter[str] = Counter()
        total = 0
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 9:
                continue
            command = parts[0]
            name_field = " ".join(parts[8:])
            remote = self._extract_remote(name_field)
            if remote:
                remote_counter[remote] += 1
                per_command[command] += 1
                total += 1
        return [Evidence(
            collector=self.name,
            kind="established_summary",
            key="established_snapshot",
            attrs={
                "total": total,
                "top_remotes": remote_counter.most_common(20),
                "top_commands": per_command.most_common(15),
            },
        )]

    @staticmethod
    def _split_listen(name: str) -> tuple[str, int | None]:
        # name like "*:8080" or "127.0.0.1:5432" or "[::]:443" or "[::1]:5000"
        if "->" in name or "(LISTEN)" not in name and ":" not in name:
            return ("", None)
        addr_part = name.replace("(LISTEN)", "").strip()
        if addr_part.startswith("["):
            try:
                ip, _, port = addr_part.rpartition("]:")
                return (ip[1:], int(port))
            except ValueError:
                return ("", None)
        if ":" not in addr_part:
            return ("", None)
        ip, _, port = addr_part.rpartition(":")
        if ip == "*":
            ip = "0.0.0.0"
        try:
            return (ip, int(port))
        except ValueError:
            return ("", None)

    @staticmethod
    def _extract_remote(name: str) -> str | None:
        # name like "192.168.1.5:55123->17.253.55.207:443"
        if "->" not in name:
            return None
        _, _, remote = name.partition("->")
        remote = remote.split("(", 1)[0].strip()
        return remote or None
