from __future__ import annotations

import argparse
import sys

from .config import config
from .worker import run_crawler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ShopinoBot Python — Public Business Data crawler",
    )
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="فقط seed را در صف بگذار",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="فقط کشف دامنه از دایرکتوری‌ها",
    )
    parser.add_argument(
        "--rediscover",
        action="store_true",
        help="حتی در حالت resume دوباره از دایرکتوری‌ها کشف کن",
    )
    parser.add_argument(
        "--reset-queue",
        action="store_true",
        help="صف SQLite را پاک کن و از صفر شروع کن",
    )
    args = parser.parse_args(argv)

    print("ShopinoBot Python public business crawler")
    print(f"UA: {config.user_agent}")
    print(f"Ingest: {config.ingest_url}")
    print(f"Discover: {'on' if config.discover_enabled else 'off'}")
    print(f"DB: {config.crawler_db_path}")

    if not config.token and not args.seed_only and not args.discover_only:
        print("CRAWLER_SERVICE_TOKEN is required", file=sys.stderr)
        return 1

    run_crawler(
        seed_only=args.seed_only,
        discover_only=args.discover_only,
        reset_queue=args.reset_queue,
        rediscover=args.rediscover,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
