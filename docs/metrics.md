# 指標字典 / Metrics Dictionary

本文件解释 `data/products.json` 中每一个字段的语义、单位、取值范围以及
前端 / 下游消费者应当如何处理。**所有数值仅供研究比对，不构成任何投资
建议**。

> 字段定义以 `app/scraper.py` 实际输出为准；本文件如与代码不一致，以代码为
> 真，请同步本文档。

## 顶层字段

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `source` | string (URL) | `https://www.hsbc.com.hk/investments/market-information/hk/deposit-rate/` | 本次抓取的 HSBC HK 公开数据源 URL。仅记录单一来源；如未来扩展数据源，应改为数组或在每个 `product.source_url` 中标注。 |
| `disclaimer` | string | 见下方 | 静态字符串免责声明，前端必须显示。 |
| `fetched_at` | string (ISO-8601, UTC) | `2026-06-13T09:11:13+00:00` | 抓取完成时间戳。**这是数据"新鲜度"的唯一来源**；前端读取该字段提示用户数据延迟。 |
| `summary.count` | int | `329` | 本次抓取的产品条目总数。`0` 即视为抓取失败（参见 `scraper.py` 的非零退出码）。 |
| `summary.currencies` | array<string> | `["AUD","CAD",...,"USD"]` | 本次抓取覆盖的 ISO-4217 货币代码列表（注意 HSBC 页面上的 `RMB` 已被归一化为 `CNY`）。 |
| `summary.tenors` | array<string> | `["1 day","1 week",...,"12 months"]` | 本次抓取覆盖的存款期限标签（原样保留银行页面的字符串，未做归一化）。 |
| `products` | array<Product> | 见下表 | 单个产品条目。 |

## `products[]` 条目字段

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `category` | string (enum) | `Time Deposit` | 产品大类。当前阶段恒为 `Time Deposit`，未来扩展请参考 [README 的 scope 表](../README.md#current-scope--non-goals)。 |
| `name` | string | `HSBC HK Time Deposit (AUD, 1 week, AUD2,000 to AUD99,999)` | 人类可读名称；由 currency / tenor / balance_band 拼接而成，**不要**用它做主键。 |
| `currency` | string (ISO-4217) | `HKD`、`USD`、`CNY` | 计价货币；前端筛选项之一。`RMB` 已统一归一化为 `CNY`。 |
| `tenor` | string | `1 day`、`1 week`、`1 month`、`12 months` | 存款期限；**原始字符串未数字化**，排序时若想按天数排序需自行解析（见下"派生指标"）。 |
| `rate` | number (float) | `0.15` | **年化利率 (% p.a.)**，即「百分比」表示，例如 `0.15` 表示 `0.15% p.a.`，不是 `15%` 也不是 `0.0015`。<br>合理范围：`0 ≤ rate ≤ 30`；超出区间的值会被 scraper 视为解析噪音并丢弃。 |
| `rate_unit` | string (enum) | `percent_per_annum` | 单位标识；当前只有一个枚举值。如未来加入 `percent_per_period`、`bps` 等单位，请同时升级 dashboard 的渲染逻辑。 |
| `balance_band` | string | `AUD2,000 to AUD99,999`、`HKD500,000 and above` | 适用余额区间，HSBC 页面原文；**未做最小 / 最大值切分**。如需筛选，请在下游解析。 |
| `risk_level` | string (enum) | `Low` | 银行页面声明的风险等级；当前定存条目恒为 `Low`。**不要**用此字段作为投资决策依据。 |
| `fee` | string | `None` | 费用说明；当前为静态字符串 `None`，因为 HSBC HK 该公开页面未在 inline 标注。如有 footnote，应通过 `source_url` 跳转核实。 |
| `source_url` | string (URL) | 同 `source` | 单条目可追溯的源 URL。当前与顶层 `source` 相同，但保留为字段以支持未来跨页面抓取。 |
| `fetched_at` | string (ISO-8601, UTC) | 同 `summary.fetched_at` | 单条目抓取时间。当前批次内所有条目共享时间戳。 |

## 派生指标 / Derived Metrics

下面这些指标**不在 JSON 中**，但前端 / 监控 / 告警可以基于上述字段派生：

| 派生指标 | 计算方式 | 用途建议 |
|----------|----------|----------|
| `tenor_days` | 将 `tenor` 字符串解析为天数。`1 day=1`、`1 week=7`、`1 month=30`、`N months=N*30`。**仅用于排序 / 桶分**，不要用于利息精算。 |
| `best_rate_by_(currency,tenor)` | 在同 currency + 同 tenor 下，按 `rate` 取 max。 | 用于"同 tenor 最高利率"卡片或告警基线。 |
| `rate_delta_vs_previous_snapshot` | 当前批次 `rate` − 上一批次 `rate`。需自行保留历史快照（见下方[告警建议](alerts.md)）。 | 用于"利率突变"告警。 |
| `staleness_minutes` | `now() − fetched_at`，单位分钟。 | 用于"数据陈旧"告警 / 前端"X 分钟前更新"提示。 |
| `coverage_drift` | `summary.count` 较上一批的变化量；或者 `summary.currencies/tenors` 差集。 | 用于"页面结构变更"早期信号；非零差集时人工介入核对页面。 |

## 数据质量约束 / Invariants

下游消费者可以**假定**以下不变量；若被违反，说明 scraper 异常，应触发
告警而非静默吞掉。

- `summary.count == len(products)`；不一致时视为数据损坏。
- 任一 `product.rate` 必为有限数值（非 `null` / `NaN` / `±Inf`）。
  scraper 已在解析阶段过滤；JSON 输出层只保留通过校验的条目。
- 任一 `product.currency` 必在 `summary.currencies` 中。
- `fetched_at` 必为有效 ISO-8601 时间戳，时区必须是 UTC（`+00:00`）。
- `summary.count == 0` **必须**被视为"抓取失败"，scraper 此时以非零退出
  码退出（CI / cron 据此决定是否阻断 deploy）。

## 与下游 UI 的契约

- 前端**绝不**应缓存超过一个批次的快照；每次进入页面必须 `fetch`
  `data/products.json`。
- 前端必须显示 `fetched_at`，并在距今 > 24h 时变红或加 badge。
- 前端必须显示 README / 页面顶部的免责声明；**不允许**通过 query string
  或开关隐藏免责声明。

## 相关文档

- [数据源策略](data-sources.md)
- [告警配置](alerts.md)
- [生产部署](deployment.md)
- [数据延迟与免责](data-latency.md)
