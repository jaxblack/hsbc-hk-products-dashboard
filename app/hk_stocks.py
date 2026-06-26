from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Protocol

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "hk_stocks.json"
HTTP_TIMEOUT_SECONDS = 12
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
ENV_PROVIDER = "HK_STOCKS_PROVIDER"
ENV_ALLOW_LIVE = "HK_STOCKS_ALLOW_LIVE"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
DEFAULT_RANGE = "6mo"
DEFAULT_INTERVAL = "1d"

HK_WATCHLIST = [
    {
        "symbol": "0005.HK",
        "code": "0005",
        "name": "HSBC Holdings",
        "sector": "Banking",
        "currency": "HKD",
    },
    {
        "symbol": "0700.HK",
        "code": "0700",
        "name": "Tencent Holdings",
        "sector": "Internet",
        "currency": "HKD",
    },
    {
        "symbol": "0941.HK",
        "code": "0941",
        "name": "China Mobile",
        "sector": "Telecom",
        "currency": "HKD",
    },
    {
        "symbol": "1299.HK",
        "code": "1299",
        "name": "AIA Group",
        "sector": "Insurance",
        "currency": "HKD",
    },
    {
        "symbol": "1810.HK",
        "code": "1810",
        "name": "Xiaomi",
        "sector": "Consumer Electronics",
        "currency": "HKD",
    },
    {
        "symbol": "2318.HK",
        "code": "2318",
        "name": "Ping An Insurance",
        "sector": "Insurance",
        "currency": "HKD",
    },
    {
        "symbol": "3690.HK",
        "code": "3690",
        "name": "Meituan",
        "sector": "Consumer Internet",
        "currency": "HKD",
    },
    {
        "symbol": "9988.HK",
        "code": "9988",
        "name": "Alibaba Group",
        "sector": "E-Commerce",
        "currency": "HKD",
    },
]

INDICATOR_METADATA = {
    "price": {
        "label": "最新价",
        "description": "最新可得成交价或收盘价，延迟与否取决于上游源。",
        "unit": "HKD",
    },
    "change_percent": {
        "label": "涨跌幅",
        "description": "相对前收盘的百分比变化，用于识别日内强弱。",
        "unit": "%",
        "formula": "((price - previous_close) / previous_close) * 100",
    },
    "turnover_value": {
        "label": "成交额",
        "description": "以最新价乘当日成交量估算的成交额。",
        "unit": "HKD",
        "formula": "price * volume",
    },
    "turnover_rate": {
        "label": "换手率",
        "description": "成交量相对流通股本或总股本的近似比例，缺少股本时为空。",
        "unit": "%",
        "formula": "(volume / shares_outstanding) * 100",
    },
    "volatility_30d": {
        "label": "30日波动率",
        "description": "最近30个交易日收益率标准差，提供日度与年化两个口径。",
        "unit": "%",
    },
    "moving_averages": {
        "label": "移动均线",
        "description": "MA5/10/20/50，用于观察趋势支撑与偏离程度。",
        "unit": "HKD",
    },
    "rsi_14": {
        "label": "RSI(14)",
        "description": "14期相对强弱指标，常用来判断超买超卖。",
        "unit": "index",
    },
    "macd": {
        "label": "MACD",
        "description": "12/26 EMA 差值与 9 EMA 信号线，用于衡量动量拐点。",
        "unit": "HKD",
    },
    "bollinger_bands": {
        "label": "布林带",
        "description": "20日均线及上下2倍标准差通道，反映波动区间。",
        "unit": "HKD",
    },
    "valuation": {
        "label": "估值/股息",
        "description": "市值、TTM PE、PB、TTM EPS、股息率等可得基本面字段。",
        "unit": "mixed",
    },
}

