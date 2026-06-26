# hsbc-hk-products-dashboard

A small **Hong Kong equities monitoring dashboard** — the page (`index.html` +
`assets/dashboard.css` + `assets/equities.js`) tracks a core watchlist of
popular HK tech stocks with live quotes, technical indicators, macro/micro
analysis, a server-side custom watchlist, and on-demand real-time queries.

Quotes are pulled from **multiple public data sources** with automatic
fallback — Yahoo Finance v8 *chart* endpoint (multi-host) → Tencent
`qt.gtimg.cn` → an embedded deterministic mock — so the dashboard shows live
prices instead of getting stuck on a stale snapshot. Run it via **FastAPI**
(`app/main.py`) to enable real-time single-stock queries and the custom
watchlist; the static page also works standalone (snapshot only).

> The retail time-deposit comparison table was removed from the dashboard UI.
> The deposit **scraper** (`app/scraper.py`) and its `data/products.json` are
> kept for reference and still power the legacy `GET /api/products` endpoint.

> ⚠️ **免责声明 / Disclaimer**
> 本看板数据**仅供研究参考，不构成任何投资建议**；行情可能延迟，上游不可用时会
> 展示回退 / mock 结果，**一切以交易所及券商官方实时报价为准**。
> Research and prototyping only. Verify against official exchange/broker quotes
> before any decision.

- Only publicly-accessible HSBC HK pages are accessed, at low frequency.
- **No login**, no authenticated endpoints, no user-specific quotes.
- This project must NOT be used to bypass authentication, rate limits, or
  access controls.

---

## Live demo (GitHub Pages)

After the included GitHub Actions workflow runs at least once on `main`, the
dashboard is published at:

```
https://<your-github-username>.github.io/hsbc-hk-products-dashboard/
```

