# Shopino Crawler (Python)

نسخهٔ پایتون خزندهٔ شاپینو با استخراج **هوشمندتر** از اطلاعات عمومی کسب‌وکارها.

با `shopino-crawler` (Node) هم‌راستا است و به همان Ingest API می‌فرستد:
`POST /api/internal/ingest/businesses`

## تفاوت‌های هوشمند نسبت به نسخه Node

- نرمال‌سازی ارقام فارسی/عربی
- پاک‌سازی هوشمند نام فروشگاه
- امتیازدهی لینک‌های تماس/درباره از صفحه اول
- انتخاب بهترین مقدار هر فیلد بر اساس confidence + نوع صفحه (contact/about/home)
- استخراج JSON-LD + microdata (`itemprop`)
- حدس دسته‌بندی از متن فارسی
- **رندر Playwright** برای سایت‌های Next.js/SPA که فوتر و سوشال را با JS می‌سازند (مثل خانومی)
- استخراج سوشال از `href` + `aria-label` + JSON داخل HTML

## نصب

```bash
cd shopino-crawler-python
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
# ترجیحاً از Edge/Chrome سیستم استفاده می‌شود (PLAYWRIGHT_CHANNEL=msedge)
# اگر خواستید Chromium جدا: playwright install chromium
cp .env.example .env
# CRAWLER_SERVICE_TOKEN را با بک‌اند یکی کنید
```

## اجرا

```bash
python -m shopino_crawler
python -m shopino_crawler --discover-only
python -m shopino_crawler --seed-only
```

## Seedها

همان منطق Node:

| فایل | نقش |
|------|-----|
| `seeds/shops.csv` | دامنه‌های اولیه |
| `seeds/directories.csv` | صفحات فهرست برای کشف لینک |

## اصول

- فقط Public Business Data
- احترام به robots.txt
- Rate limit per host
- User-Agent: `ShopinoBot/1.0 (+https://shopinoo-plus.ir/bot)`
- بدون login و بدون دور زدن دسترسی
- سایت ایگنور/ردشده: لینک‌های داخلش کشف و صف نمی‌شوند
