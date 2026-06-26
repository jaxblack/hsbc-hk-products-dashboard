from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
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
# Yahoo's v7 quote endpoint now requires a crumb/cookie and commonly returns 401,
# so live data is sourced from the public v8 *chart* endpoint (price + history),
# tried across multiple hosts. Tencent is used as an independent secondary source.
YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
YAHOO_CHART_URL = "https://{host}/v8/finance/chart/{symbol}"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q={codes}"
SINA_QUOTE_URL = "https://hq.sinajs.cn/list={codes}"
DEFAULT_RANGE = "6mo"
DEFAULT_INTERVAL = "1d"
WATCHLIST_PATH = BASE_DIR / "data" / "watchlist.json"

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
    {
        "symbol": "1024.HK",
        "code": "1024",
        "name": "Kuaishou",
        "sector": "Internet",
        "currency": "HKD",
    },
    {
        "symbol": "9618.HK",
        "code": "9618",
        "name": "JD.com",
        "sector": "E-Commerce",
        "currency": "HKD",
    },
    {
        "symbol": "9999.HK",
        "code": "9999",
        "name": "NetEase",
        "sector": "Internet",
        "currency": "HKD",
    },
    {
        "symbol": "9888.HK",
        "code": "9888",
        "name": "Baidu",
        "sector": "Internet",
        "currency": "HKD",
    },
    {
        "symbol": "0981.HK",
        "code": "0981",
        "name": "SMIC",
        "sector": "Semiconductors",
        "currency": "HKD",
    },
    {
        "symbol": "0992.HK",
        "code": "0992",
        "name": "Lenovo Group",
        "sector": "Consumer Electronics",
        "currency": "HKD",
    },
    {
        "symbol": "0020.HK",
        "code": "0020",
        "name": "SenseTime",
        "sector": "Internet",
        "currency": "HKD",
    },
    {
        "symbol": "2382.HK",
        "code": "2382",
        "name": "Sunny Optical",
        "sector": "Consumer Electronics",
        "currency": "HKD",
    },
    {"symbol": "1211.HK", "code": "1211", "name": "BYD", "sector": "EV", "currency": "HKD"},
    {"symbol": "2015.HK", "code": "2015", "name": "Li Auto", "sector": "EV", "currency": "HKD"},
    {"symbol": "9868.HK", "code": "9868", "name": "XPeng", "sector": "EV", "currency": "HKD"},
    {"symbol": "9866.HK", "code": "9866", "name": "NIO", "sector": "EV", "currency": "HKD"},
    {"symbol": "9626.HK", "code": "9626", "name": "Bilibili", "sector": "Internet", "currency": "HKD"},
    {"symbol": "9961.HK", "code": "9961", "name": "Trip.com", "sector": "Internet", "currency": "HKD"},
    {"symbol": "6618.HK", "code": "6618", "name": "JD Health", "sector": "Healthcare", "currency": "HKD"},
    {"symbol": "0285.HK", "code": "0285", "name": "BYD Electronic", "sector": "Consumer Electronics", "currency": "HKD"},
    {"symbol": "0268.HK", "code": "0268", "name": "Kingdee", "sector": "Software", "currency": "HKD"},
    {"symbol": "3888.HK", "code": "3888", "name": "Kingsoft", "sector": "Software", "currency": "HKD"},
    {"symbol": "0522.HK", "code": "0522", "name": "ASMPT", "sector": "Semiconductors", "currency": "HKD"},
    {"symbol": "1347.HK", "code": "1347", "name": "Hua Hong Semi", "sector": "Semiconductors", "currency": "HKD"},
    {"symbol": "2269.HK", "code": "2269", "name": "WuXi Bio", "sector": "Biotech", "currency": "HKD"},
    {"symbol": "0772.HK", "code": "0772", "name": "China Literature", "sector": "Internet", "currency": "HKD"},
]

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh"

