"""Docker container collector.

Flags container security boundaries: --privileged, /var/run/docker.sock mount,
--cap-add, host-network. These are container-escape vectors.
"""
from __future__ import annotations

import json
from typing import Any

from collectors._base import Collector, CollectorContext, Evidence
from collectors._util import run_cmd


class DockerCollector(Collector):
    name = "docker"
    tier = "T"
    maturity = "stable"
    version = 1
    mitre = ["T1611", "T1610"]
    # 'running' toggles; 'started_at' shifts when a container is restarted.
    volatile_attrs = ["running", "started_at"]

    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        rc, out, err = run_cmd(["docker", "ps", "-a", "--format", "{{json .}}"], timeout=10)
        if rc == -127:
            # docker not installed — emit nothing (silence is the right answer)
            return []
        if rc != 0:
            # docker installed but daemon unreachable
            return [Evidence(collector=self.name, kind="error", key="docker_ps_failed",
                             attrs={"error": err.strip()[:500]})]

        evidences: list[Evidence] = []
        container_ids: list[str] = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            cid = row.get("ID") or ""
            container_ids.append(cid)

        for cid in container_ids:
            ev = self._inspect(cid)
            if ev:
                evidences.append(ev)

        return evidences

    def _inspect(self, cid: str) -> Evidence | None:
        rc, out, _ = run_cmd(["docker", "inspect", cid], timeout=10)
        if rc != 0:
            return None
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return None
        if not data:
            return None
        c = data[0]
        host_cfg = c.get("HostConfig", {}) or {}
        config = c.get("Config", {}) or {}
        state = c.get("State", {}) or {}
        mounts = c.get("Mounts", []) or []

        privileged = bool(host_cfg.get("Privileged", False))
        cap_add = host_cfg.get("CapAdd") or []
        net_mode = host_cfg.get("NetworkMode", "")
        binds = host_cfg.get("Binds") or []
        socket_mounted = any("/var/run/docker.sock" in str(b) for b in binds) or any(
            (m.get("Source") or "").endswith("docker.sock") for m in mounts
        )

        return Evidence(
            collector=self.name,
            kind="container",
            key=cid[:12],
            attrs={
                "container_id": cid[:12],
                "name": (c.get("Name") or "").lstrip("/"),
                "image": config.get("Image"),
                "running": bool(state.get("Running", False)),
                "started_at": state.get("StartedAt"),
                "command": " ".join(config.get("Cmd") or [])[:200],
                "entrypoint": " ".join(config.get("Entrypoint") or [])[:200],
                "privileged": privileged,
                "cap_add": cap_add,
                "network_mode": net_mode,
                "host_network": net_mode == "host",
                "docker_socket_mounted": socket_mounted,
                "privileged_or_docker_socket": privileged or socket_mounted,
                "mount_count": len(mounts),
                "ports": list((host_cfg.get("PortBindings") or {}).keys()),
            },
        )
