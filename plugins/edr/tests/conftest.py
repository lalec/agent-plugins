"""Isolate EDR_HOME before any runtime module is imported (paths resolves it at import)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_HOME = tempfile.mkdtemp(prefix="edr-test-")
os.environ["EDR_HOME"] = _HOME
os.environ.pop("EDR_HEADLESS", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "runtime"))

import paths  # noqa: E402

paths.ensure()