# Curated Chinese company profiles for the core watchlist. Yahoo's assetProfile
# endpoint now requires a crumb (401), and Tencent/Sina expose no business
# summary, so these are maintained here. Custom/unknown symbols fall back to
# sector only.
COMPANY_PROFILES: dict[str, dict[str, Any]] = {
    "0005.HK": {
        "name_cn": "汇丰控股",
        "summary": "全球性银行与金融服务集团，业务覆盖财富管理与个人银行、工商金融及环球银行与资本市场，在香港与伦敦上市，是高股息蓝筹代表。",
        "industry": "综合性银行",
    },
    "0700.HK": {
        "name_cn": "腾讯控股",
        "summary": "中国互联网与科技龙头，核心业务包括微信/QQ 社交、网络游戏、金融科技与企业服务、网络广告及云业务。",
        "industry": "互联网与游戏",
    },
    "0941.HK": {
        "name_cn": "中国移动",
        "summary": "全球用户规模领先的电信运营商，提供移动与宽带通信、5G、算力网络等服务，现金流稳健、股息率较高。",
        "industry": "电信运营",
    },
    "1299.HK": {
        "name_cn": "友邦保险",
        "summary": "泛亚领先的人寿与健康保险集团，业务覆盖中国内地、香港及东南亚多个市场，以代理人渠道与价值增长见长。",
        "industry": "人寿保险",
    },
    "1810.HK": {
        "name_cn": "小米集团-W",
        "summary": "智能手机、IoT 与生活消费产品及互联网服务公司，近年布局智能电动汽车，主打高性价比与生态链。",
        "industry": "消费电子与智能硬件",
    },
    "2318.HK": {
        "name_cn": "中国平安",
        "summary": "综合金融与医疗健康集团，涵盖寿险、财险、银行、资产管理与科技业务，推进“综合金融+医疗养老”战略。",
        "industry": "综合金融",
    },
    "3690.HK": {
        "name_cn": "美团-W",
        "summary": "中国领先的本地生活服务平台，覆盖外卖、到店、酒旅与即时零售（美团闪购、买菜等），并布局无人配送。",
        "industry": "本地生活服务",
    },
    "9988.HK": {
        "name_cn": "阿里巴巴-W",
        "summary": "中国电商与云计算龙头，业务含淘宝天猫、国际数字商业、阿里云、菜鸟物流与数字媒体娱乐。",
        "industry": "电商与云计算",
    },
    "1024.HK": {
        "name_cn": "快手-W",
        "summary": "中国短视频与直播平台，业务涵盖内容社区、直播电商、线上营销服务，并发力可灵 AI 视频生成。",
        "industry": "短视频与直播",
    },
    "9618.HK": {
        "name_cn": "京东集团-SW",
        "summary": "以自营零售与一体化供应链物流为核心的电商企业，涉足零售、京东物流与科技服务。",
        "industry": "电商与供应链",
    },
    "9999.HK": {
        "name_cn": "网易-S",
        "summary": "以网络游戏为核心，兼有有道教育、网易云音乐与互联网增值服务，自研精品游戏出海。",
        "industry": "网络游戏",
    },
    "9888.HK": {
        "name_cn": "百度集团-SW",
        "summary": "中国搜索与人工智能公司，布局文心大模型、百度智能云与 Apollo 自动驾驶（萝卜快跑）。",
        "industry": "搜索与人工智能",
    },
    "0981.HK": {
        "name_cn": "中芯国际",
        "summary": "中国内地规模最大、技术最先进的晶圆代工厂之一，提供集成电路制造及配套设计服务。",
        "industry": "半导体代工",
    },
    "0992.HK": {
        "name_cn": "联想集团",
        "summary": "全球个人电脑与设备龙头，业务含 PC、智能设备、基础设施方案（服务器）与解决方案服务。",
        "industry": "PC 与硬件设备",
    },
    "0020.HK": {
        "name_cn": "商汤-W",
        "summary": "人工智能软件公司，提供计算机视觉、日日新大模型与生成式 AI、智能产业及智能汽车解决方案。",
        "industry": "人工智能软件",
    },
    "2382.HK": {
        "name_cn": "舜宇光学科技",
        "summary": "光学零件与镜头模组供应商，产品用于智能手机、车载摄像、AR/VR 与安防等领域。",
        "industry": "光学元件",
    },
    "1211.HK": {
        "name_cn": "比亚迪股份",
        "summary": "中国新能源汽车与动力电池龙头，业务含乘用车、商用车、电池（弗迪）与电子代工，垂直整合度高。",
        "industry": "新能源汽车",
    },
    "2015.HK": {
        "name_cn": "理想汽车-W",
        "summary": "中国新能源车企，主打增程式与纯电 SUV，以家庭用户与智能座舱见长。",
        "industry": "新能源汽车",
    },
    "9868.HK": {
        "name_cn": "小鹏汽车-W",
        "summary": "中国智能电动车企，主打智能驾驶（XNGP）与全栈自研，覆盖轿车与 SUV。",
        "industry": "新能源汽车",
    },
    "9866.HK": {
        "name_cn": "蔚来-SW",
        "summary": "中国高端智能电动车企，以换电体系、用户社区与多品牌（蔚来/乐道/萤火虫）布局。",
        "industry": "新能源汽车",
    },
    "9626.HK": {
        "name_cn": "哔哩哔哩-W",
        "summary": "中国年轻人文化社区与视频平台，业务含游戏、增值服务、广告与电商。",
        "industry": "互联网视频",
    },
    "9961.HK": {
        "name_cn": "携程集团-S",
        "summary": "中国领先的在线旅游平台，覆盖机票、酒店、度假与商旅，海外 Trip.com 增长较快。",
        "industry": "在线旅游",
    },
    "6618.HK": {
        "name_cn": "京东健康",
        "summary": "京东旗下医疗健康平台，业务含医药电商、在线问诊与互联网医院。",
        "industry": "互联网医疗",
    },
    "0285.HK": {
        "name_cn": "比亚迪电子",
        "summary": "比亚迪旗下电子代工与零部件商，业务含手机结构件、组装、新型智能产品与汽车电子。",
        "industry": "电子代工",
    },
    "0268.HK": {
        "name_cn": "金蝶国际",
        "summary": "中国企业管理软件与云服务商，主打 ERP 与企业级 SaaS（金蝶云·苍穹/星空）。",
        "industry": "企业软件",
    },
    "3888.HK": {
        "name_cn": "金山软件",
        "summary": "软件与互联网公司，旗下 WPS Office（金山办公）、金山游戏与云业务。",
        "industry": "软件",
    },
    "0522.HK": {
        "name_cn": "ASMPT",
        "summary": "半导体与电子封装设备供应商，提供后段封装、SMT 及先进封装设备。",
        "industry": "半导体设备",
    },
    "1347.HK": {
        "name_cn": "华虹半导体",
        "summary": "中国特色工艺晶圆代工厂，聚焦功率器件、模拟与嵌入式存储等成熟制程。",
        "industry": "半导体代工",
    },
    "2269.HK": {
        "name_cn": "药明生物",
        "summary": "全球领先的生物药 CRDMO 平台，提供从发现、开发到生产的一体化外包服务。",
        "industry": "生物医药外包",
    },
    "0772.HK": {
        "name_cn": "阅文集团",
        "summary": "中国网络文学与 IP 运营平台（起点中文网等），布局影视、动漫与版权衍生。",
        "industry": "网络文学与 IP",
    },
}

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
    "open_price": {
        "label": "开盘价",
        "description": "当日开盘价；与昨收比较可看出高开 / 低开（跳空）。",
        "unit": "HKD",
    },
    "high_low": {
        "label": "最高 / 最低",
        "description": "当日盘中最高价与最低价。",
        "unit": "HKD",
    },
    "amplitude": {
        "label": "振幅",
        "description": "(当日最高 - 最低) / 昨收，衡量日内波动幅度。",
        "unit": "%",
        "formula": "(high - low) / previous_close * 100",
    },
    "volume_ratio": {
        "label": "量比",
        "description": "当前成交量与近期平均成交量之比；>1 表示放量，<1 表示缩量。",
        "unit": "ratio",
    },
    "bid_ask": {
        "label": "买卖盘",
        "description": "最优买一价 / 卖一价及其价差；免费 HK 行情仅提供一档，无完整 5 档深度与买卖量。",
        "unit": "HKD",
    },
    "intraday_change": {
        "label": "今 / 昨涨跌",
        "description": "今日相对昨收、昨日相对前日收盘的涨跌幅；昨日涨跌需历史数据，quote-only 源下为空。",
        "unit": "%",
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


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isdigit())