MOCK_STOCK_CONFIG = {
    "0005.HK": {
        "base_price": 69.4,
        "trend_pct": 0.0015,
        "amplitude_pct": 0.018,
        "volume_base": 16500000,
        "market_cap": 1240000000000,
        "shares_outstanding": 17880000000,
        "eps_ttm": 8.12,
        "book_value": 74.3,
        "dividend_yield_pct": 6.25,
    },
    "0700.HK": {
        "base_price": 408.2,
        "trend_pct": 0.0022,
        "amplitude_pct": 0.024,
        "volume_base": 14500000,
        "market_cap": 3770000000000,
        "shares_outstanding": 9300000000,
        "eps_ttm": 16.3,
        "book_value": 108.5,
        "dividend_yield_pct": 0.92,
    },
    "0941.HK": {
        "base_price": 77.3,
        "trend_pct": 0.001,
        "amplitude_pct": 0.012,
        "volume_base": 9200000,
        "market_cap": 1580000000000,
        "shares_outstanding": 20480000000,
        "eps_ttm": 6.21,
        "book_value": 68.9,
        "dividend_yield_pct": 7.05,
    },
    "1299.HK": {
        "base_price": 58.8,
        "trend_pct": 0.0013,
        "amplitude_pct": 0.02,
        "volume_base": 8300000,
        "market_cap": 616000000000,
        "shares_outstanding": 10970000000,
        "eps_ttm": 4.25,
        "book_value": 30.5,
        "dividend_yield_pct": 2.01,
    },
    "1810.HK": {
        "base_price": 19.2,
        "trend_pct": 0.0025,
        "amplitude_pct": 0.032,
        "volume_base": 52000000,
        "market_cap": 394000000000,
        "shares_outstanding": 20500000000,
        "eps_ttm": 0.86,
        "book_value": 5.64,
        "dividend_yield_pct": 0.0,
    },
    "2318.HK": {
        "base_price": 47.1,
        "trend_pct": 0.0016,
        "amplitude_pct": 0.021,
        "volume_base": 19800000,
        "market_cap": 885000000000,
        "shares_outstanding": 18280000000,
        "eps_ttm": 7.03,
        "book_value": 61.2,
        "dividend_yield_pct": 5.88,
    },
    "3690.HK": {
        "base_price": 122.8,
        "trend_pct": 0.002,
        "amplitude_pct": 0.03,
        "volume_base": 31200000,
        "market_cap": 751000000000,
        "shares_outstanding": 6110000000,
        "eps_ttm": 5.41,
        "book_value": 36.7,
        "dividend_yield_pct": 0.0,
    },
    "9988.HK": {
        "base_price": 85.6,
        "trend_pct": 0.0017,
        "amplitude_pct": 0.028,
        "volume_base": 28700000,
        "market_cap": 1640000000000,
        "shares_outstanding": 19050000000,
        "eps_ttm": 7.94,
        "book_value": 59.5,
        "dividend_yield_pct": 1.12,
    },
}


class MarketDataProvider(Protocol):
    name: str

    def fetch(self, watchlist: list[dict[str, Any]]) -> dict[str, Any]:
        ...


class YahooFinanceProvider:
    name = "yahoo-finance"

    def fetch(self, watchlist: list[dict[str, Any]]) -> dict[str, Any]:
        quotes = self._fetch_quotes(watchlist)
        items: list[dict[str, Any]] = []
        quote_timestamp: str | None = None
        for stock in watchlist:
            symbol = stock["symbol"]
            quote = quotes.get(symbol)
            if not quote:
                raise RuntimeError(f"missing live quote for {symbol}")
            history = self._fetch_chart(symbol)
            items.append(_build_stock_entry(stock, quote, history, source_mode="live"))
            quote_timestamp = quote_timestamp or _timestamp_to_iso(
                quote.get("regularMarketTime")
            )
        return {
            "provider": {
                "name": self.name,
                "mode": "live",
                "fallback_used": False,
                "warning": None,
                "source": "Yahoo Finance public chart/quote endpoints",
            },
            "as_of": quote_timestamp or _now_iso(),
            "watchlist": items,
        }

    def _fetch_quotes(self, watchlist: list[dict[str, Any]]) -> dict[str, Any]:
        symbols = ",".join(item["symbol"] for item in watchlist)
        url = f"{YAHOO_QUOTE_URL}?{urllib.parse.urlencode({'symbols': symbols})}"
        payload = _fetch_json(url)
        results = payload.get("quoteResponse", {}).get("result", [])
        return {item["symbol"]: item for item in results if item.get("symbol")}

    def _fetch_chart(self, symbol: str) -> dict[str, Any]:
        params = urllib.parse.urlencode(
            {"range": DEFAULT_RANGE, "interval": DEFAULT_INTERVAL, "includePrePost": "false"}
        )
        payload = _fetch_json(f"{YAHOO_CHART_URL.format(symbol=symbol)}?{params}")
        result = payload.get("chart", {}).get("result")
        if not result:
            error = payload.get("chart", {}).get("error")
            raise RuntimeError(f"missing chart data for {symbol}: {error}")
        return _extract_history(result[0])


