from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from .config import config
from .discover import discover_domains_from_html, is_shop_candidate
from .extract import extract_public_business, merge_extractions
from .fetch import fetch_public, is_allowed
from .normalize import normalize_domain
from .pages import build_crawl_targets
from .publish import publish_business
from .queue import create_queue
from .render import render_with_playwright
from .socials import extract_social_links
from .assets import harvest_socials_from_assets


def load_seed_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith("domain,"):
            continue
        parts = line.split(",", 1)
        domain = normalize_domain(parts[0])
        if not domain:
            continue
        name = parts[1].strip() if len(parts) > 1 else ""
        rows.append({"domain": domain, "name": name})
    return rows


def load_directory_urls(path: Path) -> list[str]:
    if not path.exists():
        return []
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith("url,"):
            continue
        url = line.split(",", 1)[0].strip()
        if url.startswith("http"):
            urls.append(url)
    return urls


def expand_from_html(
    html: str,
    page_url: str,
    host: str,
    enqueue,
) -> int:
    if not config.discover_enabled or not html:
        return 0
    found = discover_domains_from_html(
        html,
        max_domains=config.max_expand_per_domain,
        current_host=host,
        base_url=page_url,
    )
    added = 0
    for d in found:
        if enqueue(d):
            added += 1
    return added


def crawl_domain(domain: str, seed_name: str | None, enqueue) -> dict | None:
    host = normalize_domain(domain)
    if not host:
        print(f"[skip] invalid domain: {domain}", flush=True)
        return None

    print(f"[crawl] start {host}", flush=True)
    print(f"[crawl] robots {host} …", flush=True)
    if not is_allowed(host, "/"):
        print(f"[robots] blocked {host}", flush=True)
        return None

    home_url = f"https://{host}/"
    home_html = ""
    home_final = home_url
    print(f"[crawl] fetch {home_url}", flush=True)
    home_res = fetch_public(home_url, prefer_browser_ua=True)
    if home_res.get("ok") and home_res.get("html"):
        home_html = home_res["html"]
        home_final = home_res.get("url") or home_url
        print(f"[ok] {home_final} (homepage)", flush=True)
    else:
        print(
            f"[fetch] {home_res.get('status')} {home_url} "
            f"{home_res.get('error') or ''}",
            flush=True,
        )

    # اگر فوتر/سوشال در HTML اولیه نبود (مثل خانومی/Next.js):
    # ۱) اسکن باندل‌های JS عمومی  ۲) رندر Playwright با Edge/Chrome سیستم
    static_socials = extract_social_links(home_html, home_final) if home_html else []
    if home_html and not static_socials:
        print(f"[crawl] assets scan {host} …", flush=True)
        asset_socials = harvest_socials_from_assets(home_html, home_final)
        if asset_socials:
            print(f"[assets] socials={len(asset_socials)}", flush=True)
            # تزریق لینک‌ها به‌صورت کامنت مجازی تا extractor بعدی ببیند
            inject = "\n".join(
                f'<a href="{s["url"]}">{s["platform"]}</a>' for s in asset_socials
            )
            home_html = home_html + "\n<!-- shopino-social-inject -->\n" + inject
            static_socials = asset_socials

    # فقط وقتی واقعاً سوشال نداریم Playwright بزن (assets کافی بود → رد شو)
    if config.use_playwright and not static_socials:
        print(
            f"[render] playwright {home_final} (socials_static=0)",
            flush=True,
        )
        rendered = render_with_playwright(home_final or home_url)
        if rendered.get("ok") and rendered.get("html"):
            home_html = rendered["html"]
            home_final = rendered.get("url") or home_final
            rendered_socials = extract_social_links(home_html, home_final)
            print(f"[render] ok socials={len(rendered_socials)}", flush=True)
        else:
            print(f"[render] fail {rendered.get('error')}", flush=True)

    max_pages = max(config.max_pages_per_domain, 8)
    targets = build_crawl_targets(host, home_html, home_final, max_pages)
    print(f"[targets] {host} → {len(targets)} pages", flush=True)

    parts: list[dict] = []
    total_expanded = 0
    did_home = False

    for url in targets:
        path = "/"
        try:
            path = urlparse(url).path or "/"
        except Exception:
            continue
        if not is_allowed(host, path):
            continue

        if home_html and path in {"/", ""}:
            if not did_home:
                did_home = True
                parts.append(extract_public_business(home_html, home_final, host))
                total_expanded += expand_from_html(home_html, home_final, host, enqueue)
            continue

        res = fetch_public(url)
        if not res.get("ok") or not res.get("html"):
            print(f"[fetch] {res.get('status')} {url}")
            continue
        extracted = extract_public_business(res["html"], res.get("url") or url, host)
        parts.append(extracted)
        print(f"[ok] {res.get('url')} → {extracted.get('name')}")
        total_expanded += expand_from_html(
            res["html"], res.get("url") or url, host, enqueue
        )

    if total_expanded:
        print(f"[expand] {host} → +{total_expanded} domains")

    if not parts and home_html:
        parts.append(extract_public_business(home_html, home_final, host))

    if not parts:
        print(f"[empty] no public pages for {host}")
        return None

    merged = merge_extractions(parts, host, home_final)
    if seed_name and (not merged.get("name") or merged.get("name") == host):
        merged["name"] = seed_name

    if not merged.get("name") or not merged.get("canonicalDomain"):
        print(f"[gate] missing name/domain for {host}")
        return None

    result = publish_business(merged)
    print(
        f"[ingest] {result.get('action')} {result.get('slug')} "
        f"({result.get('canonicalDomain')})"
    )
    return result


