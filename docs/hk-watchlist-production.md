# 港股观察池生产说明 / HK Watchlist Production

本文只覆盖 `data/hk_stocks.json` / `GET /api/hk-stocks` / `POST /api/hk-stocks/refresh`
这条港股观察池链路的生产接入约束。它解决的是**研究看板**与**运维可观测性**
问题，不提供任何投资建议，也不能作为交易、投顾或下单依据。

> ⚠️ `data/hk_stocks.json` 的行情可能延迟，且在上游限流 / 不可用时会回退到
> 内置 mock 快照。任何真实交易前，必须回到官方券商 / 银行 / 交易终端做二次核对。

## 1. 数据源策略

### 1.1 当前生产链路（已实现）

| 层级 | 来源 | 用途 | 生产约束 |
|------|------|------|----------|
| 微观 / Micro | Yahoo Finance public quote/chart endpoints | 单只港股的价格、成交量、均线、RSI、MACD、布林带、估值字段 | 公开端点、非成交系统、可能延迟；**只能**做研究展示。 |
| 降级 / Fallback | `app/hk_stocks.py` 内置 deterministic mock snapshot | 上游 429/5xx/网络错误时保持页面结构不崩 | payload 会显式写 `provider.fallback_used=true` 与 `MOCK_DATA` 风险标记；生产环境不应把它当成正常行情。 |

### 1.2 宏观 / 微观 / 派生分析框架

当前仓库已实现的是**微观层**，即 8 只核心港股观察池的单票指标。若要做更完整
的“宏观 + 微观”分析，推荐按下列方式分层，而**不要**把不同频率的数据粗暴塞进
同一个字段：

| 层级 | 示例指标 | 说明 |
|------|----------|------|
| 宏观 / Macro | HSI / HSTECH、HIBOR、HKD/USD、Fed Funds、HKMA Base Rate | 解释港股风险偏好、流动性和联系汇率环境；建议独立 JSON、独立刷新频率。 |
| 微观 / Micro | 单只股票价格、成交量、MA5/10/20/50、RSI(14)、MACD、PB/PE、股息率 | 当前 `hk_stocks.json` 已覆盖。 |
| 派生 / Derived | price vs MA20、MA20 vs MA50、factor score、watchlist alert density | 用于趋势、动量和风险排序；只能作为研究线索，不是买卖信号。 |

### 1.3 何时不该接入新源

- 需要登录、cookie、OAuth、付费 API key 的行情源。
- 提供逐笔 / 实时成交流的接口。
- 会把观察池研究看板误导成“可下单、可成交、可自动化交易”的数据源。
- 与当前 `hk_stocks.json` 的刷新粒度明显不一致、却又没有独立降级策略的宏观源。

## 2. 指标字典（`data/hk_stocks.json`）

### 2.1 顶层字段

| 字段 | 说明 |
|------|------|
| `generated_at` | 本次 JSON 写盘时间；反映生成时刻，不一定等于上游行情时刻。 |
| `as_of` | 本次 payload 代表的行情时间。若 live 数据可用，来自上游 quote timestamp；fallback 时为本地生成时间。 |
| `provider.name` / `provider.mode` | 当前来源与模式。生产上应重点关注 `yahoo-finance/live`、`embedded-mock/mock-fallback`、`embedded-mock/mock-configured`。 |
| `provider.fallback_used` | `true` 表示本次已降级到 mock；这应触发运维介入或至少在 UI 明示。 |
| `summary.count` | 观察池股票数，当前应为 8。 |
| `summary.fallback_count` | 当前 payload 中带 `MOCK_DATA` 风险标记的股票数。生产期望为 `0`。 |
| `summary.alert_count` / `summary.high_severity_alerts` | 命中预设规则的股票数 / 高优先级股票数。适合作为告警聚合入口。 |
| `summary.average_factor_score` | 全观察池平均 factor score，可用于“整体偏多/偏空/中性”摘要。 |
| `metadata.indicator_definitions` | 当前指标说明的权威来源；前端或下游展示应优先读这里。 |
| `metadata.alert_rule_model` | 当前内置 alert / factor 规则模型；任何外部告警系统都应与它对齐。 |

### 2.2 单只股票字段

