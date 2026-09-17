from __future__ import annotations

from typing import Any

import requests

from .config import config


def publish_business(payload: dict[str, Any]) -> dict[str, Any]:
    if not config.token:
        raise RuntimeError("CRAWLER_SERVICE_TOKEN تنظیم نشده است")

    # فقط فیلدهای عمومی مجاز
    body = {
        k: v
        for k, v in payload.items()
        if k
        in {
            "name",
            "canonicalDomain",
            "sourceUrl",
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
            "keywords",
            "categorySlug",
            "socialLinks",
            "fieldSources",
            "confidence",
        }
        and v is not None
    }

    res = requests.post(
        config.ingest_url,
        json=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.token}",
            "User-Agent": config.user_agent,
        },
        timeout=20,
    )
    data = {}
    try:
        data = res.json()
    except Exception:
        pass
    if not res.ok:
        msg = data.get("message") if isinstance(data, dict) else None
        if isinstance(msg, list):
            msg = ", ".join(str(x) for x in msg)
        raise RuntimeError(msg or f"HTTP {res.status_code}")
    return data if isinstance(data, dict) else {"ok": True}
