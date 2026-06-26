# 数据源策略 / Data Source Strategy

本仓库当前**只覆盖** HSBC HK 公开定存利率页面。本文件说明该策略的边界、
为什么不抓其他品类，以及在判断"哪些数据值得进入看板"时应当如何分层
（宏观 / 微观）。

> ⚠️ 任何超出本文件列出的"已批准来源"的抓取行为，都必须先经过人工
> review，至少包含：(1) 该 URL 是否公开（匿名可访问、未触发 reCAPTCHA / WAF）；
> (2) 该页面的 robots.txt / ToS 是否允许；(3) 抓取频率是否礼貌（≤ 每日 1 次为佳）。

## 当前已批准的数据源

| Source | URL | 类型 | 抓取方式 | 频率 |
|--------|-----|------|----------|------|
| HSBC HK Deposit Rate | https://www.hsbc.com.hk/investments/market-information/hk/deposit-rate/ | 微观 / 银行产品 | `urllib + bs4`（服务端渲染） | 每日 1 次（建议） |

## 三层数据分层 / Data Layering

为了让看板既能"看清单一产品"也能"放进市场大盘背景"，建议未来按以下
分层组织数据；当前仓库只完成 ① 这一层。

### ① 微观层 / Micro — 银行自身产品

来源：发行方公开页面（HSBC 官网公开 quote 列表）。

- **特点**：粒度细（按 currency × tenor × balance band），结构化好，但**更新
  频率受发行方限制**（HSBC HK 该页面通常每个工作日更新一次或更少）。
- **代表数据**：定存利率、活期利率、外汇牌价（如果未来加入公开 FX 牌
  价页面）。
- **抓取建议**：
  - 严格只抓"公开 quote 列表"页面；任何需要登录 / 风险测评 / KYC 的页面
    一律不抓。
  - 单次抓取，礼貌 `User-Agent`，不并发请求同一发行方。
  - 使用 `If-Modified-Since` / `ETag` 减少不必要带宽（HSBC HK 当前页面
    暂不返回这两个 header，所以靠 cron 频率控制）。

### ② 宏观层 / Macro — 港股 / 港元市场背景（**未实现**，建议来源）

来源建议（**全部公开 / 官方**；本仓库未自动抓取，仅列入未来 roadmap）：

| 指标 | 来源建议 | 备注 |
|------|----------|------|
| HIBOR (Hong Kong Interbank Offered Rate) | [HKAB](https://www.hkab.org.hk/) 每日发布 | 1M/3M/6M HIBOR 是港元定存最直接的对标基线。 |
| HKD/USD 即期 | [HKMA Daily Monetary Statistics](https://www.hkma.gov.hk/eng/data-publications-and-research/data-and-statistics/monthly-statistical-bulletin/) | HKD 联系汇率区间 7.75–7.85 是 HKD 利率定价的硬约束。 |
| US Fed Funds Target Rate | [FOMC 公告](https://www.federalreserve.gov/monetarypolicy/openmarket.htm) | 港元联系汇率制度下，USD 利率几乎线性传导到 HKD 同业利率。 |
| HKMA 基本利率 (Base Rate) | [HKMA Base Rate](https://www.hkma.gov.hk/eng/key-information/press-releases/?category=base+rate) | HKMA 公布的政策利率；与 Fed Funds 强联动。 |
| 香港 CPI / GDP | [政府统计处](https://www.censtatd.gov.hk/) | 中长期参考；与定存利率关联较弱，但能解释购买力。 |

**实现思路（仅作 roadmap，不在本任务范围）**：
- 每个宏观源独立的 scraper 模块；输出 JSON 结构 `{indicator, value, as_of, source_url}`。
- 在 `data/macros/` 目录下分文件存放（`hibor.json`、`fed_funds.json` 等），
  避免单个 JSON 过大、避免不同更新频率互相绑架。
- 看板新增"宏观背景"标签页；产品利率旁标注「同 tenor HIBOR」差值。

### ③ 衍生层 / Derived — 跨源派生指标（**未实现**）

例如：
- 「HSBC 1M HKD 定存利率 − 1M HIBOR」=  发行方对个人客户的相对让利幅度。
- 「HSBC USD 12M 利率 − Fed Funds Target」= 长端定存相对短端政策利率的曲
  线形态。
- 「HKD 与 USD 同 tenor 利差」= 联系汇率制下的市场预期偏离。

## 何时**不应**采集 / 引入数据源

以下情形即便技术上可行，也**不要**接入：

- 需要登录、需要 cookie、需要 client certificate、需要风险测评通过的页面。
- 已知部署 reCAPTCHA / Cloudflare Bot Fight Mode 等反爬机制的页面（强行
  绕过即违反 ToS）。
- 任何提供"实时成交流 / 报价流"的接口；个人研究项目没有合规承担能力。
- 任何"代客下单 / 申购"接口；本仓库**严禁**触达交易类 endpoint，无论
  公开与否。
- 任何要求付费 API key 才能访问的数据（避免在公共仓库里管理凭证）。

## 数据质量检查（接入新源时）

新增数据源的 PR 必须能回答：

1. **来源是否权威？** 优先官方（HKAB / HKMA / 发行方），次选行业聚合
   （Bloomberg / Reuters 抓取**严禁**——他们的 ToS 不允许）。
2. **更新频率？** 是否能与定存数据「每日 1 次」对齐；若频率更高 / 更低
   要单独 cron。
3. **失败行为？** 上游 5xx / 解析失败时，下游看板是显示「未取得」还是
   静默吞数据？必须是前者。
4. **结构稳定性？** 上游 HTML / API schema 多久变动一次？需要在 CI 加
   schema 校验，参见 [指标字典 § Invariants](metrics.md#数据质量约束--invariants)。

## 与告警的耦合

任何新数据源接入后，必须同步在 [alerts.md](alerts.md) 中：
- 增加该源对应的"抓取失败"告警阈值；
- 增加该源对应的"结构变更"早期信号（如条目数突变 > X%）。

## 相关文档

- [指标字典](metrics.md)
- [告警配置](alerts.md)
- [生产部署 checklist](deployment.md)
- [真实交易依赖风险](trading-risk.md)
