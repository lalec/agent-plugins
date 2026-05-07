"""IOC database — sqlite schema + accessors.

One row per IOC. Collectors and the analyst query by (ioc_type, value) or
(mitre_id) for enrichment. Feeds insert/upsert via sync.py.
"""
from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Make runtime/ importable when this module is loaded standalone (e.g. by sync.py).
_RUNTIME = Path(__file__).resolve().parent.parent
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

import paths  # noqa: E402

DB_PATH = paths.INTEL_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS iocs (
    ioc_type   TEXT NOT NULL,    -- 'hash_sha256', 'domain', 'ip', 'file_path', 'mitre_id', 'plist_label'
    value      TEXT NOT NULL,
    feed       TEXT NOT NULL,
    severity   TEXT,
    first_seen REAL NOT NULL,
    last_seen  REAL NOT NULL,
    metadata   TEXT,
    PRIMARY KEY (ioc_type, value, feed)
);
CREATE INDEX IF NOT EXISTS iocs_value_idx ON iocs(value);
CREATE INDEX IF NOT EXISTS iocs_type_idx ON iocs(ioc_type);
"""


@contextmanager
def connect(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert(conn: sqlite3.Connection, ioc_type: str, value: str, feed: str,
           severity: str | None, ts: float, metadata: str | None = None) -> None:
    conn.execute(
        """INSERT INTO iocs(ioc_type, value, feed, severity, first_seen, last_seen, metadata)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(ioc_type, value, feed) DO UPDATE SET
               last_seen = excluded.last_seen,
               severity = excluded.severity,
               metadata = excluded.metadata""",
        (ioc_type, value, feed, severity, ts, ts, metadata),
    )


def lookup(conn: sqlite3.Connection, ioc_type: str, value: str) -> list[dict]:
    cur = conn.execute(
        "SELECT feed, severity, first_seen, last_seen, metadata FROM iocs WHERE ioc_type=? AND value=?",
        (ioc_type, value),
    )
    return [{"feed": r[0], "severity": r[1], "first_seen": r[2], "last_seen": r[3], "metadata": r[4]}
            for r in cur.fetchall()]