def run_directory_discovery(enqueue) -> int:
    if not config.discover_enabled:
        print("[discover] disabled")
        return 0
    pages = load_directory_urls(config.directories_csv)
    print(f"[discover] directory pages: {len(pages)}")
    total = 0
    for page in pages:
        host = normalize_domain(page)
        # صفحات دایرکتوری seedشده را به‌خاطر robots رد نکن — فقط برای کشف لینک عمومی
        res = fetch_public(page)
        if not res.get("ok") or not res.get("html"):
            print(f"[discover] {res.get('status')} {page}")
            continue
        domains = [
            d
            for d in discover_domains_from_html(
                res["html"],
                max_domains=config.max_discover_per_page,
                current_host=host,
                base_url=res.get("url") or page,
            )
            if is_shop_candidate(d)
        ]
        print(f"[discover] {page} → {len(domains)} shop domains")
        for d in domains:
            if enqueue(d):
                total += 1
    print(f"[discover] queued {total} new domains from directories")
    return total


def run_crawler(
    *,
    seed_only: bool = False,
    discover_only: bool = False,
    reset_queue: bool = False,
    rediscover: bool = False,
) -> None:
    queue, qtype = create_queue()
    print(f"[queue] type={qtype}")

    if reset_queue and hasattr(queue, "reset"):
        queue.reset()
        print("[queue] reset — صف و سابقه پاک شد")

    prior = queue.stats() if hasattr(queue, "stats") else None
    if prior:
        print(
            f"[queue] pending={prior['pending']} done={prior['done']} "
            f"failed={prior['failed']} total={prior['total']}"
        )
        reclaimed = getattr(queue, "_reclaimed", 0)
        if reclaimed:
            print(f"[queue] reclaimed {reclaimed} interrupted jobs")

    print(f"[discover] enabled={config.discover_enabled}")

    def enqueue(domain: str) -> bool:
        return queue.push(domain)

    seeds = load_seed_csv(config.seed_csv)
    print(f"[seed] loaded {len(seeds)} domains from CSV")
    seed_names = {row["domain"]: row.get("name") or None for row in seeds}
    seed_added = 0
    for row in seeds:
        if enqueue(row["domain"]):
            seed_added += 1
    print(f"[seed] queued {seed_added} new domains")

    force_discover = (
        discover_only
        or rediscover
        or config.force_rediscover
    )
    prior_total = prior["total"] if prior else 0

    if config.discover_enabled:
        if prior_total > 0 and not force_discover:
            if queue.size() > 0:
                print(
                    "[discover] skipped (resume; --rediscover برای کشف دوباره)"
                )
            else:
                print("[discover] صف خالی — جستجوی دامنهٔ جدید از دایرکتوری‌ها")
                run_directory_discovery(enqueue)
                if hasattr(queue, "set_meta"):
                    from datetime import datetime, timezone

                    queue.set_meta(
                        "last_discover",
                        datetime.now(timezone.utc).isoformat(),
                    )
        else:
            run_directory_discovery(enqueue)
            if hasattr(queue, "set_meta"):
                from datetime import datetime, timezone

                queue.set_meta(
                    "last_discover",
                    datetime.now(timezone.utc).isoformat(),
                )

    if seed_only or discover_only:
        label = "discover-only" if discover_only else "seed-only"
        print(f"[{label}] queued={queue.size()} seen={queue.seen_count()}")
        queue.close()
        return

    processed = 0
    limit = config.max_domains_per_run or 10**9
    print(
        f"[run] processing up to {limit} domains "
        f"(queue pending≈{queue.size()})",
        flush=True,
    )
    while processed < limit:
        domain = queue.pop()
        if not domain:
            break
        print(
            f"[run] #{processed + 1}/{limit} → {domain} "
            f"(remaining≈{queue.size()})",
            flush=True,
        )
        try:
            crawl_domain(domain, seed_names.get(domain), enqueue)
            queue.mark_done(domain)
            print(f"[run] done {domain}", flush=True)
        except Exception as exc:
            print(f"[fail] {domain}: {exc}", flush=True)
            queue.mark_failed(domain, str(exc))
        processed += 1

    print(
        f"[done] processed={processed} remaining={queue.size()} "
        f"seen={queue.seen_count()}"
    )
    if hasattr(queue, "stats"):
        s = queue.stats()
        print(
            f"[db] pending={s['pending']} done={s['done']} failed={s['failed']}"
        )
    queue.close()
