"""Local record of every file already handled, so nothing is read or booked twice."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    sha256  TEXT PRIMARY KEY,
    path    TEXT,
    doc_key TEXT,
    layer   TEXT,
    status  TEXT,       -- extracted, filed, booked, ignored
    updated TEXT
);
CREATE INDEX IF NOT EXISTS by_key ON documents (doc_key);
"""


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


class Ledger:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def get(self, digest: str) -> dict | None:
        row = self.db.execute("SELECT * FROM documents WHERE sha256 = ?", (digest,)).fetchone()
        return dict(row) if row else None

    def by_key(self, doc_key: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM documents WHERE doc_key = ?", (doc_key,))]

    def record(self, digest: str, path: str, doc_key: str, layer: str, status: str) -> None:
        self.db.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(sha256) DO UPDATE SET "
            "path = excluded.path, doc_key = excluded.doc_key, layer = excluded.layer, status = excluded.status, "
            "updated = excluded.updated",
            (digest, path, doc_key, layer, status, dt.datetime.now().isoformat(timespec="seconds")),
        )
        self.db.commit()
