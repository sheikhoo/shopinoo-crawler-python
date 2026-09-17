from __future__ import annotations

import re
from urllib.parse import urlparse

from .souputil import make_soup

# platform -> host fragments / keywords
SOCIAL_HOSTS: list[tuple[str, tuple[str, ...]]] = [
    ("instagram", ("instagram.com", "instagr.am")),
    ("telegram", ("t.me", "telegram.me", "telegram.org")),
    ("whatsapp", ("wa.me", "api.whatsapp.com", "whatsapp.com")),
    ("bale", ("ble.ir", "bale.ai")),
    ("eitaa", ("eitaa.com",)),
    ("rubika", ("rubika.ir",)),
    ("youtube", ("youtube.com", "youtu.be")),
    ("aparat", ("aparat.com",)),
    ("linkedin", ("linkedin.com",)),
    ("twitter", ("twitter.com", "x.com")),
    ("facebook", ("facebook.com", "fb.com", "fb.me")),
]

LABEL_MAP = [
    ("instagram", re.compile(r"instagram|اینستا|اینستاگرام", re.I)),
    ("telegram", re.compile(r"telegram|تلگرام|t\.me", re.I)),
    ("whatsapp", re.compile(r"whatsapp|واتس?\s*اپ|واتساپ", re.I)),
    ("aparat", re.compile(r"aparat|آپارات", re.I)),
    ("linkedin", re.compile(r"linkedin|لینکدین", re.I)),
    ("youtube", re.compile(r"youtube|یوتیوب", re.I)),
    ("twitter", re.compile(r"twitter|\bx\b|توییتر", re.I)),
    ("facebook", re.compile(r"facebook|فیس\s*بوک", re.I)),
    ("bale", re.compile(r"\bbale\b|بله", re.I)),
    ("eitaa", re.compile(r"eitaa|ایتا", re.I)),
    ("rubika", re.compile(r"rubika|روبیکا", re.I)),
]


def _platform_from_url(url: str) -> str | None:
    try:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return None
    for platform, hosts in SOCIAL_HOSTS:
        if any(host == h or host.endswith("." + h) or h in host for h in hosts):
            return platform
    return None


def _platform_from_label(blob: str) -> str | None:
    for platform, rx in LABEL_MAP:
        if rx.search(blob):
            return platform
    return None


def _normalize_social_url(url: str) -> str:
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    if not re.match(r"^https?://", url, re.I):
        # بعضی سایت‌ها فقط مسیر نسبی به سوشال ندارند؛ رد کن
        if "instagram.com" in url or "t.me" in url:
            url = "https://" + url.lstrip("/")
        else:
            return url
    return url.split("#")[0].rstrip("/")


def non_website_socials(links: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """لینک‌هایی غیر از خود وب‌سایت فروشگاه (اینستا، تلگرام، …)."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for link in links or []:
        platform = str(link.get("platform") or "").strip().lower()
        url = str(link.get("url") or "").strip()
        if not platform or not url:
            continue
        if platform in {"website", "web", "site"}:
            continue
        key = f"{platform}:{url}"
        if key in seen:
            continue
        seen.add(key)
        out.append(link)
    return out


def extract_social_links(html: str, base_url: str = "") -> list[dict[str, str]]:
    """
    استخراج هوشمند شبکه‌های اجتماعی از:
    - href مستقیم
    - aria-label / title / class
    - متن لینک
    - regex روی کل HTML (برای JSON/RSC)
    """
    soup = make_soup(html)
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(platform: str | None, url: str | None) -> None:
        if not platform or not url:
            return
        url = _normalize_social_url(url)
        if not url.startswith("http"):
            return
        # فقط دامنه سوشال واقعی
        if not _platform_from_url(url):
            # اگر از label آمده ولی url داخلی است رد کن
            return
        key = f"{platform}:{url.lower()}"
        if key in seen:
            return
        seen.add(key)
        found.append({"platform": platform, "url": url})

    # ۱) همه <a>
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        blob = " ".join(
            filter(
                None,
                [
                    href,
                    a.get_text(" ", strip=True),
                    a.get("aria-label"),
                    a.get("title"),
                    a.get("data-network"),
                    a.get("data-social"),
                    " ".join(a.get("class") or []),
                ],
            )
        )
        platform = _platform_from_url(href) or _platform_from_label(blob)
        if platform and _platform_from_url(href):
            add(platform, href)

    # ۲) دکمه/آیکن با data-href
    for el in soup.find_all(attrs={"data-href": True}):
        href = el.get("data-href")
        platform = _platform_from_url(str(href)) or _platform_from_label(
            str(el.get("aria-label") or el.get("class") or "")
        )
        add(platform, str(href) if href else None)

    # ۳) regex روی کل سند (پوشش Next.js RSC / JSON)
    url_re = re.compile(
        r"https?://(?:www\.)?(?:"
        r"instagram\.com/[A-Za-z0-9_./?-]+|"
        r"(?:t\.me|telegram\.me)/[A-Za-z0-9_/?-]+|"
        r"(?:wa\.me|api\.whatsapp\.com)/[A-Za-z0-9+/=?&\-._%~]+|"
        r"(?:ble\.ir|bale\.ai)/[A-Za-z0-9_/?-]+|"
        r"eitaa\.com/[A-Za-z0-9_/?-]+|"
        r"rubika\.ir/[A-Za-z0-9_/?-]+|"
        r"(?:youtube\.com|youtu\.be)/[A-Za-z0-9_/@?=&\-]+|"
        r"aparat\.com/[A-Za-z0-9_/?-]+|"
        r"linkedin\.com/[A-Za-z0-9_/?-]+|"
        r"(?:twitter\.com|x\.com)/[A-Za-z0-9_/?-]+|"
        r"(?:facebook\.com|fb\.com)/[A-Za-z0-9_./?-]+"
        r")",
        re.I,
    )
    for m in url_re.findall(html or ""):
        # unescape json slashes
        url = m.replace("\\/", "/").replace("\\u002F", "/")
        add(_platform_from_url(url), url)

    return found
