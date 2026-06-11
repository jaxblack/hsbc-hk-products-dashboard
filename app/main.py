from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "products.json"

app = FastAPI(title="HSBC HK Products Dashboard")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def load_products() -> dict:
    with DATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


@app.get("/")
async def index(request: Request) -> JSONResponse:
    payload = load_products()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "payload": payload},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/products")
async def products() -> dict:
    return load_products()
