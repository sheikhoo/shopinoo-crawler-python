from __future__ import annotations

from .config import config


def needs_js_render(html: str) -> bool:
    """صفحات Next/SPA که محتوای فوتر را سمت کلاینت می‌سازند."""
    if not html:
        return True
    markers = (
        "/_next/static",
        "__NEXT_DATA__",
        'data-sentry-element":"Footer',
        "data-sentry-element\":\"Footer\"",
        'id="__next"',
        "ng-version=",
        "data-reactroot",
    )
    low = html
    hit = any(m in low for m in markers)
    social_markers = (
        "instagram.com",
        "t.me/",
        "telegram.me",
        "aparat.com",
        "linkedin.com",
        "facebook.com",
        "wa.me/",
        "youtube.com/",
        "x.com/",
        "twitter.com",
    )
    has_social = any(s in low.lower() for s in social_markers)
    return hit and not has_social


def _launch_browser(p):
    """
    اول Edge/Chrome سیستم (بدون دانلود)، بعد Chromium پلی‌رایت.
    در ایران CDN پلی‌رایت اغلب 403 می‌دهد.
    """
    last_err: Exception | None = None
    for channel in (config.playwright_channel, "msedge", "chrome", None):
        try:
            if channel:
                return p.chromium.launch(channel=channel, headless=True)
            return p.chromium.launch(headless=True)
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(
        f"هیچ مرورگری برای Playwright پیدا نشد ({last_err}). "
        "Edge یا Chrome را نصب کنید یا channel را در .env تنظیم کنید."
    )


def render_with_playwright(url: str, wait_ms: int | None = None) -> dict:
    """
    رندر کامل صفحه با مرورگر برای استخراج فوتر/شبکه‌های اجتماعی.
    فقط Public HTML نهایی — بدون login.
    """
    if not config.use_playwright:
        return {
            "ok": False,
            "status": 0,
            "url": url,
            "html": "",
            "error": "playwright disabled",
        }

    wait_ms = wait_ms if wait_ms is not None else config.playwright_wait_ms
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "ok": False,
            "status": 0,
            "url": url,
            "html": "",
            "error": "playwright not installed",
        }

    try:
        with sync_playwright() as p:
            browser = _launch_browser(p)
            context = browser.new_context(
                user_agent=config.browser_ua,
                locale="fa-IR",
                viewport={"width": 1365, "height": 900},
                ignore_https_errors=True,
            )
            page = context.new_page()
            page.set_default_timeout(max(config.fetch_timeout_ms, 25000))

            # بعضی سایت‌ها با Playwright قطع می‌شوند؛ www و networkidle را هم امتحان کن
            last_err: Exception | None = None
            html = ""
            final_url = url
            candidates = [url]
            if "://" in url and "://www." not in url:
                candidates.append(url.replace("://", "://www.", 1))

            for candidate in candidates:
                for wait_until in ("domcontentloaded", "commit"):
                    try:
                        page.goto(candidate, wait_until=wait_until)
                        try:
                            page.wait_for_selector(
                                "footer a[href*='instagram'], footer a[href*='t.me'], "
                                "a[href*='instagram.com'], a[aria-label*='Instagram' i], "
                                "a[href*='aparat.com'], a[href*='linkedin.com'], "
                                "a[href*='telegram']",
                                timeout=wait_ms,
                            )
                        except Exception:
                            page.wait_for_timeout(min(wait_ms, 5000))
                        page.evaluate(
                            "window.scrollTo(0, document.body.scrollHeight)"
                        )
                        page.wait_for_timeout(1200)
                        html = page.content()
                        final_url = page.url
                        last_err = None
                        break
                    except Exception as exc:
                        last_err = exc
                        continue
                if html:
                    break

            browser.close()
            if not html:
                return {
                    "ok": False,
                    "status": 0,
                    "url": url,
                    "html": "",
                    "error": str(last_err or "empty render"),
                }
            if len(html) > 2_000_000:
                html = html[:2_000_000]
            return {
                "ok": True,
                "status": 200,
                "url": final_url,
                "html": html,
                "rendered": True,
            }
    except Exception as exc:
        return {"ok": False, "status": 0, "url": url, "html": "", "error": str(exc)}
