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
    if len(name) < 2 or is_generic_page_title(name):
        name = domain
    return name[:120]


_GENERIC_PAGE_TITLES = re.compile(
    r"^(?:"
    r"درباره\s*ما|درباره|تماس\s*با\s*ما|تماس|ارتباط\s*با\s*ما|"
    r"قوانین|حریم\s*خصوصی|سوالات\s*متداول|فاکتور|سبد\s*خرید|"
    r"ورود|ثبت\s*نام|حساب\s*کاربری|بلاگ|مقالات|محصولات|فروشگاه|"
    r"صفحه\s*اصلی|خانه|"
    r"about(?:\s*us)?|contact(?:\s*us)?|privacy(?:\s*policy)?|"
    r"terms(?:\s*&?\s*conditions)?|faq|blog|home|shop|products|"
    r"login|sign\s*up|cart|checkout"
    r")$",
    re.I,
)


def is_generic_page_title(name: str | None) -> bool:
    """عنوان‌هایی مثل «درباره ما» که نام فروشگاه نیستند."""
    cleaned = to_english_digits(name or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return True
    return bool(_GENERIC_PAGE_TITLES.match(cleaned))


_PERSIAN_CHAR = re.compile(r"[\u0600-\u06FF]")


def has_persian_text(html_or_text: str | None, *, min_chars: int = 25) -> bool:
    """اگر متن فارسی کافی نباشد، احتمالاً سایت ایرانی نیست."""
    if not html_or_text:
        return False
    # اسکریپت/استایل را ساده حذف کن تا نویز کمتر شود
    text = re.sub(
        r"(?is)<script[^>]*>.*?</script>|<style[^>]*>.*?</style>",
        " ",
        html_or_text,
    )
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    chars = _PERSIAN_CHAR.findall(text)
    return len(chars) >= min_chars
