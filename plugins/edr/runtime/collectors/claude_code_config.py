"""Claude Code config collector — highest-leverage AI-stack surface.

Hooks in settings*.json run arbitrary shell on every Claude tool use. New plugins,
skills, commands, agents, and MCP servers are supply-chain risks. Tracks them all.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from collectors._base import Collector, CollectorContext, Evidence
from collectors._util import sha256_file

CLAUDE_HOME = Path("~/.claude").expanduser()
SETTINGS_FILES = [CLAUDE_HOME / "settings.json", CLAUDE_HOME / "settings.local.json"]
SUBDIRS = [
    ("skill_added", CLAUDE_HOME / "skills"),
    ("plugin_added", CLAUDE_HOME / "plugins"),
    ("command_added", CLAUDE_HOME / "commands"),
    ("agent_added", CLAUDE_HOME / "agents"),
]
CLAUDE_MD = CLAUDE_HOME / "CLAUDE.md"
KEYBINDINGS = CLAUDE_HOME / "keybindings.json"


class ClaudeCodeConfigCollector(Collector):
    name = "claude_code_config"
    tier = "T"
    maturity = "stable"
    version = 1
    mitre = ["T1546", "T1195.002", "T1059.004"]

    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        out: list[Evidence] = []
        for f in SETTINGS_FILES:
            if f.exists():
                out.extend(self._parse_settings(f))
        for kind, d in SUBDIRS:
            out.extend(self._enumerate(kind, d))
        if CLAUDE_MD.exists():
            out.append(Evidence(
                collector=self.name, kind="claude_md", key="claude_md:global",
                attrs={"path": str(CLAUDE_MD), "sha256": sha256_file(CLAUDE_MD),
                       "size": CLAUDE_MD.stat().st_size},
            ))
        if KEYBINDINGS.exists():
            out.append(Evidence(
                collector=self.name, kind="setting", key="setting:keybindings",
                attrs={"path": str(KEYBINDINGS), "sha256": sha256_file(KEYBINDINGS)},
            ))
        return out

    def _parse_settings(self, settings_file: Path) -> list[Evidence]:
        try:
            data = json.loads(settings_file.read_text())
        except (OSError, json.JSONDecodeError) as e:
            return [Evidence(collector=self.name, kind="error",
                             key=f"settings_unparseable:{settings_file.name}",
                             attrs={"path": str(settings_file), "error": str(e)})]
        out: list[Evidence] = []
        scope = settings_file.name  # 'settings.json' or 'settings.local.json'

        # Hooks: most dangerous — arbitrary shell on tool events
        hooks = data.get("hooks") or {}
        if isinstance(hooks, dict):
            for event, entries in hooks.items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    cmd = self._hook_command(entry)
                    if not cmd:
                        continue
                    sig = hashlib.sha256(cmd.encode()).hexdigest()[:10]
                    out.append(Evidence(
                        collector=self.name,
                        kind="hook_added",
                        key=f"hook:{scope}:{event}:{sig}",
                        attrs={
                            "scope": scope,
                            "event": event,
                            "command": cmd[:500],
                            "matcher": entry.get("matcher") if isinstance(entry, dict) else None,
                        },
                    ))

        # MCP servers
        mcp = data.get("mcpServers") or data.get("mcp_servers") or {}
        if isinstance(mcp, dict):
            for server_name, cfg in mcp.items():
                if not isinstance(cfg, dict):
                    continue
                out.append(Evidence(
                    collector=self.name,
                    kind="mcp_server_added",
                    key=f"mcp:{scope}:{server_name}",
                    attrs={
                        "scope": scope,
                        "server_name": server_name,
                        "command": cfg.get("command"),
                        "args": cfg.get("args") or [],
                        "url": cfg.get("url"),
                        "env_keys": list((cfg.get("env") or {}).keys()),
                    },
                ))

        # Other top-level settings — emit one Evidence with overall hash
        non_volatile = {k: v for k, v in data.items() if k not in ("hooks", "mcpServers", "mcp_servers")}
        if non_volatile:
            blob = json.dumps(non_volatile, sort_keys=True)
            out.append(Evidence(
                collector=self.name,
                kind="setting",
                key=f"setting:{scope}:body",
                attrs={
                    "scope": scope,
                    "sha256": hashlib.sha256(blob.encode()).hexdigest(),
                    "top_level_keys": sorted(non_volatile.keys()),
                },
            ))
        return out

    @staticmethod
    def _hook_command(entry: Any) -> str | None:
        if isinstance(entry, str):
            return entry
        if isinstance(entry, dict):
            cmd = entry.get("command")
            if isinstance(cmd, str):
                return cmd
            hooks = entry.get("hooks")
            if isinstance(hooks, list):
                inner = []
                for h in hooks:
                    if isinstance(h, dict) and isinstance(h.get("command"), str):
                        inner.append(h["command"])
                if inner:
                    return " ; ".join(inner)
        return None

    def _enumerate(self, kind: str, root: Path) -> list[Evidence]:
        if not root.is_dir():
            return []
        out: list[Evidence] = []
        try:
            children = sorted(root.iterdir())
        except OSError:
            return out
        for child in children:
            if child.name.startswith("."):
                continue
            name = child.name
            attrs: dict[str, Any] = {"path": str(child), "scope": "user"}
            # SKILL.md / first markdown body excerpt for context
            md_path = self._first_markdown(child) if child.is_dir() else None
            if md_path:
                try:
                    body = md_path.read_text(errors="replace")
                    attrs["body_sha256"] = hashlib.sha256(body.encode()).hexdigest()
                    attrs["body_excerpt"] = body[:300]
                except OSError:
                    pass
            elif child.is_file():
                attrs["sha256"] = sha256_file(child)
            out.append(Evidence(
                collector=self.name,
                kind=kind,
                key=f"{kind}:{name}",
                attrs={**attrs, "name": name},
            ))
        return out

    @staticmethod
    def _first_markdown(d: Path) -> Path | None:
        for candidate in ("SKILL.md", "README.md", "AGENT.md"):
            p = d / candidate
            if p.exists():
                return p
        try:
            for child in d.iterdir():
                if child.suffix.lower() == ".md":
                    return child
        except OSError:
            pass
        return None
