from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from .normalize import (
    absolute_url,
    clean_shop_name,
    normalize_phone,
    to_english_digits,
)
from .pages import classify_page_kind
from .socials import extract_social_links
from .souputil import make_soup


PHONE_RE = re.compile(
    r"(?:(?:\+98|0098|98|0)?9\d{9})|(?:0\d{2,3}[\s\-]?\d{3,4}[\s\-]?\d{4})"
)
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

CITY_HINTS = [
    "تهران",
    "مشهد",
    "اصفهان",
    "شیراز",
    "تبریز",
    "کرج",
    "اهواز",
    "قم",
    "کرمان",
    "رشت",
    "همدان",
    "یزد",
    "ارومیه",
    "کرمانشاه",
    "زاهدان",
    "اردبیل",
    "بندرعباس",
    "قزوین",
    "زنجان",
    "ساری",
]

CATEGORY_HINTS: list[tuple[str, list[str]]] = [
    ("fashion", ["پوشاک", "لباس", "مد", "کفش", "کیف", "استایل", "مردانه", "زنانه"]),
    ("beauty", ["آرایشی", "بهداشتی", "زیبایی", "عطر", "مراقبت پوست"]),
    ("digital", ["موبایل", "لپ‌تاپ", "لپ تاپ", "دیجیتال", "الکترونیک", "گوشی", "تبلت"]),
    ("book", ["کتاب", "نشر", "رمان", "کتابفروشی"]),
    ("food", ["خوراک", "مواد غذایی", "سوپرمارکت", "رستوران", "غذا"]),
    ("home", ["خانه", "آشپزخانه", "دکوراسیون", "مبلمان"]),
    ("sport", ["ورزش", "فیتنس", "کوهنوردی"]),
    ("kids", ["کودک", "نوزاد", "اسباب بازی"]),
]


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content") and str(tag["content"]).strip():
            return str(tag["content"]).strip()
    return None


def _parse_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            blocks.extend(x for x in data if isinstance(x, dict))
        elif isinstance(data, dict):
            if isinstance(data.get("@graph"), list):
                blocks.extend(x for x in data["@graph"] if isinstance(x, dict))
            else:
                blocks.append(data)
    return blocks


