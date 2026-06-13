"""Minimal scraper for HSBC HK *public* time-deposit rates.

Source: https://www.hsbc.com.hk/investments/market-information/hk/deposit-rate/
The page is server-rendered (no JS required); we use urllib + BeautifulSoup so
this module has no runtime dependencies beyond what is already pinned in
requirements.txt (bs4) and the Python standard library.

Run:
    python -m app.scraper

It writes the result to ``data/products.json`` next to the project root.

Scope: time deposits only. Funds, structured products, bonds, FX, precious
metals are intentionally NOT touched in this iteration.

Disclaimer: This script accesses one publicly accessible HSBC HK page once per
invocation. Do not call it at high frequency, and do not use it to bypass any
authentication, rate limiting, or access controls.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup

SOURCE_URL = (
    "https://www.hsbc.com.hk/investments/market-information/hk/deposit-rate/"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT_SECONDS = 30
MAX_PLAUSIBLE_RATE_PCT = 30.0  # any > 30% p.a. is treated as parsing noise

# Currencies HSBC HK currently lists time-deposit rates for. Used to detect
# the currency of a balance-band header column such as "HKD10,000 to HKD99,999".
KNOWN_CURRENCIES = (
    "HKD", "USD", "CNY", "RMB", "EUR", "GBP", "AUD",
    "JPY", "CAD", "NZD", "SGD", "CHF",
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "products.json"


def fetch_html(url: str = SOURCE_URL, *, timeout: int = HTTP_TIMEOUT_SECONDS) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        if resp.status != 200:
            raise RuntimeError(f"unexpected HTTP {resp.status} for {url}")
        return resp.read().decode("utf-8", errors="replace")


def _detect_currency(header: str) -> str | None:
    """Return the 3-letter currency code embedded in a balance-band header."""
    upper = header.upper()
    for ccy in KNOWN_CURRENCIES:
        if ccy in upper:
            # HSBC HK shows CNY balances under the "RMB" label in some tables;
            # normalise both to "CNY" for consistency in downstream consumers.
            return "CNY" if ccy == "RMB" else ccy
    return None


_RATE_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*%\s*$")


def _parse_rate(cell: str) -> float | None:
    match = _RATE_RE.match(cell)
    if not match:
        return None
    value = float(match.group(1))
    if value < 0 or value > MAX_PLAUSIBLE_RATE_PCT:
        return None
    return value


def _is_clean_time_deposit_table(headers: list[str]) -> bool:
    """The page renders some tables twice (desktop + mobile layout glued together).

    Mobile-glued tables repeat the "Deposit Period" header column. Filter to the
    clean tables only.
    """
    if not headers or headers[0].strip().lower() != "deposit period":
        return False
    period_count = sum(
        1 for h in headers if h.strip().lower() == "deposit period"
    )
    return period_count == 1


def parse_time_deposits(html: str, *, source_url: str = SOURCE_URL) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results: list[dict] = []

    for table in soup.find_all("table"):
        caption_el = table.find("caption")
        caption = caption_el.get_text(" ", strip=True) if caption_el else ""
        if "time deposit" not in caption.lower():
            continue

        headers = [
            th.get_text(" ", strip=True)
            for th in table.find_all("th")
        ]
        if not _is_clean_time_deposit_table(headers):
            continue

        # Header[0] is "Deposit Period"; subsequent headers are balance bands.
        balance_bands = headers[1:]
        currency = next(
            (c for c in (_detect_currency(b) for b in balance_bands) if c),
            None,
        )
        if not currency:
            continue

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            tenor = cells[0].get_text(" ", strip=True)
            if not tenor or tenor.lower() == "deposit period":
                continue
            for band, cell in zip(balance_bands, cells[1:]):
                rate = _parse_rate(cell.get_text(" ", strip=True))
                if rate is None:
                    continue
                results.append({
                    "category": "Time Deposit",
                    "name": (
                        f"HSBC HK Time Deposit ({currency}, {tenor}, {band})"
                    ),
                    "currency": currency,
                    "tenor": tenor,
                    "rate": rate,
                    "rate_unit": "percent_per_annum",
                    "balance_band": band,
                    "risk_level": "Low",
                    "fee": "None",
                    "source_url": source_url,
                    "fetched_at": fetched_at,
                })
    return results


def _summarise(products: Iterable[dict]) -> dict:
    products = list(products)
    currencies = sorted({p["currency"] for p in products})
    tenors = sorted({p["tenor"] for p in products})
    return {
        "count": len(products),
        "currencies": currencies,
        "tenors": tenors,
    }


def write_products_json(products: list[dict], path: Path = DATA_PATH) -> None:
    payload = {
        "source": SOURCE_URL,
        "disclaimer": (
            "Data scraped from a single publicly-accessible HSBC HK page. "
            "Verify against the bank's official quote before any decision."
        ),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": _summarise(products),
        "products": products,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    print(f"fetching {SOURCE_URL} ...", file=sys.stderr)
    html = fetch_html()
    print(f"  got {len(html):,} bytes", file=sys.stderr)
    products = parse_time_deposits(html)
    if not products:
        print(
            "ERROR: parser produced 0 time-deposit entries — page layout may "
            "have changed.",
            file=sys.stderr,
        )
        return 2
    write_products_json(products)
    summary = _summarise(products)
    print(
        f"wrote {summary['count']} entries to {DATA_PATH} "
        f"(currencies={summary['currencies']}, tenors={summary['tenors']})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
