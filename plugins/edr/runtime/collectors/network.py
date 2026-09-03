"""Network state collector.

`tcp_listener` / `udp_listener`: each listening socket is a stable identity
worth diffing (UDP below the ephemeral range only).
`outbound`: established connections grouped by (command, remote port). The
pair is the identity; the remote IPs are volatile context and the input to the
intel match. A first-seen pair from a process that should not talk out is the
C2 / exfil signal.
`netconfig`: resolvers, system proxy, `/etc/resolver/*`. A proxy or resolver
override is interception; resolvers alone follow the network you are on, so
they carry no floor.
"""
from __future__ import annotations

import ipaddress
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from collectors._base import Collector, CollectorContext, Evidence
from collectors._util import run_cmd, sha256_file

UDP_EPHEMERAL_MIN = 49152
MAX_REMOTE_IPS = 20
PROXY_KEYS = ("HTTPEnable", "HTTPProxy", "HTTPPort", "HTTPSEnable", "HTTPSProxy", "HTTPSPort",
              "SOCKSEnable", "SOCKSProxy", "SOCKSPort", "ProxyAutoConfigEnable",
              "ProxyAutoConfigURLString", "ProxyAutoDiscoveryEnable")


class NetworkCollector(Collector):
    name = "network"
    tier = "T"
    maturity = "stable"
    version = 2
    mitre = ["T1571", "T1095", "T1049", "T1071", "T1557"]
    volatile_attrs = ["pid", "remote_ips", "connection_count"]

    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        return (self._listeners("tcp") + self._listeners("udp") + self._outbound()
                + self._netconfig())

    # --- sockets ---------------------------------------------------------------

    def _lsof(self, *args: str) -> list[list[str]] | None:
        rc, out, _ = run_cmd(["lsof", *args, "-nP", "+c", "0"], timeout=10)
        if rc != 0 and not out:
            return None
        rows = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 9:
                parts[0] = parts[0].replace("\\x20", " ")  # lsof escapes spaces in command names
                rows.append(parts)
        return rows

    def _listeners(self, proto: str) -> list[Evidence]:
        rows = self._lsof("-iTCP", "-sTCP:LISTEN") if proto == "tcp" else self._lsof("-iUDP")
        if rows is None:
            return [self.safe_evidence("error", f"lsof_{proto}_failed", error="lsof failed")]
        by_key: dict[str, Evidence] = {}
        for parts in rows:
            command, pid, user, _, family, *_ = parts
            name = " ".join(parts[8:])
            if "->" in name:
                continue  # connected socket, not a listener
            ip, port = self._split_listen(name)
            if port is None or (proto == "udp" and port >= UDP_EPHEMERAL_MIN):
                continue
            key = f"{proto}|{ip}|{port}|{command}"
            if key in by_key:
                fams = by_key[key].attrs.setdefault("ip_families", [])
                if family not in fams:
                    fams.append(family)
                continue
            by_key[key] = Evidence(
                collector=self.name, kind=f"{proto}_listener", key=key,
                attrs={"command": command, "pid": int(pid) if pid.isdigit() else pid, "user": user,
                       "bind_addr": ip, "port": port, "proto": proto,
                       "loopback_only": ip in ("127.0.0.1", "::1"), "ip_families": [family]},
            )
        return list(by_key.values())

    def _outbound(self) -> list[Evidence]:
        rows = self._lsof("-iTCP", "-sTCP:ESTABLISHED")
        if rows is None:
            return []
        groups: dict[tuple[str, int], dict[str, Any]] = defaultdict(lambda: {"ips": set(), "n": 0})
        for parts in rows:
            command, _pid, user = parts[0], parts[1], parts[2]
            remote = self._extract_remote(" ".join(parts[8:]))
            if not remote:
                continue
            ip, port = self._split_listen(remote)
            if port is None or self._is_loopback(ip):
                continue
            g = groups[(command, port)]
            g["ips"].add(ip)
            g["n"] += 1
            g["user"] = user
        return [
            Evidence(collector=self.name, kind="outbound", key=f"out|{command}|{port}",
                     attrs={"command": command, "remote_port": port, "user": g["user"],
                            "remote_ips": sorted(g["ips"])[:MAX_REMOTE_IPS],
                            "connection_count": g["n"]})
            for (command, port), g in groups.items()
        ]

    # --- configuration -------------------------------------------------------

    def _netconfig(self) -> list[Evidence]:
        out: list[Evidence] = []
        rc, dns, _ = run_cmd(["scutil", "--dns"], timeout=10)
        if rc == 0:
            servers = sorted(set(re.findall(r"nameserver\[\d+\]\s*:\s*(\S+)", dns)))
            search = sorted(set(re.findall(r"search domain\[\d+\]\s*:\s*(\S+)", dns)))
            out.append(Evidence(collector=self.name, kind="netconfig", key="netconfig|resolvers",
                                attrs={"nameservers": servers, "search_domains": search}))
        rc, proxy, _ = run_cmd(["scutil", "--proxy"], timeout=10)
        if rc == 0:
            kv = dict(re.findall(r"^\s*(\w+)\s*:\s*(.+?)\s*$", proxy, re.M))
            attrs = {k: kv[k] for k in PROXY_KEYS if k in kv}
            attrs["any_enabled"] = any(kv.get(k) == "1" for k in PROXY_KEYS if k.endswith("Enable"))
            out.append(Evidence(collector=self.name, kind="netconfig", key="netconfig|proxy", attrs=attrs))
        resolver_dir = Path("/etc/resolver")
        files = {}
        if resolver_dir.is_dir():
            for p in sorted(resolver_dir.iterdir()):
                if p.is_file():
                    files[p.name] = sha256_file(p)
        out.append(Evidence(collector=self.name, kind="netconfig", key="netconfig|etc_resolver",
                            attrs={"files": files, "count": len(files)}))
        return out

    # --- parsing -------------------------------------------------------------

    @staticmethod
    def _is_loopback(ip: str) -> bool:
        try:
            return ipaddress.ip_address(ip).is_loopback
        except ValueError:
            return ip in ("localhost",)

    @staticmethod
    def _split_listen(name: str) -> tuple[str, int | None]:
        """'*:8080' | '127.0.0.1:5432' | '[::]:443' | '[::1]:5000' → (ip, port)."""
        addr = name.replace("(LISTEN)", "").split("(", 1)[0].strip()
        if ":" not in addr:
            return ("", None)
        if addr.startswith("["):
            ip, _, port = addr.rpartition("]:")
            ip = ip[1:]
        else:
            ip, _, port = addr.rpartition(":")
        if ip == "*":
            ip = "0.0.0.0"
        try:
            return (ip, int(port))
        except ValueError:
            return ("", None)

    @staticmethod
    def _extract_remote(name: str) -> str | None:
        """'192.168.1.5:55123->17.253.55.207:443 (ESTABLISHED)' → '17.253.55.207:443'."""
        if "->" not in name:
            return None
        _, _, remote = name.partition("->")
        remote = remote.split("(", 1)[0].strip()
        return remote or None