class MockHKStockProvider:
    name = "embedded-mock"

    def __init__(self, *, reason: str | None = None, mode: str = "mock-fallback") -> None:
        self.reason = reason
        self.mode = mode

    def fetch(self, watchlist: list[dict[str, Any]]) -> dict[str, Any]:
        items = [
            _build_mock_stock_entry(stock, index)
            for index, stock in enumerate(watchlist, start=1)
        ]
        return {
            "provider": {
                "name": self.name,
                "mode": self.mode,
                "fallback_used": True,
                "warning": self.reason
                or "Live data disabled or unavailable; serving embedded development snapshot.",
                "source": "Embedded deterministic development snapshot",
            },
            "as_of": _now_iso(),
            "watchlist": items,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _timestamp_to_iso(timestamp: int | float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(timespec="seconds")


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP {response.status} for {url}")
        return json.loads(response.read().decode("utf-8"))


def _extract_history(result: dict[str, Any]) -> dict[str, Any]:
    timestamps = result.get("timestamp") or []
    quote_series = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote_series.get("close") or []
    volumes = quote_series.get("volume") or []
    pairs = [
        (ts, close, volume)
        for ts, close, volume in zip(timestamps, closes, volumes)
        if close is not None
    ]
    if len(pairs) < 30:
        raise RuntimeError("insufficient chart history for indicator calculations")
    clean_timestamps = [ts for ts, _, _ in pairs]
    clean_closes = [float(close) for _, close, _ in pairs]
    clean_volumes = [int(volume or 0) for _, _, volume in pairs]
    return {
        "timestamps": clean_timestamps,
        "closes": clean_closes,
        "volumes": clean_volumes,
    }


def _format_number(value: float | int | None, digits: int = 2) -> str | None:
    if value is None:
        return None
    return f"{value:,.{digits}f}"


def _safe_pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def _simple_moving_average(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return mean(values[-period:])


def _ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    ema_values = [values[0]]
    for price in values[1:]:
        ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def _calculate_rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev_price, current_price in zip(values[-(period + 1):-1], values[-period:]):
        delta = current_price - prev_price
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))
    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return 100 - (100 / (1 + relative_strength))


def _calculate_macd(values: list[float]) -> dict[str, float | None]:
    if len(values) < 26:
        return {"line": None, "signal": None, "histogram": None}
    short_ema = _ema_series(values, 12)
    long_ema = _ema_series(values, 26)
    macd_line_series = [short - long for short, long in zip(short_ema, long_ema)]
    signal_series = _ema_series(macd_line_series, 9)
    line = macd_line_series[-1]
    signal = signal_series[-1]
    return {
        "line": round(line, 4),
        "signal": round(signal, 4),
        "histogram": round(line - signal, 4),
    }


def _calculate_bollinger(values: list[float], period: int = 20) -> dict[str, float | None]:
    if len(values) < period:
        return {"middle": None, "upper": None, "lower": None, "bandwidth_pct": None}
    window = values[-period:]
    middle = mean(window)
    deviation = pstdev(window)
    upper = middle + (2 * deviation)
    lower = middle - (2 * deviation)
    bandwidth_pct = ((upper - lower) / middle * 100) if middle else None
    return {
        "middle": round(middle, 4),
        "upper": round(upper, 4),
        "lower": round(lower, 4),
        "bandwidth_pct": _safe_pct(bandwidth_pct),
    }


def _calculate_returns(values: list[float]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(values[:-1], values[1:]):
        if previous:
            returns.append((current - previous) / previous)
    return returns


def _calculate_indicators(
    *,
    price: float | None,
    previous_close: float | None,
    volume: int | None,
    shares_outstanding: int | None,
    closes: list[float],
    eps_ttm: float | None,
    book_value: float | None,
    market_cap: float | None,
    dividend_yield_pct: float | None,
) -> dict[str, Any]:
    change_amount = (price - previous_close) if price is not None and previous_close else None
    change_percent = (
        ((price - previous_close) / previous_close) * 100
        if price is not None and previous_close
        else None
    )
    turnover_value = price * volume if price is not None and volume is not None else None
    turnover_rate = (
        volume / shares_outstanding * 100
        if volume is not None and shares_outstanding
        else None
    )
    daily_returns = _calculate_returns(closes[-31:])
    daily_volatility = pstdev(daily_returns) * 100 if len(daily_returns) >= 2 else None
    annualized_volatility = (
        pstdev(daily_returns) * math.sqrt(252) * 100 if len(daily_returns) >= 2 else None
    )
    pb_ratio = (price / book_value) if price is not None and book_value else None
    pe_ttm = (price / eps_ttm) if price is not None and eps_ttm else None
    return {
        "price": {
            "value": round(price, 4) if price is not None else None,
            "previous_close": round(previous_close, 4) if previous_close is not None else None,
            "formatted": _format_number(price),
        },
        "change": {
            "absolute": round(change_amount, 4) if change_amount is not None else None,
            "percent": _safe_pct(change_percent),
            "direction": (
                "up" if change_amount and change_amount > 0 else
                "down" if change_amount and change_amount < 0 else
                "flat"
            ),
        },
        "liquidity": {
            "volume": volume,
            "turnover_value": round(turnover_value, 2) if turnover_value is not None else None,
            "turnover_rate_pct": _safe_pct(turnover_rate),
        },
        "volatility": {
            "daily_30d_pct": _safe_pct(daily_volatility),
            "annualized_30d_pct": _safe_pct(annualized_volatility),
        },
        "moving_averages": {
            "ma5": round(_simple_moving_average(closes, 5), 4) if _simple_moving_average(closes, 5) is not None else None,
            "ma10": round(_simple_moving_average(closes, 10), 4) if _simple_moving_average(closes, 10) is not None else None,
            "ma20": round(_simple_moving_average(closes, 20), 4) if _simple_moving_average(closes, 20) is not None else None,
            "ma50": round(_simple_moving_average(closes, 50), 4) if _simple_moving_average(closes, 50) is not None else None,
        },
        "momentum": {
            "rsi14": round(_calculate_rsi(closes), 4) if _calculate_rsi(closes) is not None else None,
            "macd": _calculate_macd(closes),
        },
        "bands": {
            "bollinger": _calculate_bollinger(closes),
        },
        "valuation": {
            "market_cap": market_cap,
            "pe_ttm": round(pe_ttm, 4) if pe_ttm is not None else None,
            "pb_ratio": round(pb_ratio, 4) if pb_ratio is not None else None,
            "eps_ttm": round(eps_ttm, 4) if eps_ttm is not None else None,
            "dividend_yield_pct": _safe_pct(dividend_yield_pct),
        },
    }


def _build_stock_entry(
    stock: dict[str, Any],
    quote: dict[str, Any],
    history: dict[str, Any],
    *,
    source_mode: str,
) -> dict[str, Any]:
    closes = history["closes"]
    price = _pick_price(quote, closes)
    previous_close = _as_float(quote.get("regularMarketPreviousClose")) or (
        closes[-2] if len(closes) >= 2 else None
    )
    volume = _as_int(quote.get("regularMarketVolume")) or (
        history["volumes"][-1] if history["volumes"] else None
    )
    shares_outstanding = _as_int(quote.get("sharesOutstanding"))
    eps_ttm = _as_float(quote.get("epsTrailingTwelveMonths"))
    book_value = _as_float(quote.get("bookValue"))
    market_cap = _as_float(quote.get("marketCap"))
    dividend_yield_pct = _normalize_yield(quote.get("dividendYield"))
    indicators = _calculate_indicators(
        price=price,
        previous_close=previous_close,
        volume=volume,
        shares_outstanding=shares_outstanding,
        closes=closes,
        eps_ttm=eps_ttm,
        book_value=book_value,
        market_cap=market_cap,
        dividend_yield_pct=dividend_yield_pct,
    )
    risk_flags = ["LIVE_DATA", "DELAYED_MARKET_DATA"]
    if shares_outstanding is None:
        risk_flags.append("TURNOVER_RATE_UNAVAILABLE")
    if dividend_yield_pct is None or eps_ttm is None:
        risk_flags.append("PARTIAL_FUNDAMENTALS")
    return {
        **stock,
        "as_of": _timestamp_to_iso(quote.get("regularMarketTime")) or _now_iso(),
        "exchange": quote.get("fullExchangeName") or quote.get("exchange") or "Hong Kong",
        "source_mode": source_mode,
        "price": indicators["price"],
        "change": indicators["change"],
        "liquidity": indicators["liquidity"],
        "volatility": indicators["volatility"],
        "moving_averages": indicators["moving_averages"],
        "momentum": indicators["momentum"],
        "bands": indicators["bands"],
        "valuation": indicators["valuation"],
        "history": {
            "range": DEFAULT_RANGE,
            "interval": DEFAULT_INTERVAL,
            "close_series": [round(value, 4) for value in closes[-60:]],
        },
        "metadata": {
            "risk_flags": risk_flags,
            "indicator_explanations": INDICATOR_METADATA,
        },
    }


def _pick_price(quote: dict[str, Any], closes: list[float]) -> float | None:
    for key in ("regularMarketPrice", "postMarketPrice", "preMarketPrice"):
        value = _as_float(quote.get(key))
        if value is not None:
            return value
    return closes[-1] if closes else None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_yield(value: Any) -> float | None:
    raw = _as_float(value)
    if raw is None:
        return None
    return raw * 100 if raw <= 1 else raw


def _build_mock_stock_entry(stock: dict[str, Any], index: int) -> dict[str, Any]:
    config = MOCK_STOCK_CONFIG[stock["symbol"]]
    closes, volumes = _generate_mock_series(config, index)
    price = closes[-1]
    previous_close = closes[-2]
    indicators = _calculate_indicators(
        price=price,
        previous_close=previous_close,
        volume=volumes[-1],
        shares_outstanding=int(config["shares_outstanding"]),
        closes=closes,
        eps_ttm=float(config["eps_ttm"]),
        book_value=float(config["book_value"]),
        market_cap=float(config["market_cap"]),
        dividend_yield_pct=float(config["dividend_yield_pct"]),
    )
    return {
        **stock,
        "as_of": _now_iso(),
        "exchange": "Hong Kong",
        "source_mode": "mock",
        "price": indicators["price"],
        "change": indicators["change"],
        "liquidity": indicators["liquidity"],
        "volatility": indicators["volatility"],
        "moving_averages": indicators["moving_averages"],
        "momentum": indicators["momentum"],
        "bands": indicators["bands"],
        "valuation": indicators["valuation"],
        "history": {
            "range": "synthetic-80d",
            "interval": "1d",
            "close_series": [round(value, 4) for value in closes[-60:]],
        },
        "metadata": {
            "risk_flags": ["MOCK_DATA", "NOT_FOR_TRADING", "DEV_FALLBACK"],
            "indicator_explanations": INDICATOR_METADATA,
        },
    }


def _generate_mock_series(config: dict[str, float], index: int) -> tuple[list[float], list[int]]:
    closes: list[float] = []
    volumes: list[int] = []
    price = float(config["base_price"]) * (0.88 + index * 0.01)
    trend_pct = float(config["trend_pct"])
    amplitude_pct = float(config["amplitude_pct"])
    volume_base = int(config["volume_base"])
    for day in range(80):
        wave = math.sin((day + 1) / (2.5 + index * 0.2)) * amplitude_pct
        drift = trend_pct * (1 + ((day % 9) - 4) / 30)
        price = max(price * (1 + drift + wave / 8), 1.0)
        closes.append(round(price, 4))
        volume = int(volume_base * (1 + abs(wave) * 6 + ((day + index) % 7) * 0.04))
        volumes.append(volume)
    return closes, volumes


def _summarise_watchlist(items: list[dict[str, Any]]) -> dict[str, Any]:
    advancing = sum(1 for item in items if (item["change"]["percent"] or 0) > 0)
    declining = sum(1 for item in items if (item["change"]["percent"] or 0) < 0)
    return {
        "count": len(items),
        "symbols": [item["symbol"] for item in items],
        "advancing": advancing,
        "declining": declining,
        "fallback_count": sum(
            1
            for item in items
            if "MOCK_DATA" in item.get("metadata", {}).get("risk_flags", [])
        ),
    }


def _build_payload(provider_data: dict[str, Any]) -> dict[str, Any]:
    watchlist = provider_data["watchlist"]
    return {
        "version": 1,
        "market": "HK",
        "generated_at": _now_iso(),
        "as_of": provider_data["as_of"],
        "provider": provider_data["provider"],
        "disclaimer": (
            "Quotes may be delayed and can fall back to embedded development data. "
            "Do not use this payload as the sole basis for any trading decision."
        ),
        "watchlist": watchlist,
        "summary": _summarise_watchlist(watchlist),
        "metadata": {
            "indicator_definitions": INDICATOR_METADATA,
            "watchlist_strategy": "Core HK large-cap and actively discussed retail names",
            "fallback_policy": (
                "If live upstream calls fail or HK_STOCKS_PROVIDER=mock, the service "
                "returns deterministic mock data with MOCK_DATA risk flags."
            ),
        },
    }


def write_hk_stock_snapshot(payload: dict[str, Any], path: Path = DATA_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_hk_stock_snapshot(
    *,
    refresh: bool = False,
    path: Path = DATA_PATH,
) -> dict[str, Any]:
    if refresh or not path.exists():
        payload = refresh_hk_stock_snapshot(path=path)
        return payload
    return json.loads(path.read_text(encoding="utf-8"))


def refresh_hk_stock_snapshot(path: Path = DATA_PATH) -> dict[str, Any]:
    provider_name = os.getenv(ENV_PROVIDER, "").strip().lower()
    allow_live = os.getenv(ENV_ALLOW_LIVE, "1").strip().lower() not in {"0", "false", "no"}
    if provider_name == "mock" or not allow_live:
        payload = _build_payload(
            MockHKStockProvider(
                reason="Live provider disabled by environment; using embedded development snapshot.",
                mode="mock-configured",
            ).fetch(HK_WATCHLIST)
        )
        write_hk_stock_snapshot(payload, path=path)
        return payload

    try:
        payload = _build_payload(YahooFinanceProvider().fetch(HK_WATCHLIST))
    except Exception as exc:
        payload = _build_payload(
            MockHKStockProvider(
                reason=f"Live Yahoo Finance fetch failed; using embedded snapshot. Details: {exc}",
            ).fetch(HK_WATCHLIST)
        )
    write_hk_stock_snapshot(payload, path=path)
    return payload


def main() -> int:
    payload = refresh_hk_stock_snapshot()
    print(
        f"wrote {len(payload['watchlist'])} HK stocks to {DATA_PATH} "
        f"(provider={payload['provider']['name']} mode={payload['provider']['mode']})"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
