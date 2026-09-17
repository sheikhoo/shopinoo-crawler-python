from __future__ import annotations

import re
from urllib.parse import urlparse

from .normalize import absolute_url, normalize_domain
from .souputil import make_soup

DEFAULT_INFO_PATHS = [
    "/",
    "/contact",
    "/contact-us",
    "/contactus",
    "/contactUs",
    "/ContactUs",
    "/contact_us",
    "/about",
    "/about-us",
    "/aboutus",
    "/aboutUs",
    "/AboutUs",
    "/about_us",
    "/content/contact",
    "/content/about",
    "/pages/contact",
    "/pages/about",
    "/page/contact",
    "/page/about",
    "/fa/contact",
    "/fa/about",
    "/fa/contact-us",
    "/fa/about-us",
    "/support",
    "/support/contact",
    "/help/contact",
    "/%D8%AA%D9%85%D8%A7%D8%B3-%D8%A8%D8%A7-%D9%85%D8%A7",
    "/%D8%AF%D8%B1%D8%A8%D8%A7%D8%B1%D9%87-%D9%85%D8%A7",
    "/تماس-با-ما",
    "/درباره-ما",
    "/ارتباط-با-ما",
]

CONTACT_TEXT = re.compile(
    r"تماس\s*با\s*ما|ارتباط\s*با\s*ما|پشتیبانی|contact(\s*us)?|support",
    re.I,
)
ABOUT_TEXT = re.compile(
    r"درباره\s*ما|about(\s*us)?|who\s*we\s*are|آشنایی",
    re.I,
)
CONTACT_HREF = re.compile(r"contact|tamas|support|ارتباط|تماس", re.I)
ABOUT_HREF = re.compile(r"about|darbare|درباره", re.I)


def _score_link(text: str, href: str, path: str, kind: str) -> int:
    score = 0
    blob = f"{text} {href} {path}".lower()
    if kind == "contact":
        if CONTACT_TEXT.search(text):
            score += 50
        if CONTACT_HREF.search(href) or CONTACT_HREF.search(path):
            score += 30
        if "footer" in blob:
            score += 5
    else:
        if ABOUT_TEXT.search(text):
            score += 50
        if ABOUT_HREF.search(href) or ABOUT_HREF.search(path):
            score += 30
    # مسیرهای کوتاه‌تر معمولاً صفحهٔ اصلی تماس هستند
    if path.count("/") <= 2:
        score += 10
    if re.search(r"(login|cart|product|blog|mag|category)", path, re.I):
        score -= 40
    return score


def find_info_links_from_homepage(html: str, page_url: str) -> dict[str, list[str]]:
    soup = make_soup(html)
    host = normalize_domain(urlparse(page_url).hostname or "")
    contact: list[tuple[int, str]] = []
    about: list[tuple[int, str]] = []

    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        abs_url = absolute_url(page_url, href)
        if not abs_url:
            continue
        try:
            parsed = urlparse(abs_url)
            if normalize_domain(parsed.hostname) != host:
                continue
            path = parsed.path or "/"
            if path in {"/", ""} or len(path) < 2:
                continue
            text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
            clean = abs_url.split("#", 1)[0]
            c_score = _score_link(text, href, path, "contact")
            a_score = _score_link(text, href, path, "about")
            if c_score >= 30:
                contact.append((c_score, clean))
            if a_score >= 30:
                about.append((a_score, clean))
        except Exception:
            continue

    contact.sort(key=lambda x: -x[0])
    about.sort(key=lambda x: -x[0])

    def uniq(items: list[tuple[int, str]], limit: int = 4) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for _, u in items:
            key = re.sub(r"/+$", "", u)
            if key in seen:
                continue
            seen.add(key)
            out.append(u)
            if len(out) >= limit:
                break
        return out

    return {"contact": uniq(contact), "about": uniq(about)}


def build_crawl_targets(
    domain: str,
    homepage_html: str,
    homepage_url: str,
    max_pages: int,
) -> list[str]:
    host = normalize_domain(domain)
    home = homepage_url or f"https://{host}/"
    urls: list[str] = []
    seen: set[str] = set()

    def add(url: str | None) -> None:
        if not url:
            return
        try:
            parsed = urlparse(url)
            if normalize_domain(parsed.hostname) != host:
                return
            key = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/") or parsed.netloc
            if key in seen:
                return
            seen.add(key)
            urls.append(parsed.geturl())
        except Exception:
            return

    add(home)
    if homepage_html:
        found = find_info_links_from_homepage(homepage_html, home)
        for u in found["contact"] + found["about"]:
            add(u)
    for path in DEFAULT_INFO_PATHS:
        if path == "/":
            continue
        add(absolute_url(home, path))

    return urls[: max(1, max_pages)]


def classify_page_kind(url: str) -> str:
    path = (urlparse(url).path or "/").lower()
    if CONTACT_HREF.search(path):
        return "contact"
    if ABOUT_HREF.search(path):
        return "about"
    if path in {"/", ""}:
        return "home"
    return "other"
