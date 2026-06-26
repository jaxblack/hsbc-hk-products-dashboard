"""Optional LLM-backed analysis for a single HK stock.

This is **scaffolding**: it works end-to-end even with no key configured —
``generate_llm_analysis`` then returns ``configured: False`` with a hint instead
of erroring, so the UI can show "not enabled" gracefully. Fill the environment
variables (or repo-root ``.env``) and restart the backend to turn it on.

Config (env vars / .env):
    LLM_PROVIDER     openai | azure | ollama | "" (empty = disabled)
    LLM_MODEL        model (openai/ollama) or deployment name (azure)
    LLM_API_KEY      secret (not needed for ollama)
    LLM_BASE_URL     openai: https://api.openai.com/v1 (default)
                     azure:  https://<resource>.openai.azure.com
                     ollama: http://localhost:11434/v1 (default)
    LLM_API_VERSION  azure only (default 2024-06-01)

No third-party SDK is used — calls go through urllib against the OpenAI-style
``/chat/completions`` API (Azure uses the deployment URL + ``api-key`` header).
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import hk_stocks as hk

BASE_DIR = Path(__file__).resolve().parent.parent
LLM_HTTP_TIMEOUT_SECONDS = 45
_ENV_LOADED = False

SYSTEM_PROMPT = (
    "你是一位严谨的港股技术与基本面分析师。基于用户提供的行情指标与近期新闻，"
    "用简体中文输出结构化研判：①趋势判断（偏多/中性/偏空及理由）；②关键支撑、压力，"
    "以及买入区间、目标价、止损的参考区间；③主要风险点。语言精炼、可分点。"
    "严禁编造未提供的数据；如数据缺失请直接说明。"
    "结尾必须声明：“本分析为 AI 生成，仅供研究参考，不构成任何投资建议。”"
)


def _load_dotenv(path: Path = BASE_DIR / ".env") -> None:
    """Minimal ``.env`` loader (no dependency). Loads ``KEY=VALUE`` lines into
    ``os.environ`` without overriding values already set in the process env."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


def llm_config() -> dict[str, Any]:
    _load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
    api_version = os.getenv("LLM_API_VERSION", "2024-06-01").strip()
    has_key = bool(os.getenv("LLM_API_KEY", "").strip())
    if provider in ("openai", "compat") and not base_url:
        base_url = "https://api.openai.com/v1"
    if provider == "ollama" and not base_url:
        base_url = "http://localhost:11434/v1"
    return {
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "api_version": api_version,
        "has_key": has_key,
    }


def llm_configured() -> bool:
    cfg = llm_config()
    if not cfg["provider"] or not cfg["model"] or not cfg["base_url"]:
        return False
    if cfg["provider"] == "ollama":
        return True  # local model needs no key
    return cfg["has_key"]


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=LLM_HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def call_llm(system: str, user: str) -> str:
    """Send a chat-completion request to the configured provider and return text."""
    cfg = llm_config()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if cfg["provider"] == "azure":
        url = (
            f"{cfg['base_url']}/openai/deployments/{cfg['model']}"
            f"/chat/completions?api-version={cfg['api_version']}"
        )
        headers = {"api-key": api_key}
        payload: dict[str, Any] = {"messages": messages, "temperature": 0.3, "max_tokens": 800}
    else:
        # openai / ollama / OpenAI-compatible
        url = f"{cfg['base_url']}/chat/completions"
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": cfg["model"],
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 800,
        }
    data = _post_json(url, headers, payload)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"LLM returned no choices: {str(data)[:200]}")
    content = (choices[0].get("message") or {}).get("content", "")
    return content.strip()


def _build_user_prompt(entry: dict[str, Any], insight: dict[str, Any] | None) -> str:
    prof = (insight or {}).get("profile") or entry.get("profile") or {}
    news = (insight or {}).get("news") or []
    price = entry.get("price") or {}
    change = entry.get("change") or {}
    mov = entry.get("moving_averages") or {}
    mom = entry.get("momentum") or {}
    macd = mom.get("macd") or {}
    val = entry.get("valuation") or {}
    intr = entry.get("intraday") or {}
    liq = entry.get("liquidity") or {}
    factor = entry.get("factor") or {}
    lines = [
        f"股票：{entry.get('name')}（{entry.get('symbol')}），板块：{entry.get('sector')}",
        f"公司简介：{prof.get('summary') or '—'}",
        f"现价：{price.get('value')}；今日涨跌幅：{change.get('percent')}%",
        f"今开 {intr.get('open')} / 最高 {intr.get('high')} / 最低 {intr.get('low')} / 振幅 {intr.get('amplitude_pct')}%",
        f"换手率 {liq.get('turnover_rate_pct')}% / 量比 {intr.get('volume_ratio')} / 买一 {intr.get('bid')} 卖一 {intr.get('ask')}",
        f"MA5/10/20/50：{mov.get('ma5')}/{mov.get('ma10')}/{mov.get('ma20')}/{mov.get('ma50')}",
        f"RSI(14)：{mom.get('rsi14')}；MACD 柱：{macd.get('histogram')}",
        f"PE(TTM)：{val.get('pe_ttm')}；PB：{val.get('pb_ratio')}；股息率：{val.get('dividend_yield_pct')}%；总市值：{val.get('market_cap')}",
        f"内部 Factor Score：{factor.get('score')}（{factor.get('band')}）",
    ]
    if news:
        lines.append("近期新闻标题：")
        lines.extend(f"- {item.get('title')}（{item.get('source')}）" for item in news[:6])
    lines.append("请基于以上数据给出研判。数据为空的字段不要臆测。")
    return "\n".join(str(line) for line in lines)


def generate_llm_analysis(raw_symbol: str) -> dict[str, Any]:
    """LLM analysis payload for one symbol. Returns ``configured: False`` (not an
    error) when the LLM is not set up, so the UI degrades gracefully."""
    symbol = hk.normalize_hk_symbol(raw_symbol)
    cfg = llm_config()
    payload: dict[str, Any] = {
        "symbol": symbol,
        "configured": llm_configured(),
        "provider": cfg["provider"] or None,
        "model": cfg["model"] or None,
        "analysis": None,
        "error": None,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if not payload["configured"]:
        payload["error"] = (
            "LLM 未配置。请设置环境变量 LLM_PROVIDER / LLM_MODEL"
            "（openai、azure 还需 LLM_API_KEY；azure/自建还需 LLM_BASE_URL），"
            "或写入仓库根目录的 .env 后重启后端。"
        )
        return payload

    entry: dict[str, Any] | None = None
    try:
        snapshot = hk.load_hk_stock_snapshot()
        entry = next(
            (item for item in snapshot.get("watchlist", []) if item.get("symbol") == symbol),
            None,
        )
    except Exception:  # noqa: BLE001
        entry = None
    if entry is None:
        try:
            entry = hk.fetch_single_quote(symbol).get("stock")
        except Exception as exc:  # noqa: BLE001
            payload["error"] = f"无法获取行情数据：{exc}"
            return payload
    try:
        insight = hk.fetch_stock_insight(symbol)
    except Exception:  # noqa: BLE001
        insight = None

    try:
        payload["analysis"] = call_llm(SYSTEM_PROMPT, _build_user_prompt(entry or {"symbol": symbol}, insight))
    except Exception as exc:  # noqa: BLE001
        payload["error"] = f"LLM 调用失败：{exc}"
    return payload
