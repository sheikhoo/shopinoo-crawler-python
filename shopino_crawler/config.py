from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    root: Path
    ingest_url: str
    token: str
    seed_csv: Path
    directories_csv: Path
    redis_url: str
    crawler_db_path: str
    force_rediscover: bool
    requests_per_minute: int
    per_host_delay_ms: int
    max_pages_per_domain: int
    fetch_timeout_ms: int
    user_agent: str
    discover_enabled: bool
    max_discover_per_page: int
    max_expand_per_domain: int
    max_domains_per_run: int
    use_playwright: bool
    playwright_wait_ms: int
    playwright_channel: str
    browser_ua: str


def load_config() -> Config:
    return Config(
        root=ROOT,
        ingest_url=(
            os.getenv("INGEST_API_URL")
            or "http://localhost:4000/api/internal/ingest/businesses"
        ).rstrip("/"),
        token=(os.getenv("CRAWLER_SERVICE_TOKEN") or "").strip(),
        seed_csv=Path(os.getenv("SEED_CSV") or ROOT / "seeds" / "shops.csv"),
        directories_csv=Path(
            os.getenv("DIRECTORIES_CSV") or ROOT / "seeds" / "directories.csv"
        ),
        redis_url=(os.getenv("REDIS_URL") or "").strip(),
        crawler_db_path=(
            os.getenv("CRAWLER_DB_PATH") or str(ROOT / "data" / "crawler.db")
        ).strip(),
        force_rediscover=_bool("CRAWLER_REDISCOVER", False),
        requests_per_minute=_int("REQUESTS_PER_MINUTE", 20),
        per_host_delay_ms=_int("PER_HOST_DELAY_MS", 2500),
        max_pages_per_domain=_int("MAX_PAGES_PER_DOMAIN", 8),
        fetch_timeout_ms=_int("FETCH_TIMEOUT_MS", 12000),
        user_agent=(
            os.getenv("USER_AGENT")
            or "ShopinoBot/1.0 (+https://shopinoo-plus.ir/bot)"
        ),
        discover_enabled=_bool("DISCOVER_ENABLED", True),
        max_discover_per_page=_int("MAX_DISCOVER_PER_PAGE", 100),
        max_expand_per_domain=_int("MAX_EXPAND_PER_DOMAIN", 40),
        max_domains_per_run=_int("MAX_DOMAINS_PER_RUN", 200),
        use_playwright=_bool("USE_PLAYWRIGHT", True),
        playwright_wait_ms=_int("PLAYWRIGHT_WAIT_MS", 8000),
        playwright_channel=(os.getenv("PLAYWRIGHT_CHANNEL") or "msedge").strip(),
        browser_ua=(
            os.getenv("BROWSER_UA")
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
    )


config = load_config()
