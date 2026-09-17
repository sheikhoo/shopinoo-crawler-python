"""استخراج URLهای سوشال از باندل‌های JS سایت (برای SPA/Next)."""
from __future__ import annotations

import re
import subprocess
from urllib.parse import urljoin

from .socials import extract_social_links
from .souputil import make_soup

SCRIPT_SRC_RE = re.compile(
    r"""(?:src|href)=["']([^"']+_next/static/[^"']+\.js[^"']*)["']""",
    re.I,
)


def _curl_get(url: str, timeout: int = 12) -> str:
    try:
        proc = subprocess.run(
            [
                "curl",
                "-sL",
                "-A",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0",
                "--max-time",
                str(timeout),
                "--connect-timeout",
                "5",
                url,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
            timeout=timeout + 5,
        )
        return proc.stdout or ""
    except Exception:
        return ""


def extract_script_urls(html: str, base_url: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    soup = make_soup(html)
    for script in soup.find_all("script", src=True):
        src = script.get("src") or ""
        if "_next/static" in src or "chunk" in src or "main" in src:
            abs_url = urljoin(base_url, src)
            if abs_url not in seen:
                seen.add(abs_url)
                urls.append(abs_url)
    for m in SCRIPT_SRC_RE.finditer(html or ""):
        abs_url = urljoin(base_url, m.group(1))
        if abs_url not in seen:
            seen.add(abs_url)
            urls.append(abs_url)
    # اولویت به chunkهایی که احتمال فوتر دارند
    def score(u: str) -> int:
        s = 0
        low = u.lower()
        for key in ("footer", "layout", "app", "main", "framework"):
            if key in low:
                s += 5
        return -s

    urls.sort(key=score)
    return urls[:25]


def harvest_socials_from_assets(html: str, base_url: str) -> list[dict[str, str]]:
    """
    وقتی HTML استاتیک سوشال ندارد، باندل‌های JS عمومی را برای URL شبکه‌ها اسکن کن.
    """
    found = extract_social_links(html, base_url)
    if found:
        return found

    scripts = extract_script_urls(html, base_url)[:8]
    blobs = [html]
    for src in scripts:
        body = _curl_get(src, timeout=10)
        if body:
            blobs.append(body)
            # اگر سوشال پیدا شد زودتر تمام کن
            hit = extract_social_links("\n".join(blobs), base_url)
            if hit:
                return hit

    combined = "\n".join(blobs)
    return extract_social_links(combined, base_url)