| 字段 | 说明 | 生产解释 |
|------|------|----------|
| `price.value` / `price.previous_close` | 最新价 / 前收 | 延迟行情；只能用来观察相对变化。 |
| `change.absolute` / `change.percent` | 绝对涨跌 / 涨跌幅 | 适合做排序、热度摘要，不代表可成交价。 |
| `liquidity.volume` / `turnover_value` / `turnover_rate_pct` | 成交量、成交额、换手率 | `turnover_rate_pct` 若缺流通股本会为空，并带 `TURNOVER_RATE_UNAVAILABLE`。 |
| `volatility.daily_30d_pct` / `annualized_30d_pct` | 30 日波动率（日度 / 年化） | 仅用于风险对比，不能替代正式风控模型。 |
| `moving_averages.ma5/10/20/50` | 移动均线 | 用于趋势判断与 alert 规则。 |
| `momentum.rsi14` / `momentum.macd.*` | RSI、MACD 线/信号线/柱体 | 用于动量与过热/超跌识别。 |
| `bands.bollinger.*` | 布林带中轨、上下轨、带宽 | 适合观察波动压缩 / 扩张。 |
| `valuation.market_cap/pe_ttm/pb_ratio/eps_ttm/dividend_yield_pct` | 估值与股息字段 | 公共源可能缺失；缺失时会带 `PARTIAL_FUNDAMENTALS`。 |
| `factor.score` / `factor.band` | 综合趋势、动量、风险价值打分 | 0–100 分，仅用于研究排序。 |
| `alert` / `alerts[]` | 当前命中的主 alert 与全部命中规则 | 描述必须保持客观，不得改写成“建议买入/卖出”。 |
| `metadata.risk_flags` | `LIVE_DATA`、`DELAYED_MARKET_DATA`、`MOCK_DATA`、`DEV_FALLBACK` 等 | 生产 UI 和监控都必须展示或消费这些风险标记。 |

### 2.3 factor score 解释

当前 `app/hk_stocks.py` 将 factor score 分为：

| 分数区间 | band | 解释 |
|----------|------|------|
| `>= 80` | `strong_bullish` | 趋势、动量、风险价值因子多数偏多。 |
| `65–79.9` | `bullish` | 因子整体偏多，但未到最强。 |
| `45–64.9` | `neutral` | 多空混合，不宜过度解读。 |
| `30–44.9` | `bearish` | 结构偏弱，需要结合风险标记一起看。 |
| `< 30` | `strong_bearish` | 弱势因子密集，但仍不是交易建议。 |

## 3. alert 用法

### 3.1 内置规则模型

payload 已包含 `metadata.alert_rule_model`，当前重点规则包括：

- 趋势类：`trend_breakout`、`trend_breakdown`、`trend_stack_bullish`、`trend_stack_bearish`
- 动量类：`overbought_stretch`、`oversold_stretch`、`macd_bullish_cross`、`macd_bearish_cross`
- 均线结构：`ma_golden_cross`、`ma_death_cross`
- 组合信号：`bullish_composite`、`bearish_composite`、`momentum_exhaustion`

生产上建议把 **股票级规则** 与 **payload 级聚合指标** 分开处理：

| 层级 | 推荐触发条件 | 用法 |
|------|--------------|------|
| 股票级 | `watchlist[i].alert.severity == "high"` | 推送到研究频道，提醒人工看一眼。 |
| payload 级 | `provider.fallback_used == true` | 视为数据源故障，不作为行情事件处理。 |
| payload 级 | `summary.high_severity_alerts >= 2` | 可生成“观察池风险升温”摘要，但只能陈述事实。 |
| payload 级 | `summary.average_factor_score` 明显跌破/升破阈值 | 可做宏观情绪摘要，不要联动交易。 |

### 3.2 外部告警配置建议

不要把 webhook 或 token 写进仓库。推荐把执行器放在 workflow / cron 侧，并通过
环境变量注入告警出口：

```jsonc
{
  "version": 1,
  "channels": {
    "default": { "type": "webhook", "url_env": "ALERT_WEBHOOK_URL" }
  },
  "rules": [
    {
      "id": "hk-watchlist-fallback",
      "metric": "provider.fallback_used",
      "op": "==",
      "threshold": true,
      "channel": "default"
    },
    {
      "id": "hk-watchlist-high-alert-burst",
      "metric": "summary.high_severity_alerts",
      "op": ">=",
      "threshold": 2,
      "channel": "default"
    }
  ]
}
```

### 3.3 红线

- 不把 alert 写成“建议买入 / 卖出 / 抄底 / 止盈”。
- 不把客户持仓、账号、手机号、邮箱写进告警载荷。
- 不因为 `factor.score` 高就触发任何自动下单、自动调仓或自动消息外发给客户。

