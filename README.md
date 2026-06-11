# hsbc-hk-products-dashboard

An initial private scaffold for a Hong Kong public-products dashboard. This repo currently serves placeholder data only and does not log in, scrape authenticated pages, or implement a full parser.

## Disclaimer

- For research and prototyping only.
- Only publicly accessible pages should be accessed at low frequency and in line with the target site's published policies.
- Do not use this scaffold to bypass authentication, rate limits, or access controls.

## Project layout

- `app/main.py`: FastAPI app, web page, and API routes
- `app/scraper.py`: Playwright + BeautifulSoup placeholder scraper entrypoint
- `app/templates/index.html`: minimal dashboard page
- `app/static/style.css`: simple styling
- `data/products.json`: placeholder product dataset

## Quickstart

1. Create and activate a virtual environment:
   - macOS / Linux: `python3 -m venv .venv && source .venv/bin/activate`
2. Install Python dependencies:
   - `pip install -r requirements.txt`
3. Install the Playwright browser used by the scaffold:
   - `playwright install chromium`
4. Start the dashboard:
   - `uvicorn app.main:app --reload`
5. Open the app:
   - `http://127.0.0.1:8000`

## Available endpoints

- `GET /`: dashboard page
- `GET /health`: health status
- `GET /api/products`: returns placeholder data from `data/products.json`

## Current status

- Minimal runnable skeleton is in place.
- Product fetching currently returns placeholder data.
- Full parsing logic and any source-specific extraction are intentionally out of scope for this initialization commit.