See [GitHub Pages setup](#github-pages-setup) below for the one-time toggle.

---

## Project layout

```
.
├── index.html                  # HK equities dashboard (Pages root)
├── assets/
│   ├── dashboard.css           # styles
│   └── equities.js             # fetches hk_stocks.json + live API, renders watchlist
├── data/
│   ├── hk_stocks.json          # HK watchlist snapshot (overwritten on refresh)
│   ├── watchlist.json          # server-side custom stocks (created on first add)
│   └── products.json           # legacy scraped time-deposit dataset
├── app/
│   ├── main.py                 # FastAPI server — serves the dashboard + live API
│   ├── hk_stocks.py            # multi-source providers + indicator calculations
│   ├── scraper.py              # (legacy) scraper for the HSBC HK deposit-rate page
│   ├── templates/index.html    # (unused) legacy Jinja template
│   └── static/style.css        # (unused) legacy FastAPI styling
├── requirements.txt
└── .github/workflows/pages.yml # auto-deploys static site to GitHub Pages
```

The static dashboard at the **repo root** is what GitHub Pages serves. The
`app/` FastAPI scaffold is kept for local development; the static page is
the production deliverable.

---

## Quickstart

### 1. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
pip install -r requirements.txt
```

### 2. (Optional) Install Playwright browser binaries

The current scraper uses `urllib + bs4` and does **not** require Playwright,
but `playwright` is pinned in `requirements.txt` for future scrapers
(funds, structured products, etc.) that need a real browser. Install the
Chromium runtime once if you want it ready:

```bash
playwright install chromium
```

### 3. Run the scraper to refresh data

```bash
python -m app.scraper
```

This rewrites `data/products.json`. Exit code `0` on success; non-zero if
the page layout changed and zero entries were parsed.

### 4. Run the dashboard

**Recommended — FastAPI backend** (enables real-time single-stock queries and
the server-side custom watchlist):

```bash
uvicorn app.main:app --reload
# then open: http://127.0.0.1:8000
```

FastAPI serves the same static dashboard (`index.html` + `assets/` + `data/`)
and the live API. You should see the **core HK tech watchlist** (Tencent,
Alibaba, Meituan, Xiaomi, Kuaishou, JD.com, NetEase, Baidu, SMIC, Lenovo,
SenseTime, Sunny Optical, plus HSBC / China Mobile / AIA / Ping An) with
overview cards, macro/micro analysis, a sortable watchlist, per-stock metric
detail, an **添加自选股** form, and an **实时查询此股** button.

**Static only** (snapshot view, no real-time / custom watchlist — e.g. GitHub
Pages):

```bash
python -m http.server 8080
# then open: http://127.0.0.1:8080/
```

The page reads `data/hk_stocks.json`; the add-stock and real-time buttons are
disabled because they require the FastAPI backend.

### API endpoints

- `GET /` — the HK equities dashboard (static `index.html`)
- `GET /health` — `{"status": "ok"}`
- `GET /api/hk-stocks?refresh=<bool>` — watchlist snapshot (default + custom)
- `POST /api/hk-stocks/refresh` — force a fresh multi-source pull
- `GET /api/hk-stocks/quote?symbol=<code>` — on-demand real-time single quote
- `GET /api/watchlist` · `POST /api/watchlist` · `DELETE /api/watchlist/{symbol}`
  — read / add / remove custom stocks (persisted to `data/watchlist.json`)
- `GET /api/products` — legacy time-deposit dataset (`data/products.json`)

### Hong Kong stock watchlist payload

The watchlist payload (`/api/hk-stocks`) includes:

- latest price, absolute / percent change, volume, turnover value, turnover rate
- 30-day volatility, MA5/10/20/50, RSI(14), MACD, Bollinger Bands
- market cap, TTM PE, PB, TTM EPS, dividend yield when upstream fields exist
- `metadata.indicator_definitions` explanations and per-stock `risk_flags`

**Data sources (multi-source fallback chain):** Yahoo Finance v8 *chart*
endpoint (tried across multiple hosts; gives price + history → full technical
indicators) → Tencent `qt.gtimg.cn` (quote-only live fallback + TTM P/E
enrichment; `LIMITED_HISTORY` flag) → embedded deterministic mock
(`MOCK_DATA` / `DEV_FALLBACK` flags). Set `HK_STOCKS_PROVIDER=mock` to force
the mock, or `HK_STOCKS_PROVIDER=tencent` for quote-only live.

> **Dividend yield note:** `0.00%` means the company pays **no dividend** (a
> valid, known value — e.g. Meituan, Xiaomi), shown as `0.00%（不分红）`; `—`
> means the figure was unavailable upstream. Free live sources (Yahoo chart /
> Tencent) do not expose dividend yield, so live mode shows `—`; the curated
> mock data carries the worked dividend examples.

---

## GitHub Pages setup

This repo ships with `.github/workflows/pages.yml`, which builds and
deploys `index.html` + `assets/` + `data/products.json` to GitHub Pages
on every push to `main`. **One-time setup is required**:

1. On GitHub → **Settings → Pages**.
2. Under **Build and deployment → Source**, select **GitHub Actions**.
3. (Optional) Push any commit to `main` (or trigger the workflow via
   *Actions → Deploy static dashboard to GitHub Pages → Run workflow*) to
   produce the first deployment.

After the first successful run, the URL will be:

```
https://<your-github-username>.github.io/hsbc-hk-products-dashboard/
```

To keep data fresh, re-run `python -m app.scraper` and commit the updated
`data/products.json`. The workflow re-deploys automatically.

> If you prefer the classic *Deploy from a branch* mode instead, you can
> instead set **Source** to **Deploy from a branch**, branch = `main`,
> folder = `/ (root)` — the static site is already at repo root, so it
> works either way. The Actions workflow above is the recommended path
> because it gives you build logs and atomic deploys.

---

## Data shape (`data/products.json`)

```jsonc
{
  "source": "https://www.hsbc.com.hk/investments/market-information/hk/deposit-rate/",
  "disclaimer": "...",
  "fetched_at": "2026-06-13T09:11:13+00:00",
  "summary": { "count": 329, "currencies": [...], "tenors": [...] },
  "products": [
    {
      "category": "Time Deposit",
      "name": "HSBC HK Time Deposit (AUD, 1 week, AUD2,000 to AUD99,999)",
      "currency": "AUD",
      "tenor": "1 week",
      "rate": 0.15,
      "rate_unit": "percent_per_annum",
      "balance_band": "AUD2,000 to AUD99,999",
      "risk_level": "Low",
      "fee": "None",
      "source_url": "https://www.hsbc.com.hk/...",
      "fetched_at": "2026-06-13T09:11:13+00:00"
    }
  ]
}
```

The dashboard reads `products[]` and ignores any entries with missing
required fields.

---

## Current scope & non-goals

| Category                               | Status              | Reason                                                                                |
|----------------------------------------|---------------------|---------------------------------------------------------------------------------------|
| Time Deposit (retail)                  | ✅ covered (329 條) | Public, server-rendered HSBC HK page; no JS / login required.                         |
| Funds / Wealth Management              | ⛔ no data          | Listings need a logged-in client view; out of scope for an unauthenticated MVP.       |
| Structured Products / Bonds            | ⛔ no data          | Distribution is gated behind risk-assessment + auth flows; out of scope.              |
| FX / Precious Metals                   | ⛔ no data          | Live quotes come from authenticated streaming endpoints; out of scope.                |

The deposit **scraper** still covers time deposits only and does **not**
fabricate numbers for the other categories. (The deposit comparison table is
no longer rendered in the dashboard UI, but `python -m app.scraper` and
`GET /api/products` continue to work.)

---

## Endpoints

See [API endpoints](#api-endpoints) above for the full list. In short: `GET /`
serves the static HK equities dashboard, `GET /api/hk-stocks` (+ `?refresh=1`)
returns the watchlist snapshot, `GET /api/hk-stocks/quote?symbol=…` does a
real-time single-stock query, `GET|POST|DELETE /api/watchlist` manages custom
stocks, and `GET /api/products` returns the legacy deposit dataset.

---

## Production & operations

看板的运维 / 部署 / 数据语义 / 告警 / 风险说明都在 [`docs/`](docs/README.md) 下，**与业务 UI 解耦**：

- [`docs/hk-watchlist-production.md`](docs/hk-watchlist-production.md) — 港股观察池生产说明：数据源策略、宏观/微观分析框架、指标字典、alert 用法、环境变量、刷新频率、监控与降级。
- [`docs/metrics.md`](docs/metrics.md) — 指标字典：`data/products.json` 每个字段的语义、单位、合法范围、派生指标定义。
- [`docs/data-sources.md`](docs/data-sources.md) — 数据源策略、宏观/微观分层、未来 roadmap、何时不该接入新源。
- [`docs/alerts.md`](docs/alerts.md) — 抓取健康度 / 数据语义 / 站点可用性三类告警的轻量级配置方案（webhook、Healthchecks.io、GitHub Actions）。
- [`docs/deployment.md`](docs/deployment.md) — 生产部署 checklist、环境变量约定、部署目标矩阵、回滚流程。
- [`docs/observability.md`](docs/observability.md) — 监控 / 日志 / 故障降级路径（Level 0–5）、季度故障演练建议。
- [`docs/data-latency.md`](docs/data-latency.md) — 数据延迟来源拆解 + 标准免责声明文本（前端必须保留）。
- [`docs/trading-risk.md`](docs/trading-risk.md) — 为什么本看板**不能**驱动真实下单 / 真实交易决策。

> ⚠️ 上述文档**不是**投资建议、产品推荐或合规背书；任何关于 HSBC 产品的真实条款请以 HSBC 官网为准。

对于 `data/hk_stocks.json` / `/api/hk-stocks` 的生产接入，请至少先读：
`hk-watchlist-production.md` → `alerts.md` → `deployment.md` →
`observability.md` → `trading-risk.md`。其中明确约束了：

- 公共 Yahoo Finance 端点只作为**延迟、研究用途**的数据源；
- `HK_STOCKS_PROVIDER=mock` 或 live 拉取失败时会写入带 `MOCK_DATA` /
  `DEV_FALLBACK` 风险标记的快照；
- 所有 alert 只能陈述客观事实，**不得**包装成买卖建议或自动联动交易。