## 4. 部署环境变量与刷新频率

### 4.1 环境变量

| 变量名 | 用途 | 生产建议 |
|--------|------|----------|
| `HK_STOCKS_PROVIDER` | 强制指定 provider；当前 `mock` 会直接走内置快照 | 生产默认留空；只有演练 / 本地调试时才设 `mock`。 |
| `HK_STOCKS_ALLOW_LIVE` | `0/false/no` 时禁用 live 拉取 | 生产默认 `1`；若上游持续限流，可临时置 `0` 并同时显式维护公告。 |
| `ALERT_WEBHOOK_URL` | 外部告警出口 | 仅放在 GitHub Secrets / 部署 Secrets。 |
| `PAGES_BASE_URL` | 站点 URL，供可用性脚本使用 | 部署侧注入，不写死在仓库里。 |

### 4.2 刷新频率

`hk_stocks.json` 的推荐刷新节奏应与“公共、延迟、可能限流”的上游性质匹配：

| 场景 | 建议频率 | 说明 |
|------|----------|------|
| 交易时段研究看板 | 每 15–30 分钟 | 兼顾可读性与上游 429 风险；不追求实时。 |
| 收市后复盘 | 每日 1 次 | 足够生成日终快照。 |
| GitHub Pages 静态演示 | 每日 1 次或手动刷新 | 避免把 mock fallback 误当 live 行情频繁发布。 |

若生产环境连续出现 429 / 5xx，应先降频，再决定是否临时切到 `HK_STOCKS_ALLOW_LIVE=0`。

## 5. 生产 checklist

- [ ] 页面或下游系统显式展示“延迟数据 / 非投资建议 / 非交易依据”免责声明。
- [ ] 刷新链路在 `provider.fallback_used == true` 时会告警，并阻止“悄悄把 mock 当 live 发布”。
- [ ] `metadata.risk_flags` 已在 UI、日志或监控面板中可见。
- [ ] `summary.count == 8`，`summary.fallback_count == 0`（正常生产期望）。
- [ ] 已配置 `ALERT_WEBHOOK_URL` 等 Secrets，但仓库 / README / issue / logs 中无明文凭证。
- [ ] 已定义收市后或非交易时段的降级说明文案，避免用户误解为实时行情。

## 6. 日志监控与故障降级

### 6.1 最小监控面

- `provider.mode` 是否从 `live` 变成 `mock-fallback` / `mock-configured`
- `summary.fallback_count` 是否大于 0
- `summary.high_severity_alerts` 是否突增
- `as_of` 距当前是否超过你定义的陈旧阈值
- 静态页与 `data/hk_stocks.json` 是否仍然 HTTP 200

### 6.2 日志建议

- 保留 `python -m app.hk_stocks` 或 `POST /api/hk-stocks/refresh` 的 stdout/stderr。
- 在 workflow 日志中记录 provider 名称、mode、fallback 状态、股票数量。
- 不打印 webhook URL、cookie、token，也不要把完整上游响应原样入库。

### 6.3 降级路径

| Level | 现象 | 建议动作 |
|------|------|----------|
| L0 | `provider.mode=live`、`fallback_count=0` | 正常发布。 |
| L1 | 单次 429 / 网络错误，写出 `mock-fallback` | 告警并阻止对外宣称“实时 / 准实时”；必要时暂停自动发布。 |
| L2 | 连续 fallback | 降低刷新频率、排查上游限流、在页面 banner 标明“当前为研究演示快照”。 |
| L3 | 长期无法恢复 live | 关闭自动刷新，保留最后一份可读快照，并引导用户改看官方行情终端。 |

## 7. 标准风险免责声明

> ⚠️ 本观察池使用公共行情端点和内置技术指标，只供研究、教学与趋势比较。
> 数据可能延迟、缺失，或在上游异常时回退到 mock 快照；它**不构成投资建议、
> 招揽、邀约或交易指令**。任何真实交易、调仓、申购、止盈止损决策，都必须
> 回到官方券商 / 银行 / 交易终端核实实时行情与可成交条件。

## 相关文档

- [Docs Index](README.md)
- [告警配置](alerts.md)
- [生产部署 checklist](deployment.md)
- [监控 / 日志 / 故障降级](observability.md)
- [真实交易依赖风险](trading-risk.md)
