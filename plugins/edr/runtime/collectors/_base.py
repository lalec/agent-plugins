"""Collector contract + Evidence/Anomaly data model.

Collectors are the only thing that touches host state. They emit normalized
Evidence records — never verdicts. The analyst (Claude in SKILL.md) reasons
over the diff against baseline.
"""
from __future__ import annotations

import hashlib
import json
import socket
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Literal

Tier = Literal["T", "D", "OD"]
Maturity = Literal["experimental", "beta", "stable"]


@dataclass
class Evidence:
    """A single normalized observation from a collector. JSON-serializable."""
    collector: str
    kind: str                 # collector-defined sub-type (e.g. 'process', 'tcp_listener')
    key: str                  # stable identifier within (collector, kind) — used for diffing
    attrs: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def signature_hash(self) -> str:
        """Stable 16-hex-char hash for FP registry / dedup. Hashes (collector, kind, key) only."""
        h = hashlib.sha256(f"{self.collector}|{self.kind}|{self.key}".encode()).hexdigest()
        return h[:16]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Anomaly:
    """Difference vs baseline. Produced by run_collectors.diff()."""
    change: Literal["added", "removed", "modified"]
    evidence: Evidence
    prior: Evidence | None = None     # populated for 'modified' / 'removed'
    floor_severity: str | None = None  # set by triage fast-path
    suppressed: bool = False           # set by triage if FP-matched

    def to_dict(self) -> dict[str, Any]:
        return {
            "change": self.change,
            "evidence": self.evidence.to_dict(),
            "prior": self.prior.to_dict() if self.prior else None,
            "floor_severity": self.floor_severity,
            "suppressed": self.suppressed,
        }


@dataclass
class CollectorContext:
    """Read-only environment passed to each collector.collect() call.

    `data_dir` is the host-local state root (default `~/.claude/edr`, override
    via `EDR_HOME`). Collectors that cache or persist anything write under
    `data_dir / "state"`.
    """
    data_dir: Path
    last_run_path: Path
    snapshot_dir: Path
    hostname: str
    now: float

    @classmethod
    def build(cls, data_dir: Path, snapshot_dir: Path) -> "CollectorContext":
        return cls(
            data_dir=data_dir,
            last_run_path=data_dir / "state" / "last_run.json",
            snapshot_dir=snapshot_dir,
            hostname=socket.gethostname(),
            now=time.time(),
        )


class Collector(ABC):
    """Abstract base. Subclass and implement .collect(). Auto-discovered from collectors/*.py."""
    name: ClassVar[str]
    tier: ClassVar[Tier]
    maturity: ClassVar[Maturity] = "experimental"  # overridable via manifest.yaml
    version: ClassVar[int] = 1
    mitre: ClassVar[list[str]] = []
    # Attribute names to exclude from baseline diffs (kept in snapshot for analyst
    # context but ignored when deciding "modified"). Use for churn-prone metrics
    # like CPU%, pids, started_at — anything observation-volatile but not security-relevant.
    volatile_attrs: ClassVar[list[str]] = []

    @abstractmethod
    def collect(self, ctx: CollectorContext) -> list[Evidence]:
        """Gather evidence. Must not raise — use try/except internally and emit
        an Evidence with kind='error' on failure so the analyst sees the gap."""
        ...

    @classmethod
    def safe_evidence(cls, kind: str, key: str, **attrs: Any) -> Evidence:
        return Evidence(collector=cls.name, kind=kind, key=key, attrs=attrs)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str, sort_keys=True))


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())
