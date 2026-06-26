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
    "factor_score": {
        "label": "Factor Score",
        "description": "综合趋势、动量、波动与估值信号的 0-100 分数；越高表示多头因素越占优。",
        "unit": "score",
    },
}

ALERT_RULE_MODEL = {
    "version": 1,
    "description": (
        "Threshold / crossover / composite rule model for the HK watchlist. "
        "Used to derive factor score and stock-level alert summaries."
    ),
    "rules": [
        {
            "id": "trend-breakout",
            "type": "threshold",
            "trigger": "trend_breakout",
            "severity": "medium",
            "priority": 60,
            "conditions": [
                {"metric": "price_vs_ma20_pct", "operator": ">=", "value": 2.0},
                {"metric": "change_pct", "operator": ">=", "value": 0.8},
            ],
            "reason": "现价较 MA20 高出 {price_vs_ma20_pct:.1f}%，且当日涨幅达到 {change_pct:.1f}%。",
        },
        {
            "id": "trend-breakdown",
            "type": "threshold",
            "trigger": "trend_breakdown",
            "severity": "high",
            "priority": 95,
            "conditions": [
                {"metric": "price_vs_ma20_pct", "operator": "<=", "value": -2.0},
                {"metric": "change_pct", "operator": "<=", "value": -0.8},
            ],
            "reason": "现价较 MA20 低出 {price_vs_ma20_pct_abs:.1f}%，且当日跌幅达到 {change_pct_abs:.1f}%。",
        },
        {
            "id": "trend-stack-bullish",
            "type": "threshold",
            "trigger": "trend_stack_bullish",
            "severity": "low",
            "priority": 35,
            "conditions": [
                {"metric": "price_above_ma20", "operator": "==", "value": 1},
                {"metric": "ma20_above_ma50", "operator": "==", "value": 1},
            ],
            "reason": "现价站上 MA20，且 MA20 继续位于 MA50 上方，趋势结构偏多。",
        },
        {
            "id": "trend-stack-bearish",
            "type": "threshold",
            "trigger": "trend_stack_bearish",
            "severity": "medium",
            "priority": 70,
            "conditions": [
                {"metric": "price_above_ma20", "operator": "==", "value": 0},
                {"metric": "ma20_above_ma50", "operator": "==", "value": 0},
            ],
            "reason": "现价跌破 MA20，且 MA20 位于 MA50 下方，趋势结构偏弱。",
        },
        {
            "id": "overbought-stretch",
            "type": "threshold",
            "trigger": "overbought_stretch",
            "severity": "medium",
            "priority": 75,
            "conditions": [
                {"metric": "rsi14", "operator": ">=", "value": 75},
                {"metric": "price_vs_ma20_pct", "operator": ">=", "value": 3.0},
            ],
            "reason": "RSI(14) 升至 {rsi14:.1f}，现价较 MA20 高出 {price_vs_ma20_pct:.1f}%，短线偏热。",
        },
        {
            "id": "oversold-stretch",
            "type": "threshold",
            "trigger": "oversold_stretch",
            "severity": "medium",
            "priority": 72,
            "conditions": [
                {"metric": "rsi14", "operator": "<=", "value": 30},
                {"metric": "price_vs_ma20_pct", "operator": "<=", "value": -3.0},
            ],
            "reason": "RSI(14) 降至 {rsi14:.1f}，现价较 MA20 低出 {price_vs_ma20_pct_abs:.1f}%，进入超跌区。",
        },
        {
            "id": "macd-bullish-cross",
            "type": "crossover",
            "trigger": "macd_bullish_cross",
            "severity": "medium",
            "priority": 58,
            "fast_metric": "macd_line",
            "slow_metric": "macd_signal",
            "direction": "cross_over",
            "reason": "MACD 线向上穿越信号线，动量开始改善。",
        },
        {
            "id": "macd-bearish-cross",
            "type": "crossover",
            "trigger": "macd_bearish_cross",
            "severity": "high",
            "priority": 90,
            "fast_metric": "macd_line",
            "slow_metric": "macd_signal",
            "direction": "cross_under",
            "reason": "MACD 线向下跌破信号线，动量转弱。",
        },
        {
            "id": "ma-golden-cross",
            "type": "crossover",
            "trigger": "ma_golden_cross",
            "severity": "medium",
            "priority": 55,
            "fast_metric": "ma20",
            "slow_metric": "ma50",
            "direction": "cross_over",
            "reason": "MA20 向上穿越 MA50，趋势出现黄金交叉。",
        },
        {
            "id": "ma-death-cross",
            "type": "crossover",
            "trigger": "ma_death_cross",
            "severity": "high",
            "priority": 88,
            "fast_metric": "ma20",
            "slow_metric": "ma50",
            "direction": "cross_under",
            "reason": "MA20 向下跌破 MA50，趋势出现死亡交叉。",
        },
        {
            "id": "bullish-composite",
            "type": "composite",
            "trigger": "bullish_composite",
            "severity": "medium",
            "priority": 82,
            "all_of": ["trend-stack-bullish"],
            "any_of": ["trend-breakout", "macd-bullish-cross", "ma-golden-cross"],
            "factor_score_min": 65,
            "reason": "趋势与动量形成共振，factor score 为 {factor_score:.1f}，命中规则：{matched_rules_text}。",
        },
        {
            "id": "bearish-composite",
            "type": "composite",
            "trigger": "bearish_composite",
            "severity": "high",
            "priority": 100,
            "all_of": ["trend-stack-bearish"],
            "any_of": ["trend-breakdown", "macd-bearish-cross", "ma-death-cross"],
            "factor_score_max": 35,
            "reason": "趋势与动量同步走弱，factor score 仅 {factor_score:.1f}，命中规则：{matched_rules_text}。",
        },
        {
            "id": "momentum-exhaustion",
            "type": "composite",
            "trigger": "momentum_exhaustion",
            "severity": "high",
            "priority": 92,
            "all_of": ["trend-stack-bullish", "overbought-stretch"],
            "factor_score_min": 70,
            "reason": "趋势仍强但 RSI / 偏离率已过热，factor score 为 {factor_score:.1f}，注意追高风险。",
        },
    ],
    "factor_bands": [
        {"min": 80, "label": "strong_bullish"},
        {"min": 65, "label": "bullish"},
        {"min": 45, "label": "neutral"},
        {"min": 30, "label": "bearish"},
        {"min": 0, "label": "strong_bearish"},
    ],
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


def _pct_gap(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return ((numerator - denominator) / denominator) * 100


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _compare_metric(left: float | int | None, operator: str, right: float | int) -> bool:
    if left is None:
        return False
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    if operator == "<":
        return left < right
    if operator == "==":
        return left == right
    raise ValueError(f"unsupported operator: {operator}")


def _build_alert_metrics(entry: dict[str, Any], closes: list[float]) -> dict[str, float | int | None]:
    price_value = entry["price"]["value"]
    moving = entry["moving_averages"]
    momentum = entry["momentum"]
    macd = momentum["macd"]
    valuation = entry["valuation"]
    previous_closes = closes[:-1]
    previous_macd = _calculate_macd(previous_closes) if len(previous_closes) >= 26 else {
        "line": None,
        "signal": None,
        "histogram": None,
    }
    previous_ma20 = _simple_moving_average(previous_closes, 20)
    previous_ma50 = _simple_moving_average(previous_closes, 50)
    price_vs_ma20 = _pct_gap(price_value, moving["ma20"])
    price_vs_ma50 = _pct_gap(price_value, moving["ma50"])
    return {
        "price": price_value,
        "change_pct": entry["change"]["percent"],
        "change_pct_abs": abs(entry["change"]["percent"]) if entry["change"]["percent"] is not None else None,
        "price_vs_ma20_pct": _safe_pct(price_vs_ma20),
        "price_vs_ma20_pct_abs": abs(price_vs_ma20) if price_vs_ma20 is not None else None,
        "price_vs_ma50_pct": _safe_pct(price_vs_ma50),
        "ma20": moving["ma20"],
        "ma50": moving["ma50"],
        "ma20_prev": round(previous_ma20, 4) if previous_ma20 is not None else None,
        "ma50_prev": round(previous_ma50, 4) if previous_ma50 is not None else None,
        "rsi14": momentum["rsi14"],
        "macd_line": macd["line"],
        "macd_signal": macd["signal"],
        "macd_histogram": macd["histogram"],
        "macd_line_prev": previous_macd["line"],
        "macd_signal_prev": previous_macd["signal"],
        "macd_histogram_prev": previous_macd["histogram"],
        "turnover_rate_pct": entry["liquidity"]["turnover_rate_pct"],
        "annualized_volatility_pct": entry["volatility"]["annualized_30d_pct"],
        "pe_ttm": valuation["pe_ttm"],
        "pb_ratio": valuation["pb_ratio"],
        "dividend_yield_pct": valuation["dividend_yield_pct"],
        "price_above_ma20": 1 if price_value is not None and moving["ma20"] is not None and price_value >= moving["ma20"] else 0,
        "ma20_above_ma50": 1 if moving["ma20"] is not None and moving["ma50"] is not None and moving["ma20"] >= moving["ma50"] else 0,
    }


def _compute_factor_score(metrics: dict[str, float | int | None]) -> dict[str, Any]:
    trend = 0.0
    price_vs_ma20 = metrics["price_vs_ma20_pct"]
    price_vs_ma50 = metrics["price_vs_ma50_pct"]
    change_pct = metrics["change_pct"]
    if price_vs_ma20 is not None:
        trend += _clamp(float(price_vs_ma20) * 2.4, -12, 12)
    if price_vs_ma50 is not None:
        trend += _clamp(float(price_vs_ma50) * 1.2, -8, 8)
    trend += 10 if metrics["ma20_above_ma50"] == 1 else -10
    if change_pct is not None:
        trend += _clamp(float(change_pct) * 4, -8, 8)

    momentum = 0.0
    macd_hist = metrics["macd_histogram"]
    macd_hist_prev = metrics["macd_histogram_prev"]
    rsi14 = metrics["rsi14"]
    momentum += 8 if macd_hist is not None and macd_hist >= 0 else -8
    if macd_hist is not None and macd_hist_prev is not None:
        momentum += 5 if macd_hist >= macd_hist_prev else -5
    if rsi14 is not None:
        if 50 <= float(rsi14) <= 68:
            momentum += 7
        elif 68 < float(rsi14) <= 80:
            momentum += 3
        elif 35 <= float(rsi14) < 50:
            momentum -= 2
        elif float(rsi14) < 35:
            momentum -= 8
        else:
            momentum -= 5

    risk_value = 0.0
    annualized_vol = metrics["annualized_volatility_pct"]
    turnover_rate = metrics["turnover_rate_pct"]
    pe_ttm = metrics["pe_ttm"]
    dividend_yield_pct = metrics["dividend_yield_pct"]
    if annualized_vol is not None:
        if float(annualized_vol) <= 20:
            risk_value += 5
        elif float(annualized_vol) >= 40:
            risk_value -= 8
    if turnover_rate is not None:
        risk_value += 4 if float(turnover_rate) >= 0.15 else -2
    if pe_ttm is not None:
        if 0 < float(pe_ttm) <= 18:
            risk_value += 6
        elif float(pe_ttm) >= 35:
            risk_value -= 6
    if dividend_yield_pct is not None and float(dividend_yield_pct) >= 4:
        risk_value += 4

    score = _clamp(50 + trend + momentum + risk_value, 0, 100)
    band = next(
        band_item["label"]
        for band_item in ALERT_RULE_MODEL["factor_bands"]
        if score >= band_item["min"]
    )
    return {
        "score": round(score, 1),
        "factorScore": round(score, 1),
        "band": band,
        "components": {
            "trend": round(trend, 1),
            "momentum": round(momentum, 1),
            "risk_value": round(risk_value, 1),
        },
    }


def _evaluate_threshold_rule(
    rule: dict[str, Any], metrics: dict[str, float | int | None], factor: dict[str, Any]
) -> dict[str, Any] | None:
    if not all(
        _compare_metric(metrics.get(cond["metric"]), cond["operator"], cond["value"])
        for cond in rule["conditions"]
    ):
        return None
    context = {**metrics, "factor_score": factor["score"]}
    return {
        "id": rule["id"],
        "type": rule["type"],
        "trigger": rule["trigger"],
        "severity": rule["severity"],
        "priority": rule["priority"],
        "reason": rule["reason"].format(**context),
        "matchedRules": [rule["id"]],
    }


def _evaluate_crossover_rule(
    rule: dict[str, Any], metrics: dict[str, float | int | None]
) -> dict[str, Any] | None:
    fast_metric = metrics.get(rule["fast_metric"])
    slow_metric = metrics.get(rule["slow_metric"])
    fast_prev = metrics.get(f"{rule['fast_metric']}_prev")
    slow_prev = metrics.get(f"{rule['slow_metric']}_prev")
    if None in {fast_metric, slow_metric, fast_prev, slow_prev}:
        return None
    crossed = (
        fast_prev < slow_prev and fast_metric >= slow_metric
        if rule["direction"] == "cross_over"
        else fast_prev > slow_prev and fast_metric <= slow_metric
    )
    if not crossed:
        return None
    return {
        "id": rule["id"],
        "type": rule["type"],
        "trigger": rule["trigger"],
        "severity": rule["severity"],
        "priority": rule["priority"],
        "reason": rule["reason"],
        "matchedRules": [rule["id"]],
    }


def _evaluate_composite_rule(
    rule: dict[str, Any],
    matched_results: dict[str, dict[str, Any]],
    factor: dict[str, Any],
) -> dict[str, Any] | None:
    all_of = rule.get("all_of", [])
    any_of = rule.get("any_of", [])
    if any(rule_id not in matched_results for rule_id in all_of):
        return None
    if any_of and not any(rule_id in matched_results for rule_id in any_of):
        return None
    score = factor["score"]
    min_score = rule.get("factor_score_min")
    max_score = rule.get("factor_score_max")
    if min_score is not None and score < min_score:
        return None
    if max_score is not None and score > max_score:
        return None
    matched_rule_ids = list(dict.fromkeys(all_of + [item for item in any_of if item in matched_results]))
    matched_rules_text = ", ".join(matched_rule_ids)
    return {
        "id": rule["id"],
        "type": rule["type"],
        "trigger": rule["trigger"],
        "severity": rule["severity"],
        "priority": rule["priority"],
        "reason": rule["reason"].format(
            factor_score=score,
            matched_rules_text=matched_rules_text,
        ),
        "matchedRules": matched_rule_ids,
    }


def _build_alert_factor(
    entry: dict[str, Any], closes: list[float]
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    metrics = _build_alert_metrics(entry, closes)
    factor = _compute_factor_score(metrics)
    matched_results: dict[str, dict[str, Any]] = {}
    for rule in ALERT_RULE_MODEL["rules"]:
        if rule["type"] == "threshold":
            result = _evaluate_threshold_rule(rule, metrics, factor)
        elif rule["type"] == "crossover":
            result = _evaluate_crossover_rule(rule, metrics)
        else:
            continue
        if result:
            matched_results[rule["id"]] = result
    for rule in ALERT_RULE_MODEL["rules"]:
        if rule["type"] != "composite":
            continue
        result = _evaluate_composite_rule(rule, matched_results, factor)
        if result:
            matched_results[rule["id"]] = result
    ordered_results = sorted(
        matched_results.values(),
        key=lambda item: (
            {"high": 3, "medium": 2, "low": 1, "info": 0}.get(item["severity"], 0),
            item["priority"],
        ),
        reverse=True,
    )
    primary_alert = (
        {
            "trigger": ordered_results[0]["trigger"],
            "severity": ordered_results[0]["severity"],
            "reason": ordered_results[0]["reason"],
            "matchedRules": ordered_results[0]["matchedRules"],
        }
        if ordered_results
        else {
            "trigger": "none",
            "severity": "info",
            "reason": "当前未触发预设规则，factor score 处于中性区间。",
            "matchedRules": [],
        }
    )
    return factor, primary_alert, [
        {
            "trigger": item["trigger"],
            "severity": item["severity"],
            "reason": item["reason"],
            "matchedRules": item["matchedRules"],
        }
        for item in ordered_results
    ]


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
    entry = {
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
    factor, primary_alert, alerts = _build_alert_factor(entry, closes)
    entry["factor"] = factor
    entry["alert"] = primary_alert
    entry["alerts"] = alerts
    return entry


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
    entry = {
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
    factor, primary_alert, alerts = _build_alert_factor(entry, closes)
    entry["factor"] = factor
    entry["alert"] = primary_alert
    entry["alerts"] = alerts
    return entry


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
    alerted = [item for item in items if item.get("alert", {}).get("trigger") != "none"]
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
        "alert_count": len(alerted),
        "high_severity_alerts": sum(
            1 for item in alerted if item.get("alert", {}).get("severity") == "high"
        ),
        "average_factor_score": round(
            mean(
                item.get("factor", {}).get("score", 0)
                for item in items
                if item.get("factor", {}).get("score") is not None
            ),
            1,
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
            "alert_rule_model": ALERT_RULE_MODEL,
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