def _from_json_ld(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for b in blocks:
        raw_type = b.get("@type", "")
        if isinstance(raw_type, list):
            type_s = " ".join(str(x) for x in raw_type).lower()
        else:
            type_s = str(raw_type).lower()
        if not any(k in type_s for k in ("organization", "localbusiness", "store", "onlinebusiness")):
            continue
        if b.get("name"):
            out["name"] = str(b["name"])
        if b.get("description"):
            out["description"] = str(b["description"])
        if b.get("telephone"):
            out["phone"] = normalize_phone(str(b["telephone"]))
        if b.get("email"):
            out["email"] = str(b["email"])
        logo = b.get("logo")
        if isinstance(logo, str):
            out["logo"] = logo
        elif isinstance(logo, dict) and logo.get("url"):
            out["logo"] = str(logo["url"])
        image = b.get("image")
        if isinstance(image, str):
            out["image"] = image
        elif isinstance(image, dict) and image.get("url"):
            out["image"] = str(image["url"])
        elif isinstance(image, list) and image:
            first = image[0]
            out["image"] = first if isinstance(first, str) else str((first or {}).get("url") or "")
        addr = b.get("address")
        if isinstance(addr, str):
            out["address"] = addr
        elif isinstance(addr, dict):
            out["address"] = "، ".join(
                filter(
                    None,
                    [
                        addr.get("streetAddress"),
                        addr.get("addressLocality"),
                        addr.get("addressRegion"),
                    ],
                )
            )
            if addr.get("addressLocality"):
                out["city"] = str(addr["addressLocality"])
            if addr.get("addressRegion"):
                out["province"] = str(addr["addressRegion"])
    return out


def _itemprop(soup: BeautifulSoup, prop: str) -> str | None:
    el = soup.find(attrs={"itemprop": prop})
    if not el:
        return None
    if el.get("content"):
        return str(el["content"]).strip()
    if el.name == "a" and el.get("href"):
        href = str(el["href"])
        if href.startswith("tel:"):
            return href.replace("tel:", "")
        if href.startswith("mailto:"):
            return href.replace("mailto:", "").split("?", 1)[0]
        return href
    text = el.get_text(" ", strip=True)
    return text or None


def _guess_category(text: str) -> str | None:
    lower = text.lower()
    best: tuple[int, str] | None = None
    for slug, words in CATEGORY_HINTS:
        hits = sum(1 for w in words if w.lower() in lower or w in text)
        if hits and (best is None or hits > best[0]):
            best = (hits, slug)
    return best[1] if best and best[0] >= 1 else None


def _page_bonus(kind: str, field: str) -> float:
    """صفحه تماس برای تلفن/ایمیل/آدرس ارزش بیشتری دارد."""
    if kind == "contact" and field in {"phone", "email", "address", "city"}:
        return 0.15
    if kind == "about" and field in {"description", "name"}:
        return 0.1
    if kind == "home" and field in {"logo", "coverImage", "name"}:
        return 0.05
    return 0.0


def extract_public_business(html: str, page_url: str, domain: str) -> dict[str, Any]:
    soup = make_soup(html)
    kind = classify_page_kind(page_url)
    body = soup.body or soup
    text = to_english_digits(body.get_text(" ", strip=True))[:80000]
    json_ld = _from_json_ld(_parse_json_ld(soup))

    title = (
        _meta(soup, "og:site_name")
        or _meta(soup, "application-name")
        or (soup.title.get_text(strip=True) if soup.title else None)
        or json_ld.get("name")
        or domain
    )
    # اگر title طولانی سئو است و og:site_name نبود، نام کوتاه‌تر از JSON-LD یا دامنه
    if title and len(title) > 40 and json_ld.get("name"):
        title = str(json_ld["name"])
    description = (
        _meta(soup, "og:description", "description", "twitter:description")
        or json_ld.get("description")
        or _itemprop(soup, "description")
    )
    og_image = _meta(soup, "og:image", "twitter:image")
    favicon_href = None
    icon = soup.find("link", rel=lambda v: v and "icon" in str(v).lower())
    if icon and icon.get("href"):
        favicon_href = icon["href"]
    favicon = absolute_url(page_url, favicon_href or "/favicon.ico")

    logo = absolute_url(page_url, json_ld.get("logo"))
    if not logo:
        logo_el = (
            soup.select_one("header img")
            or soup.select_one(".logo img")
            or soup.find("img", alt=re.compile(r"logo", re.I))
            or soup.find("img", class_=re.compile(r"logo", re.I))
        )
        if logo_el and logo_el.get("src"):
            logo = absolute_url(page_url, logo_el["src"])

    cover = absolute_url(page_url, og_image or json_ld.get("image"))

    tel_hrefs = [
        a["href"].replace("tel:", "")
        for a in soup.select('a[href^="tel:"]')
        if a.get("href")
    ]
    mailtos = [
        a["href"].replace("mailto:", "").split("?", 1)[0]
        for a in soup.select('a[href^="mailto:"]')
        if a.get("href")
    ]

    phones: list[str] = []
    for raw in tel_hrefs + PHONE_RE.findall(text) + [json_ld.get("phone"), _itemprop(soup, "telephone")]:
        p = normalize_phone(raw if isinstance(raw, str) else None)
        if p and p not in phones:
            phones.append(p)

    emails: list[str] = []
    for raw in mailtos + EMAIL_RE.findall(text) + [json_ld.get("email"), _itemprop(soup, "email")]:
        if not raw:
            continue
        e = str(raw).strip().lower()
        if re.search(r"example\.|test@|sentry|wixpress|cloudflare|noreply", e):
            continue
        if e not in emails:
            emails.append(e)

    socials = extract_social_links(html or "", page_url)

    city = json_ld.get("city") or _itemprop(soup, "addressLocality")
    if not city:
        city = next((c for c in CITY_HINTS if c in text), None)

    address = json_ld.get("address") or _itemprop(soup, "address")
    if not address:
        m = re.search(r"(?:آدرس|address)\s*[:：]?\s*([^\n.]{10,120})", text, re.I)
        if m:
            address = m.group(1).strip()

    hours = None
    hm = re.search(
        r"(?:ساعات?\s*کاری|ساعت\s*کاری|working\s*hours?)\s*[:：]?\s*([^\n.]{5,80})",
        text,
        re.I,
    )
    if hm:
        hours = hm.group(1).strip()

    name = clean_shop_name(json_ld.get("name") or title, domain)
    category_hint = _guess_category(f"{name} {description or ''} {text[:2000]}")

    now = datetime.now(timezone.utc).isoformat()
    field_sources: dict[str, Any] = {}

    def mark(field: str, value: Any, source: str, confidence: float) -> None:
        if value is None or value == "":
            return
        conf = min(1.0, confidence + _page_bonus(kind, field))
        field_sources[field] = {
            "value": str(value),
            "source": source,
            "url": page_url,
            "confidence": round(conf, 3),
            "extractedAt": now,
            "pageKind": kind,
        }

    mark("name", name, "json-ld" if json_ld.get("name") else "html-title", 0.85)
    mark("description", description, "meta", 0.7)
    mark("logo", logo, "json-ld" if json_ld.get("logo") else "html", 0.75)
    mark("coverImage", cover, "og", 0.7)
    mark("faviconUrl", favicon, "html", 0.9)
    mark("phone", phones[0] if phones else None, "tel-link" if tel_hrefs else "regex", 0.8)
    mark("email", emails[0] if emails else None, "mailto" if mailtos else "regex", 0.8)
    mark("address", address, "json-ld" if json_ld.get("address") else "regex", 0.6)
    mark("city", city, "json-ld" if json_ld.get("city") else "heuristic", 0.55)
    mark("categoryHint", category_hint, "heuristic", 0.45)

    return {
        "name": name,
        "description": (description or "")[:2000] or None,
        "logo": logo,
        "coverImage": cover,
        "faviconUrl": favicon,
        "phone": phones[0] if phones else None,
        "email": emails[0] if emails else None,
        "address": (address or "")[:300] or None,
        "city": city,
        "province": json_ld.get("province"),
        "workingHoursNote": hours,
        "categoryHint": category_hint,
        "socialLinks": socials,
        "fieldSources": field_sources,
        "confidence": 0.85 if name and domain else 0.3,
        "pageKind": kind,
        "pageUrl": page_url,
    }


def merge_extractions(
    parts: list[dict[str, Any]],
    domain: str,
    source_url: str,
) -> dict[str, Any]:
    """ادغام هوشمند: برای هر فیلد بهترین confidence را انتخاب کن."""
    merged: dict[str, Any] = {
        "name": "",
        "canonicalDomain": domain,
        "sourceUrl": source_url,
        "socialLinks": [],
        "fieldSources": {},
        "confidence": 0.0,
    }
    social_seen: set[str] = set()
    best: dict[str, tuple[float, Any, dict[str, Any]]] = {}

    fields = [
        "name",
        "description",
        "logo",
        "coverImage",
        "faviconUrl",
        "phone",
        "email",
        "address",
        "city",
        "province",
        "workingHoursNote",
        "categoryHint",
    ]

    for part in parts:
        if not part:
            continue
        sources = part.get("fieldSources") or {}
        for field in fields:
            value = part.get(field)
            if not value:
                continue
            meta = sources.get(field) or {}
            conf = float(meta.get("confidence") or part.get("confidence") or 0.5)
            prev = best.get(field)
            if prev is None or conf > prev[0]:
                best[field] = (conf, value, meta)

        for link in part.get("socialLinks") or []:
            key = f"{link.get('platform')}:{link.get('url')}"
            if key in social_seen:
                continue
            social_seen.add(key)
            merged["socialLinks"].append(link)

        merged["confidence"] = max(merged["confidence"], float(part.get("confidence") or 0))

    for field, (_conf, value, meta) in best.items():
        merged[field] = value
        if meta:
            merged["fieldSources"][field] = meta

    if not merged.get("name"):
        merged["name"] = domain

    # categorySlug فقط اگر ingest پشتیبانی کند — به‌صورت hint در keywords هم بفرست
    hint = merged.pop("categoryHint", None)
    if hint:
        merged["keywords"] = list({hint, *(merged.get("keywords") or [])})[:10]
        # اگر بک‌اند categorySlug داشته باشد می‌تواند استفاده کند
        merged["categorySlug"] = hint

    # پاکسازی None
    return {k: v for k, v in merged.items() if v is not None}
