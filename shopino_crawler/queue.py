from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import config
from .normalize import normalize_domain


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DomainQueue:
    def push(self, domain: str) -> bool: ...
    def pop(self) -> str | None: ...
    def size(self) -> int: ...
    def seen_count(self) -> int: ...
    def mark_done(self, domain: str) -> None: ...
    def mark_failed(self, domain: str, error: str = "") -> None: ...
    def close(self) -> None: ...


class MemoryQueue(DomainQueue):
    def __init__(self) -> None:
        self._q: list[str] = []
        self._seen: set[str] = set()

    def push(self, domain: str) -> bool:
        host = normalize_domain(domain)
        if not host or host in self._seen:
            return False
        self._seen.add(host)
        self._q.append(host)
        return True

    def pop(self) -> str | None:
        return self._q.pop(0) if self._q else None

    def size(self) -> int:
        return len(self._q)

    def seen_count(self) -> int:
        return len(self._seen)

    def mark_done(self, domain: str) -> None:
        return None

    def mark_failed(self, domain: str, error: str = "") -> None:
        return None

    def close(self) -> None:
        return None


class RedisQueue(DomainQueue):
    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.from_url(url, decode_responses=True)
        self._queue_key = "shopino:crawler:py:queue"
        self._seen_key = "shopino:crawler:py:seen"
        self._done_key = "shopino:crawler:py:done"

    def push(self, domain: str) -> bool:
        host = normalize_domain(domain)
        if not host:
            return False
        if self._r.sismember(self._done_key, host):
            return False
        if self._r.sadd(self._seen_key, host) == 0:
            return False
        self._r.rpush(self._queue_key, host)
        return True

    def pop(self) -> str | None:
        return self._r.lpop(self._queue_key)

    def size(self) -> int:
        return int(self._r.llen(self._queue_key))

    def seen_count(self) -> int:
        return int(self._r.scard(self._seen_key)) + int(
            self._r.scard(self._done_key)
        )

    def mark_done(self, domain: str) -> None:
        host = normalize_domain(domain)
        if host:
            self._r.sadd(self._done_key, host)

    def mark_failed(self, domain: str, error: str = "") -> None:
        # failed هم دیده می‌شود تا دوباره در همان run تکرار نشود
        self.mark_done(domain)

    def close(self) -> None:
        self._r.close()


class SqliteQueue(DomainQueue):
    """
    صف پایدار روی SQLite — بعد از توقف، دامنه‌های pending باقی می‌مانند.
    دامنه‌هایی که وسط کرال قطع شده‌اند (processing) هنگام باز شدن دوباره pending می‌شوند.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        # کرال‌های نیمه‌کاره بعد از کرش را برگردان
        cur = self._conn.execute(
            "UPDATE domains SET status='pending' WHERE status='processing'"
        )
        reclaimed = cur.rowcount
        self._conn.commit()
        self._reclaimed = reclaimed

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS domains (
              domain TEXT PRIMARY KEY,
              status TEXT NOT NULL CHECK(status IN ('pending','processing','done','failed')),
              enqueued_at TEXT NOT NULL,
              finished_at TEXT,
              last_error TEXT,
              attempts INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_domains_status
              ON domains(status, enqueued_at);
            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def push(self, domain: str) -> bool:
        host = normalize_domain(domain)
        if not host:
            return False
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO domains (domain, status, enqueued_at)
            VALUES (?, 'pending', ?)
            """,
            (host, _now()),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def pop(self) -> str | None:
        with self._conn:
            row = self._conn.execute(
                """
                SELECT domain FROM domains
                WHERE status='pending'
                ORDER BY enqueued_at ASC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            host = row["domain"]
            self._conn.execute(
                """
                UPDATE domains
                SET status='processing', attempts=attempts+1
                WHERE domain=? AND status='pending'
                """,
                (host,),
            )
            return host

    def size(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM domains WHERE status IN ('pending','processing')"
        ).fetchone()
        return int(row["c"] if row else 0)

    def seen_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM domains").fetchone()
        return int(row["c"] if row else 0)

    def mark_done(self, domain: str) -> None:
        host = normalize_domain(domain)
        if not host:
            return
        self._conn.execute(
            """
            UPDATE domains
            SET status='done', finished_at=?, last_error=NULL
            WHERE domain=?
            """,
            (_now(), host),
        )
        self._conn.commit()

    def mark_failed(self, domain: str, error: str = "") -> None:
        host = normalize_domain(domain)
        if not host:
            return
        self._conn.execute(
            """
            UPDATE domains
            SET status='failed', finished_at=?, last_error=?
            WHERE domain=?
            """,
            (_now(), (error or "")[:500], host),
        )
        self._conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            """
            INSERT INTO meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )
        self._conn.commit()

    def reset(self) -> None:
        self._conn.execute("DELETE FROM domains")
        self._conn.execute("DELETE FROM meta")
        self._conn.commit()

    def stats(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS c FROM domains GROUP BY status"
        ).fetchall()
        out = {r["status"]: int(r["c"]) for r in rows}
        return {
            "pending": out.get("pending", 0),
            "processing": out.get("processing", 0),
            "done": out.get("done", 0),
            "failed": out.get("failed", 0),
            "total": sum(out.values()),
        }

    def close(self) -> None:
        self._conn.close()


def create_queue() -> tuple[DomainQueue, str]:
    if config.redis_url:
        return RedisQueue(config.redis_url), "redis"

    db_path = (config.crawler_db_path or "").strip()
    if db_path.lower() in {"", "memory", "none", "off"}:
        return MemoryQueue(), "memory"

    path = Path(db_path)
    if not path.is_absolute():
        path = config.root / path
    q = SqliteQueue(path)
    return q, f"sqlite:{path}"
