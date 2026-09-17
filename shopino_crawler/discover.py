from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from .normalize import normalize_domain
from .souputil import make_soup

BLOCKLIST = {
    "google.com",
    "google.ir",
    "youtube.com",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "t.me",
    "telegram.me",
    "telegram.org",
    "whatsapp.com",
    "wa.me",
    "linkedin.com",
    "aparat.com",
    "rubika.ir",
    "eitaa.com",
    "ble.ir",
    "bale.ai",
    "github.com",
    "gitlab.com",
    "cloudflare.com",
    "jsdelivr.net",
    "unpkg.com",
    "npmjs.com",
    "w3.org",
    "schema.org",
    "wikipedia.org",
    "wikimedia.org",
    "microsoft.com",
    "apple.com",
    "amazon.com",
    "cdninstagram.com",
    "fbcdn.net",
    "gstatic.com",
    "googleapis.com",
    "doubleclick.net",
    "googletagmanager.com",
    "google-analytics.com",
    "shopinoo-plus.ir",
    "shopinoo.ir",
    "enamad.ir",
    "samandehi.ir",
    "zarinpal.com",
    "idpay.ir",
    "pay.ir",
    "nextpay.ir",
    "aftership.com",
    "shoprank.com",
}

ALLOWED_TLDS = {"ir", "com", "net", "org", "shop", "store", "online", "co"}


def is_shop_candidate(domain: str | None) -> bool:
    host = normalize_domain(domain)
    if not host:
        return False
    if host in BLOCKLIST:
        return False
    for bad in BLOCKLIST:
        if host == bad or host.endswith("." + bad):
            return False
    if host.endswith((".gov.ir", ".ac.ir", ".sch.ir", ".edu")):
        return False
    if re.match(r"^(cdn|static|assets|img|image|media|api|ws|mail)\.", host, re.I):
        return False
    tld = host.rsplit(".", 1)[-1]
    return tld in ALLOWED_TLDS


def discover_domains_from_html(
    html: str,
    *,
    max_domains: int = 80,
    current_host: str | None = None,
    base_url: str | None = None,
) -> list[str]:
    found: set[str] = set()
    current = normalize_domain(current_host)

    def add(host: str | None) -> None:
        h = normalize_domain(host)
        if not h or h == current:
            return
        if is_shop_candidate(h):
            found.add(h)

    try:
        soup = make_soup(html)
        for a in soup.find_all("a", href=True):
            if len(found) >= max_domains:
                break
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            try:
                if href.startswith("//"):
                    abs_url = "https:" + href
                elif not re.match(r"^https?://", href, re.I):
                    if not base_url:
                        continue
                    abs_url = urljoin(base_url, href)
                else:
                    abs_url = href
                add(urlparse(abs_url).hostname)
            except Exception:
                continue
    except Exception:
        pass

    if len(found) < max_domains:
        for m in re.finditer(
            r"https?://((?:[a-z0-9-]+\.)+[a-z]{2,})", html or "", re.I
        ):
            add(m.group(1))
            if len(found) >= max_domains:
                break

    return list(found)
