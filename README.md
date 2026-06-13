# hsbc-hk-products-dashboard

A small Hong Kong public-products dashboard scaffold. The current scope is **time deposits only** — the scraper pulls publicly-listed HSBC HK retail time-deposit rates from a single market-information page and writes them to `data/products.json`. The FastAPI dashboard reads that file.

## Disclaimer

- Research and prototyping only.
- Only publicly accessible HSBC HK pages are accessed, at low frequency, and in line with the site's published policies.
- Do NOT use this project to bypass authentication, rate limits, or access controls.
- Rates change continuously. Always verify against the bank's official quote before any decision.

## Project layout

- `app/main.py` — FastAPI app, web page, and API routes.
- `app/scraper.py` — minimal scraper for the HSBC HK public deposit-rate page.
- `app/templates/index.html` — minimal dashboard page.
- `app/static/style.css` — simple styling.
- `data/products.json` — scraped time-deposit dataset (overwritten on each run).

## Quickstart

1. Create and activate a virtual environment:
   - macOS / Linux: `python3 -m venv .venv && source .venv/bin/activate`
2. Install Python dependencies:
   - `pip install -r requirements.txt`
3. Run the scraper to populate real data:
   - `python -m app.scraper`
4. (Optional) Start the dashboard:
   - `uvicorn app.main:app --reload`
   - Open `http://127.0.0.1:8000`

## Scraper

```
python -m app.scraper
```

The scraper:

- Fetches `https://www.hsbc.com.hk/investments/market-information/hk/deposit-rate/` (the public, server-rendered market-information page — no JS needed).
- Parses every `Time Deposit` table on the page (one per currency).
- Writes the results to `data/products.json`.

Each product entry contains:

- `category` (always `"Time Deposit"` in this iteration)
- `name`
- `currency` (e.g. `HKD`, `USD`, `CNY`, `EUR`, ...)
- `tenor` (e.g. `1 week`, `3 months`, `12 months`)
- `rate` (annualised percentage as a number, e.g. `0.15` means 0.15% p.a.)
- `rate_unit` (`percent_per_annum`)
- `balance_band` (the HSBC HK tier the rate applies to)
- `risk_level` (`Low` for retail time deposits)
- `fee` (`None` for these deposits)
- `source_url`
- `fetched_at` (ISO-8601 UTC timestamp)

Exit code `0` on success; non-zero if no entries could be parsed (a signal that the page layout has likely changed).

## Available endpoints

- `GET /` — dashboard page
- `GET /health` — health status
- `GET /api/products` — returns the contents of `data/products.json`

## Current status & non-goals

- Only HSBC HK retail **time deposits** are scraped.
- Funds, structured products, bonds, FX, and precious metals are intentionally **out of scope** for this iteration.
- No login, no authenticated endpoints, no user-specific quotes.
- No frontend dashboard polish beyond the existing minimal Jinja template.
- No GitHub Pages / hosting configuration.
