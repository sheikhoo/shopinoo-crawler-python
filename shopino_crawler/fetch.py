from __future__ import annotations

import subprocess
import time
from functools import lru_cache
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from .config import config
from .normalize import normalize_domain


def _fetch_timeout() -> float:
    return max(config.fetch_timeout_ms / 1000.0, 3.0)


def _robots_timeout() -> float:
    # robots نباید کل کرال را hang کند
    return min(_fetch_timeout(), 6.0)


@lru_cache(maxsize=512)
def _parser_for(host: str) -> RobotFileParser | None:
    """
    robots.txt را با timeout می‌خواند.
    اگر در دسترس نبود / خطا → اجازه بده (None).
    """
    url = f"https://{host}/robots.txt"
    try:
        res = requests.get(
            url,
            headers={
                "User-Agent": config.user_agent,
                "Accept": "text/plain,*/*;q=0.8",
            },
            timeout=_robots_timeout(),
            allow_redirects=True,
        )
        if res.status_code >= 400 or not (res.text or "").strip():
            return None
        rp = RobotFileParser()
        rp.parse(res.text.splitlines())
        return rp
    except Exception:
        return None


def is_allowed(domain: str, path: str = "/") -> bool:
    host = normalize_domain(domain)
    if not host:
        return False
    rp = _parser_for(host)
    if rp is None:
        return True
    try:
        return rp.can_fetch(config.user_agent, path or "/")
    except Exception:
        return True


_host_last: dict[str, float] = {}


def _wait_host(host: str) -> None:
    last = _host_last.get(host, 0.0)
    wait = config.per_host_delay_ms / 1000.0 - (time.monotonic() - last)
    if wait > 0:
        time.sleep(wait)
    _host_last[host] = time.monotonic()


def _fetch_curl(url: str, timeout: float) -> dict:
    try:
        proc = subprocess.run(
            [
                "curl",
                "-sL",
                "-A",
                config.browser_ua,
                "--max-time",
                str(max(int(timeout), 3)),
                "--connect-timeout",
                "5",
                "-H",
                "Accept-Language: fa-IR,fa;q=0.9,en;q=0.5",
                url,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
            timeout=max(timeout + 5, 10),
        )
        html = proc.stdout or ""
        if proc.returncode != 0 or not html:
            return {
                "ok": False,
                "status": 0,
                "url": url,
                "html": "",
                "error": f"curl exit {proc.returncode}",
            }
        if len(html) > 1_500_000:
            html = html[:1_500_000]
        return {"ok": True, "status": 200, "url": url, "html": html, "via": "curl"}
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "status": 0,
            "url": url,
            "html": "",
            "error": "curl timeout",
        }
    except Exception as exc:
        return {"ok": False, "status": 0, "url": url, "html": "", "error": str(exc)}


def fetch_public(url: str, *, prefer_browser_ua: bool = False) -> dict:
    host = normalize_domain(urlparse(url).hostname or "")
    if host:
        _wait_host(host)

    timeout = _fetch_timeout()
    ua = config.browser_ua if prefer_browser_ua else config.user_agent
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
    }
    try:
        res = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )
        ctype = (res.headers.get("content-type") or "").lower()
        if res.status_code >= 400:
            # fallback curl برای بعضی CDN/SSL
            return _fetch_curl(url, timeout)
        if ctype and any(
            x in ctype for x in ("json", "image/", "octet", "pdf", "javascript")
        ):
            return {"ok": False, "status": res.status_code, "url": res.url, "html": ""}
        text = res.text or ""
        if len(text) > 1_500_000:
            text = text[:1_500_000]
        return {"ok": True, "status": res.status_code, "url": res.url, "html": text}
    except requests.RequestException:
        return _fetch_curl(url, timeout)
