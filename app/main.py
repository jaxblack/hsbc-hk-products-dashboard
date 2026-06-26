from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.hk_stocks import (
    add_custom_watchlist,
    fetch_single_quote,
    fetch_stock_insight,
    load_custom_watchlist,
    load_hk_stock_snapshot,
    refresh_hk_stock_snapshot,
    remove_custom_watchlist,
)
from app.llm import generate_llm_analysis

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "products.json"
INDEX_HTML = BASE_DIR / "index.html"

app = FastAPI(title="HK Equities Monitoring Dashboard")

# Serve the rich static dashboard (index.html + assets/ + data/) directly, so the
# FastAPI deployment and the static GitHub Pages deployment render the same UI.
app.mount("/assets", StaticFiles(directory=BASE_DIR / "assets"), name="assets")
app.mount("/data", StaticFiles(directory=BASE_DIR / "data"), name="data")


def load_products() -> dict:
    with DATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


class WatchlistItem(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(INDEX_HTML)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/products")
async def products() -> dict:
    return load_products()


@app.get("/api/hk-stocks")
async def hk_stocks(refresh: bool = False) -> dict:
    return load_hk_stock_snapshot(refresh=refresh)


@app.post("/api/hk-stocks/refresh")
async def refresh_hk_stocks() -> dict:
    return refresh_hk_stock_snapshot()


@app.get("/api/hk-stocks/quote")
async def hk_stock_quote(symbol: str) -> dict:
    """On-demand real-time quote for a single symbol (live source chain)."""
    try:
        return fetch_single_quote(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/hk-stocks/insight")
async def hk_stock_insight(symbol: str) -> dict:
    """Company profile + recent news for one symbol (lazy detail-panel payload)."""
    try:
        return fetch_stock_insight(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/hk-stocks/llm")
async def hk_stock_llm(symbol: str) -> dict:
    """Optional LLM-backed analysis. Returns ``configured: False`` (HTTP 200)
    when no LLM key/provider is set, so the UI degrades gracefully."""
    try:
        return generate_llm_analysis(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/watchlist")
async def get_watchlist() -> dict:
    return {"custom": load_custom_watchlist()}


@app.post("/api/watchlist")
async def post_watchlist(item: WatchlistItem) -> JSONResponse:
    try:
        entry = add_custom_watchlist(
            item.symbol, name=item.name, sector=item.sector
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(status_code=201, content={"added": entry})


@app.delete("/api/watchlist/{symbol}")
async def delete_watchlist(symbol: str) -> dict:
    try:
        removed = remove_custom_watchlist(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail=f"{symbol} 不在自选列表中")
    return {"removed": symbol}