def normalize_hk_symbol(raw: str) -> str:
    """Normalise user input like '700', '0700', '0700.hk' to Yahoo form '0700.HK'."""
    code = _digits(raw)
    if not code:
        raise ValueError(f"无法从 {raw!r} 解析出港股代码")
    if len(code) < 4:
        code = code.zfill(4)
    return f"{code}.HK"


def _tencent_code(symbol: str) -> str:
    return "hk" + _digits(symbol).zfill(5)


def _fetch_yahoo_chart(symbol: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch ``(meta, history)`` for one symbol from the v8 chart endpoint.

    Every host in ``YAHOO_HOSTS`` is tried before giving up, so a per-host
    429/5xx on one Yahoo edge does not take the whole refresh down.
    """
    params = urllib.parse.urlencode(
        {"range": DEFAULT_RANGE, "interval": DEFAULT_INTERVAL, "includePrePost": "false"}
    )
    last_error: Exception | None = None
    for host in YAHOO_HOSTS:
        url = f"{YAHOO_CHART_URL.format(host=host, symbol=symbol)}?{params}"
        try:
            payload = _fetch_json(url)
            result = payload.get("chart", {}).get("result")
            if not result:
                error = payload.get("chart", {}).get("error")
                raise RuntimeError(f"missing chart data for {symbol}: {error}")
            return result[0].get("meta", {}), _extract_history(result[0])
        except Exception as exc:  # noqa: BLE001 — try the next host
            last_error = exc
    raise RuntimeError(f"all Yahoo hosts failed for {symbol}: {last_error}")


def _parse_tencent_line(line: str) -> dict[str, Any] | None:
    """Parse one ``v_hkXXXXX="100~name~code~price~prevclose~..."`` payload line."""
    body = line.split('="', 1)
    if len(body) != 2:
        return None
    parts = body[1].rstrip('";').split("~")

    def at(index: int) -> float | None:
        return _as_float(parts[index]) if index < len(parts) else None

    if at(3) is None:
        return None
    as_of: str | None = None
    if len(parts) > 30 and parts[30]:
        try:
            naive = datetime.strptime(parts[30].strip(), "%Y/%m/%d %H:%M:%S")
            as_of = (
                naive.replace(tzinfo=timezone(timedelta(hours=8)))
                .astimezone(timezone.utc)
                .isoformat(timespec="seconds")
            )
        except ValueError:
            as_of = None
    return {
        "name": parts[1] if len(parts) > 1 else None,
        "price": at(3),
        "previous_close": at(4),
        "open": at(5),
        "volume": at(6),
        "change_pct": at(32),
        "high": at(33),
        "low": at(34),
        "turnover_value": at(37),
        "pe_ttm": at(39),
        "amplitude_pct": at(43),
        "market_cap": (at(44) * 1e8) if at(44) else None,
        "volume_ratio": at(50),
        "pb_ratio": at(58),
        "turnover_rate_pct": at(59),
        "total_shares": at(69),
        "as_of": as_of,
    }


def _sina_code(symbol: str) -> str:
    return "rt_hk" + _digits(symbol).zfill(5)


def _fetch_sina_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Best bid / ask (买一价 / 卖一价) from Sina's HK feed.

    Requires a ``finance.sina.com.cn`` Referer. HK free quotes expose only the
    top-of-book price (no depth / sizes), so this returns ``{symbol: {"bid":..,
    "ask":..}}``; closed-market or missing values come back as ``None``."""
    if not symbols:
        return {}
    codes = ",".join(_sina_code(symbol) for symbol in symbols)
    url = SINA_QUOTE_URL.format(codes=codes)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Referer": "https://finance.sina.com.cn"},
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP {response.status} for Sina quote")
        text = response.read().decode("gbk", errors="replace")
    quotes: dict[str, dict[str, Any]] = {}
    for symbol, raw_line in zip(symbols, text.strip().splitlines()):
        body = raw_line.split('="', 1)
        if len(body) != 2:
            continue
        parts = body[1].rstrip('";').split(",")
        if len(parts) < 11:
            continue
        bid = _as_float(parts[9])
        ask = _as_float(parts[10])
        quotes[symbol] = {"bid": bid or None, "ask": ask or None}
    return quotes


def _fetch_tencent_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    codes = ",".join(_tencent_code(symbol) for symbol in symbols)
    url = TENCENT_QUOTE_URL.format(codes=codes)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP {response.status} for Tencent quote")
        text = response.read().decode("gbk", errors="replace")
    quotes: dict[str, dict[str, Any]] = {}
    for symbol, raw_line in zip(symbols, text.strip().splitlines()):
        parsed = _parse_tencent_line(raw_line)
        if parsed:
            quotes[symbol] = parsed
    return quotes


def _yahoo_quote_from_meta(
    meta: dict[str, Any], enrichment: dict[str, Any] | None
) -> dict[str, Any]:
    """Adapt v8 chart ``meta`` into the v7-quote-shaped dict ``_build_stock_entry``
    expects. ``previous_close`` is intentionally omitted so the indicator layer
    derives the daily reference from ``closes[-2]`` (chart meta only exposes the
    *range* previous close, not the prior *daily* close)."""
    price = _as_float(meta.get("regularMarketPrice"))
    quote: dict[str, Any] = {
        "regularMarketPrice": price,
        "regularMarketVolume": _as_int(meta.get("regularMarketVolume")),
        "regularMarketTime": meta.get("regularMarketTime"),
        "fullExchangeName": meta.get("fullExchangeName"),
        "exchange": meta.get("exchangeName"),
    }
    # Chart meta carries no P/E; surface Tencent's TTM P/E via an implied EPS so
    # the indicator layer recomputes a consistent pe_ttm = price / eps.
    if enrichment and price:
        pe = _as_float(enrichment.get("pe_ttm"))
        if pe and pe > 0:
            quote["epsTrailingTwelveMonths"] = round(price / pe, 4)
    return quote


class YahooFinanceProvider:
    name = "yahoo-finance"

    def fetch(self, watchlist: list[dict[str, Any]]) -> dict[str, Any]:
        symbols = [item["symbol"] for item in watchlist]
        try:
            enrichment = _fetch_tencent_quotes(symbols)
        except Exception:
            enrichment = {}
        try:
            sina = _fetch_sina_quotes(symbols)
        except Exception:
            sina = {}
        items: list[dict[str, Any]] = []
        quote_timestamp: str | None = None
        yahoo_ok = 0
        degraded = 0
        for stock in watchlist:
            symbol = stock["symbol"]
            tencent = enrichment.get(symbol)
            try:
                meta, history = _fetch_yahoo_chart(symbol)
                quote = _yahoo_quote_from_meta(meta, tencent)
                entry = _build_stock_entry(stock, quote, history, source_mode="live")
                if tencent and tencent.get("turnover_value"):
                    entry["liquidity"]["turnover_value"] = round(
                        float(tencent["turnover_value"]), 2
                    )
                _attach_intraday(entry, tencent, sina.get(symbol), history)
                yahoo_ok += 1
                quote_timestamp = quote_timestamp or _timestamp_to_iso(
                    meta.get("regularMarketTime")
                )
            except Exception:
                # Per-symbol resilience: if a Yahoo host is rate-limited for this
                # symbol, serve Tencent's quote-only entry instead of failing the
                # whole batch (so other symbols keep their full indicators).
                if not tencent:
                    raise
                entry = _build_quote_only_entry(stock, tencent)
                _attach_intraday(entry, tencent, sina.get(symbol), None)
                degraded += 1
                quote_timestamp = quote_timestamp or tencent.get("as_of")
            items.append(entry)
        if yahoo_ok == 0:
            raise RuntimeError("no symbol could be fetched from Yahoo chart hosts")
        warning = (
            f"{degraded}/{len(items)} 只标的因 Yahoo 限流改用腾讯 quote-only 数据（技术指标受限）。"
            if degraded
            else None
        )
        return {
            "provider": {
                "name": self.name,
                "mode": "live",
                "fallback_used": False,
                "warning": warning,
                "source": (
                    "Yahoo Finance v8 chart endpoint (multi-host) "
                    "with Tencent P/E enrichment + per-symbol quote fallback"
                ),
            },
            "as_of": quote_timestamp or _now_iso(),
            "watchlist": items,
        }


class TencentProvider:
    """Independent secondary source (qt.gtimg.cn).

    Quote-only: it returns last price / previous close / volume / turnover /
    TTM P/E but no OHLC history, so price-series indicators (MA, RSI, MACD,
    Bollinger, volatility) are left unavailable and flagged ``LIMITED_HISTORY``.
    Used as a live fallback when every Yahoo host is rate-limited or down.
    """

    name = "tencent-finance"

    def fetch(self, watchlist: list[dict[str, Any]]) -> dict[str, Any]:
        symbols = [item["symbol"] for item in watchlist]
        quotes = _fetch_tencent_quotes(symbols)
        if not quotes:
            raise RuntimeError("Tencent returned no parseable quotes")
        try:
            sina = _fetch_sina_quotes(symbols)
        except Exception:
            sina = {}
        items: list[dict[str, Any]] = []
        as_of: str | None = None
        for stock in watchlist:
            quote = quotes.get(stock["symbol"])
            if not quote:
                raise RuntimeError(f"missing Tencent quote for {stock['symbol']}")
            entry = _build_quote_only_entry(stock, quote)
            _attach_intraday(entry, quote, sina.get(stock["symbol"]), None)
            items.append(entry)
            as_of = as_of or quote.get("as_of")
        return {
            "provider": {
                "name": self.name,
                "mode": "live-quote",
                "fallback_used": False,
                "warning": (
                    "Tencent quote-only source: technical indicators limited "
                    "(no OHLC history)."
                ),
                "source": "Tencent qt.gtimg.cn public HK quote endpoint",
            },
            "as_of": as_of or _now_iso(),
            "watchlist": items,
        }


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
    entry["profile"] = _profile_for(stock)
    factor, primary_alert, alerts = _build_alert_factor(entry, closes)
    entry["factor"] = factor
    entry["alert"] = primary_alert
    entry["alerts"] = alerts
    return entry


def _build_quote_only_entry(
    stock: dict[str, Any], quote: dict[str, Any]
) -> dict[str, Any]:
    """Build a stock entry from a quote-only source (no OHLC history).

    Price-series indicators come out as ``None`` and the entry is tagged with a
    ``LIMITED_HISTORY`` risk flag so the UI can be explicit about the gap."""
    price = _as_float(quote.get("price"))
    yquote: dict[str, Any] = {
        "regularMarketPrice": price,
        "regularMarketPreviousClose": _as_float(quote.get("previous_close")),
        "regularMarketVolume": _as_int(quote.get("volume")),
        "regularMarketTime": None,
        "fullExchangeName": "HKSE",
        "exchange": "HKG",
    }
    pe = _as_float(quote.get("pe_ttm"))
    if pe and pe > 0 and price:
        yquote["epsTrailingTwelveMonths"] = round(price / pe, 4)
    history: dict[str, Any] = {"timestamps": [], "closes": [], "volumes": []}
    entry = _build_stock_entry(stock, yquote, history, source_mode="live-quote")
    if quote.get("as_of"):
        entry["as_of"] = quote["as_of"]
    if quote.get("turnover_value"):
        entry["liquidity"]["turnover_value"] = round(float(quote["turnover_value"]), 2)
    flags = entry["metadata"]["risk_flags"]
    if "LIMITED_HISTORY" not in flags:
        flags.append("LIMITED_HISTORY")
    return entry


def _attach_intraday(
    entry: dict[str, Any],
    tencent: dict[str, Any] | None,
    sina: dict[str, Any] | None,
    history: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach today's micro-structure block — open / high / low / amplitude /
    turnover rate / volume ratio / best bid-ask — plus yesterday's change.

    Also backfills ``liquidity.turnover_rate_pct`` and ``valuation.market_cap /
    pb_ratio`` from Tencent when the primary source did not provide them (e.g.
    live Yahoo-chart mode, where fundamentals are otherwise unavailable)."""
    prev_close = entry["price"].get("previous_close")
    block: dict[str, Any] = {
        "open": None,
        "high": None,
        "low": None,
        "amplitude_pct": None,
        "volume_ratio": None,
        "bid": None,
        "ask": None,
        "spread": None,
        "prev_close": prev_close,
        "prev_change_pct": None,
    }
    if tencent:
        block["open"] = tencent.get("open")
        block["high"] = tencent.get("high")
        block["low"] = tencent.get("low")
        block["amplitude_pct"] = tencent.get("amplitude_pct")
        block["volume_ratio"] = tencent.get("volume_ratio")
        if tencent.get("turnover_rate_pct") is not None:
            entry["liquidity"]["turnover_rate_pct"] = _safe_pct(
                tencent["turnover_rate_pct"]
            )
        if entry["valuation"].get("market_cap") is None and tencent.get("market_cap"):
            entry["valuation"]["market_cap"] = tencent["market_cap"]
        if entry["valuation"].get("pb_ratio") is None and tencent.get("pb_ratio"):
            entry["valuation"]["pb_ratio"] = tencent["pb_ratio"]
    # Fallback amplitude from high/low/prev_close if the source omitted it.
    if (
        block["amplitude_pct"] is None
        and block["high"] is not None
        and block["low"] is not None
        and prev_close
    ):
        block["amplitude_pct"] = _safe_pct((block["high"] - block["low"]) / prev_close * 100)
    if sina:
        block["bid"] = sina.get("bid")
        block["ask"] = sina.get("ask")
        if block["bid"] and block["ask"]:
            block["spread"] = round(block["ask"] - block["bid"], 4)
    # Yesterday's change needs daily history: closes[-1]=today, [-2]=yesterday,
    # [-3]=the day before. Only available when a chart series was fetched.
    closes = (history or {}).get("closes") or []
    if len(closes) >= 3 and closes[-3]:
        block["prev_change_pct"] = _safe_pct((closes[-2] - closes[-3]) / closes[-3] * 100)
    entry["intraday"] = block
    return entry


def _profile_for(stock: dict[str, Any]) -> dict[str, Any]:
    """Curated company profile for a watchlist stock (Chinese), with a sector-only
    fallback for custom / unknown symbols."""
    prof = COMPANY_PROFILES.get(stock["symbol"], {})
    return {
        "name_cn": prof.get("name_cn") or stock.get("name"),
        "summary": prof.get("summary"),
        "sector": stock.get("sector"),
        "industry": prof.get("industry"),
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


def _mock_config_for(symbol: str) -> dict[str, float]:
    """Return the curated mock config for ``symbol`` or a deterministic synthetic
    one, so any newly-added or custom symbol still renders in mock/fallback mode."""
    if symbol in MOCK_STOCK_CONFIG:
        return MOCK_STOCK_CONFIG[symbol]
    seed = int(hashlib.sha1(symbol.encode("utf-8")).hexdigest(), 16)
    base_price = round(8 + (seed % 4200) / 10, 2)
    return {
        "base_price": base_price,
        "trend_pct": round(0.0010 + (seed % 25) / 10000, 4),
        "amplitude_pct": round(0.012 + (seed % 30) / 1000, 4),
        "volume_base": 4_000_000 + (seed % 50) * 1_000_000,
        "market_cap": float(180_000_000_000 + (seed % 4000) * 1_000_000_000),
        "shares_outstanding": int(2_000_000_000 + (seed % 200) * 100_000_000),
        "eps_ttm": round(0.3 + (seed % 900) / 100, 2),
        "book_value": round(base_price * (0.4 + (seed % 50) / 100), 2),
        "dividend_yield_pct": round((seed % 700) / 100, 2),
    }


def _build_mock_stock_entry(stock: dict[str, Any], index: int) -> dict[str, Any]:
    config = _mock_config_for(stock["symbol"])
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
    _attach_intraday(entry, None, None, {"closes": closes})
    entry["profile"] = _profile_for(stock)
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


def load_custom_watchlist(path: Path = WATCHLIST_PATH) -> list[dict[str, Any]]:
    """Return the user-defined watchlist persisted in ``data/watchlist.json``."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    entries = data.get("custom") if isinstance(data, dict) else data
    return [item for item in entries if isinstance(item, dict)] if isinstance(entries, list) else []


def _write_custom_watchlist(
    entries: list[dict[str, Any]], path: Path = WATCHLIST_PATH
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "updated_at": _now_iso(), "custom": entries}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def combined_watchlist() -> list[dict[str, Any]]:
    """Default HK tech watchlist plus persisted custom symbols (deduplicated)."""
    seen = {item["symbol"] for item in HK_WATCHLIST}
    combined = [dict(item) for item in HK_WATCHLIST]
    for entry in load_custom_watchlist():
        symbol = entry.get("symbol")
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        combined.append({**entry, "custom": True})
    return combined


def _resolve_symbol_name(symbol: str) -> str | None:
    try:
        quote = _fetch_tencent_quotes([symbol]).get(symbol)
    except Exception:
        return None
    return quote.get("name") if quote else None


def add_custom_watchlist(
    raw_symbol: str,
    *,
    name: str | None = None,
    sector: str | None = None,
    currency: str = "HKD",
    path: Path = WATCHLIST_PATH,
) -> dict[str, Any]:
    """Validate, dedupe and persist a custom symbol; returns the stored entry."""
    symbol = normalize_hk_symbol(raw_symbol)
    if symbol in {item["symbol"] for item in HK_WATCHLIST}:
        raise ValueError(f"{symbol} 已在默认监控池中")
    entries = load_custom_watchlist(path=path)
    if any(entry.get("symbol") == symbol for entry in entries):
        raise ValueError(f"{symbol} 已在自选列表中")
    entry = {
        "symbol": symbol,
        "code": _digits(symbol).zfill(4),
        "name": (name or _resolve_symbol_name(symbol) or symbol),
        "sector": sector or "自选",
        "currency": currency,
    }
    entries.append(entry)
    _write_custom_watchlist(entries, path=path)
    return entry


def remove_custom_watchlist(raw_symbol: str, *, path: Path = WATCHLIST_PATH) -> bool:
    symbol = normalize_hk_symbol(raw_symbol)
    entries = load_custom_watchlist(path=path)
    remaining = [entry for entry in entries if entry.get("symbol") != symbol]
    if len(remaining) == len(entries):
        return False
    _write_custom_watchlist(remaining, path=path)
    return True


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
    watchlist = combined_watchlist()
    provider_name = os.getenv(ENV_PROVIDER, "").strip().lower()
    allow_live = os.getenv(ENV_ALLOW_LIVE, "1").strip().lower() not in {"0", "false", "no"}
    if provider_name == "mock" or not allow_live:
        payload = _build_payload(
            MockHKStockProvider(
                reason="Live provider disabled by environment; using embedded development snapshot.",
                mode="mock-configured",
            ).fetch(watchlist)
        )
        write_hk_stock_snapshot(payload, path=path)
        return payload

    # Multi-source fallback chain: Yahoo chart (multi-host) → Tencent → mock.
    if provider_name == "tencent":
        chain: list[MarketDataProvider] = [TencentProvider()]
    else:
        chain = [YahooFinanceProvider(), TencentProvider()]

    errors: list[str] = []
    for provider in chain:
        try:
            payload = _build_payload(provider.fetch(watchlist))
            write_hk_stock_snapshot(payload, path=path)
            return payload
        except Exception as exc:  # noqa: BLE001 — fall through to the next source
            errors.append(f"{provider.name}: {exc}")

    payload = _build_payload(
        MockHKStockProvider(
            reason=(
                "All live sources failed; using embedded snapshot. "
                + "; ".join(errors)
            ),
        ).fetch(watchlist)
    )
    write_hk_stock_snapshot(payload, path=path)
    return payload


def _single_payload(
    entry: dict[str, Any],
    *,
    mode: str,
    source: str,
    as_of: str | None,
    warning: str | None = None,
    fallback_used: bool = False,
) -> dict[str, Any]:
    return {
        "version": 1,
        "market": "HK",
        "generated_at": _now_iso(),
        "as_of": as_of or _now_iso(),
        "provider": {
            "name": mode,
            "mode": mode,
            "fallback_used": fallback_used,
            "warning": warning,
            "source": source,
        },
        "disclaimer": (
            "Quotes may be delayed and can fall back to embedded development data. "
            "Do not use this payload as the sole basis for any trading decision."
        ),
        "stock": entry,
        "metadata": {"indicator_definitions": INDICATOR_METADATA},
    }


def fetch_single_quote(
    raw_symbol: str,
    *,
    name: str | None = None,
    sector: str | None = None,
    currency: str = "HKD",
) -> dict[str, Any]:
    """On-demand real-time quote for a single symbol via the live source chain.

    Falls back to a deterministic mock entry (flagged) when every live source is
    unavailable, mirroring the batch snapshot behaviour."""
    symbol = normalize_hk_symbol(raw_symbol)
    stock = next(
        (item for item in combined_watchlist() if item["symbol"] == symbol), None
    )
    if stock is None:
        stock = {
            "symbol": symbol,
            "code": _digits(symbol).zfill(4),
            "name": name or _resolve_symbol_name(symbol) or symbol,
            "sector": sector or "自选",
            "currency": currency,
        }

    provider_name = os.getenv(ENV_PROVIDER, "").strip().lower()
    allow_live = os.getenv(ENV_ALLOW_LIVE, "1").strip().lower() not in {"0", "false", "no"}
    errors: list[str] = []

    if allow_live and provider_name != "mock":
        if provider_name != "tencent":
            try:
                meta, history = _fetch_yahoo_chart(symbol)
                try:
                    enrichment = _fetch_tencent_quotes([symbol])
                except Exception:
                    enrichment = {}
                tencent = enrichment.get(symbol)
                try:
                    sina = _fetch_sina_quotes([symbol]).get(symbol)
                except Exception:
                    sina = None
                quote = _yahoo_quote_from_meta(meta, tencent)
                entry = _build_stock_entry(stock, quote, history, source_mode="live")
                if tencent and tencent.get("turnover_value"):
                    entry["liquidity"]["turnover_value"] = round(
                        float(tencent["turnover_value"]), 2
                    )
                _attach_intraday(entry, tencent, sina, history)
                return _single_payload(
                    entry,
                    mode="live",
                    source="Yahoo v8 chart (multi-host) + Tencent P/E",
                    as_of=_timestamp_to_iso(meta.get("regularMarketTime")),
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"yahoo: {exc}")
        try:
            quote = _fetch_tencent_quotes([symbol]).get(symbol)
            if quote:
                try:
                    sina = _fetch_sina_quotes([symbol]).get(symbol)
                except Exception:
                    sina = None
                entry = _build_quote_only_entry(stock, quote)
                _attach_intraday(entry, quote, sina, None)
                return _single_payload(
                    entry,
                    mode="live-quote",
                    source="Tencent qt.gtimg.cn",
                    as_of=quote.get("as_of"),
                    warning="Tencent quote-only：技术指标受限（无历史 K 线）。",
                )
            errors.append("tencent: 无报价")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tencent: {exc}")

    entry = _build_mock_stock_entry(stock, 1)
    detail = ("详情：" + "; ".join(errors)) if errors else ""
    return _single_payload(
        entry,
        mode="mock-fallback",
        source="Embedded deterministic snapshot",
        as_of=_now_iso(),
        warning="实时数据源不可用，返回 mock 回退。" + detail,
        fallback_used=True,
    )


def _rfc822_to_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return (
            parsedate_to_datetime(value)
            .astimezone(timezone.utc)
            .isoformat(timespec="seconds")
        )
    except (TypeError, ValueError, IndexError):
        return None


def _xml_first(block: str, tag: str) -> str | None:
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
    return html.unescape(match.group(1).strip()) if match else None


def _fetch_google_news(name: str, *, limit: int = 6) -> list[dict[str, Any]]:
    """Recent Chinese-language company news via Google News RSS (no API key)."""
    query = urllib.parse.quote(f"{name} 股票")
    url = GOOGLE_NEWS_RSS.format(query=query)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP {response.status} for Google News")
        xml = response.read().decode("utf-8", errors="replace")
    items: list[dict[str, Any]] = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S)[:limit]:
        title = _xml_first(block, "title")
        if not title:
            continue
        source = _xml_first(block, "source")
        # Google News appends " - <source>" to each headline; trim it.
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].rstrip()
        items.append(
            {
                "title": title,
                "link": _xml_first(block, "link"),
                "source": source,
                "published_at": _rfc822_to_iso(_xml_first(block, "pubDate")),
            }
        )
    return items


