"""
Seen-post storage.

SQLite rather than a JSON blob: the original reference script trimmed a
Python set to "the last 500" via `list(seen)[-500:]`, which drops arbitrary
entries because sets are unordered — posts silently un-see themselves and
get re-alerted. A table with timestamps makes retention explicit and lets us
keep a record of what was pushed and why.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_posts (
    post_key      TEXT PRIMARY KEY,
    group_url     TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    alerted       INTEGER NOT NULL DEFAULT 0,
    score         INTEGER,
    tier          TEXT,
    snippet       TEXT
);
CREATE INDEX IF NOT EXISTS idx_seen_posts_first_seen
    ON seen_posts (first_seen_at);
"""

# Facebook decorates post text with volatile chrome — reaction counts, "3h",
# "See more" — that would otherwise make the same post hash differently on
# every run. Strip it before fingerprinting.
_VOLATILE_PATTERNS = (
    re.compile(r"\b\d+\s*(?:likes?|comments?|shares?|reactions?)\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*(?:[smhdw]|mins?|hrs?|hours?|days?|weeks?)\s*(?:ago)?\b", re.IGNORECASE),
    re.compile(r"\b(?:see more|lihat lagi|show more|translated|lihat terjemahan)\b", re.IGNORECASE),
    re.compile(r"\s+"),
)


def fingerprint(text: str, permalink: str | None = None) -> str:
    """
    Stable identity for a post.

    Prefers the permalink when Facebook exposes one — that is a real ID and
    survives edits. Falls back to a hash of normalised text, which is why the
    volatile chrome has to come off first.
    """
    if permalink:
        cleaned = permalink.split("?")[0].rstrip("/")
        return f"url:{hashlib.sha256(cleaned.encode()).hexdigest()[:24]}"

    normalised = text.lower()
    for pattern in _VOLATILE_PATTERNS:
        normalised = pattern.sub(" ", normalised)
    normalised = normalised.strip()[:600]
    return f"txt:{hashlib.sha256(normalised.encode()).hexdigest()[:24]}"


class SeenStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def has_seen(self, post_key: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_posts WHERE post_key = ?", (post_key,)
            ).fetchone()
        return row is not None

    def record(
        self,
        post_key: str,
        group_url: str,
        alerted: bool,
        score: int | None = None,
        tier: str | None = None,
        snippet: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO seen_posts
                    (post_key, group_url, first_seen_at, alerted, score, tier, snippet)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    post_key,
                    group_url,
                    datetime.now(timezone.utc).isoformat(),
                    1 if alerted else 0,
                    score,
                    tier,
                    (snippet or "")[:300],
                ),
            )

    def prune(self, retention_days: int) -> int:
        """Drop records older than the retention window. Returns rows removed."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM seen_posts WHERE first_seen_at < ?", (cutoff,)
            )
            return cursor.rowcount

    def stats(self) -> dict[str, int]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM seen_posts").fetchone()[0]
            alerted = conn.execute(
                "SELECT COUNT(*) FROM seen_posts WHERE alerted = 1"
            ).fetchone()[0]
        return {"total_seen": total, "total_alerted": alerted}
