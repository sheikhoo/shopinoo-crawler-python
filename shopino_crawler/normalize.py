from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def to_english_digits(text: str) -> str:
    return str(text or "").translate(_PERSIAN_DIGITS)


def normalize_domain(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    try:
        host = urlparse(raw).hostname or ""
    except Exception:
        host = raw.split("/")[0].split("?")[0]
    host = host.removeprefix("www.").rstrip(".")
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", host, re.I):
        return ""
    return host


def absolute_url(base: str, href: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return None
    try:
        return urljoin(base, href)
    except Exception:
        return None


def normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", to_english_digits(raw))
    if digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    if digits.startswith("9") and len(digits) == 10:
        digits = "0" + digits
    if re.fullmatch(r"09\d{9}", digits):
        return digits
    if 8 <= len(digits) <= 11:
        return digits
    return None


def clean_shop_name(raw: str | None, domain: str) -> str:
    name = to_english_digits(raw or "").strip()
    # جداکننده عنوان سایت
    name = re.split(r"\s*[|\-–—·•]\s*", name, maxsplit=1)[0].strip()
    # پسوندهای رایج فارسی/انگلیسی
    junk = [
        r"فروشگاه\s*اینترنتی",
        r"فروشگاه\s*آنلاین",
        r"آنلاین\s*شاپ",
        r"online\s*shop",
        r"official\s*website",
        r"وب\s*سایت\s*رسمی",
        r"صفحه\s*اصلی",
        r"home\s*page",
        r"^خرید\s+",
    ]
    for pat in junk:
        name = re.sub(pat, " ", name, flags=re.I).strip()
    name = re.sub(r"\s+", " ", name).strip(" -–—|·•")
    if len(name) < 2:
        name = domain
    return name[:120]