def fetch_stock_insight(raw_symbol: str, *, news_limit: int = 6) -> dict[str, Any]:
    """Company profile + recent news for one symbol (lazy detail-panel payload)."""
    symbol = normalize_hk_symbol(raw_symbol)
    stock = next(
        (item for item in combined_watchlist() if item["symbol"] == symbol), None
    )
    if stock is None:
        stock = {
            "symbol": symbol,
            "code": _digits(symbol).zfill(4),
            "name": _resolve_symbol_name(symbol) or symbol,
            "sector": "自选",
            "currency": "HKD",
        }
    profile = _profile_for(stock)
    news_name = profile.get("name_cn") or stock.get("name") or symbol
    news: list[dict[str, Any]] = []
    news_error: str | None = None
    try:
        news = _fetch_google_news(news_name, limit=news_limit)
    except Exception as exc:  # noqa: BLE001
        news_error = str(exc)
    return {
        "symbol": symbol,
        "profile": profile,
        "news": news,
        "news_query": news_name,
        "news_error": news_error,
        "generated_at": _now_iso(),
    }


def main() -> int:
    payload = refresh_hk_stock_snapshot()
    print(
        f"wrote {len(payload['watchlist'])} HK stocks to {DATA_PATH} "
        f"(provider={payload['provider']['name']} mode={payload['provider']['mode']})"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
