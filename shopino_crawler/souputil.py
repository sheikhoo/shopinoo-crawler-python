from __future__ import annotations

from bs4 import BeautifulSoup


def make_soup(html: str | None) -> BeautifulSoup:
    """همیشه html.parser — وابستگی به lxml لازم نیست و روی ویندوز کمتر می‌ترکد."""
    return BeautifulSoup(html or "", "html.parser")
