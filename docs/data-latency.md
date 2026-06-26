# 数据延迟与免责 / Data Latency & Disclaimer

> **本看板呈现的所有数据均为延迟数据。任何场景下，请以 HSBC HK 官方
> 网站 / 网银 / app 的实时报价为准。**

## 延迟来源（一条都不能略）

| 环节 | 典型延迟 | 上限 / 风险点 |
|------|----------|----------------|
| HSBC 官网内部调价 → 公开 deposit-rate 页面刷新 | 数分钟 ~ 数小时 | 后台风控 / 流动性策略调整，发布节奏不在我们控制内。 |
| 公开页面更新 → scraper 下次运行 | 0 ~ **24 小时**（默认 cron 频率） | 用户若调整 cron，可缩短但**不能消除**。 |
| scraper 写入 `data/products.json` → CI 构建并发布到 GitHub Pages | 1 ~ 5 分钟 | 受 GH Pages 队列、缓存影响，偶尔会更久。 |
| CDN 缓存 → 用户浏览器看到新数据 | 1 ~ 15 分钟 | GH Pages 默认有 CDN 缓存；强制刷新 (Cmd-Shift-R) 可绕过。 |
| 用户浏览器读取 → 用户实际"看到并相信"那个数 | ≥ 数秒 | 用户认知 / 决策不在工程可控范围内。 |

**结果**：从 HSBC 内部调价到用户屏幕上的数字更新，**端到端延迟期望
值约为 1–6 小时，最坏可达 24 小时以上**。这对"看趋势"够用，对"做交易"
完全不够。

## 我们做了什么来缓解

- 在 `data/products.json` 中写明 `fetched_at`（UTC ISO-8601），是数据
  延迟的**唯一权威字段**。
- 前端 `assets/dashboard.js` 读取并显示 `fetched_at`，方便用户判断
  新鲜度。
- 建议 cron 每日 1 次抓取（最佳实践见 [alerts.md](alerts.md)）。
- 提供"陈旧"告警阈值建议（`staleness_minutes > 2160` 即 36 小时）。

## 我们**没有**做（也不会假装做）的事

- 没有任何实时数据流 / WebSocket / 推送通道。
- 没有任何"调价提醒"能在分钟级触达用户；本看板的告警延迟取决于
  cron 周期 + Pages 部署延迟，**至少分钟级**，可能小时级。
- 没有任何"成交即时确认"——本看板不接触任何成交链路。

## 标准免责声明（请在前端 / 衍生品中保留）

> ⚠️ **免責聲明 / Disclaimer**
>
> 本看板数据来自 HSBC HK 公开页面，**仅供参考与研究**；并非投资建议，
> 不构成任何要约、邀约或推荐。利率、条款、起存金额、罚息规则等可
> 随时变更，**一切以 HSBC 官网实时公告为准**。
>
> 本项目与 HSBC 集团无任何关联，未经 HSBC 授权或背书。
>
> Data on this dashboard is sourced from public HSBC HK pages and is for
> reference and research only. It does **not** constitute investment
> advice, an offer, or a solicitation. Rates and terms may change at any
> time; always verify against HSBC's official quotes before any decision.
>
> This project is **not** affiliated with or endorsed by HSBC.

### 使用约束

- **禁止**把本看板数据用于"自动下单 / 自动申购 / 客户决策推送"等
  实际交易场景。详见 [trading-risk.md](trading-risk.md)。
- **禁止**移除或弱化本免责声明。前端代码中关于免责声明的 DOM 节点
  不允许通过 query string、cookie、A/B flag、CSS `display:none` 等方式
  隐藏。
- **禁止**对本仓库代码做"投资建议化"的二次包装（例如把利率排序结果
  改成"推荐购买列表"）。

### 数据使用的合理范围

本看板数据**可以**用于：

- 个人或团队的**研究 / 学习 / 比对**：例如"HSBC 各 tenor 名义利率
  对照"、"不同币种实际收益的购买力比较"。
- 演示"如何从公开页面抓数据、做轻量看板"的**工程教学**用例。
- 在写报告 / 写笔记时**引用**当时的快照（请同时引用 `fetched_at` 和
  `source_url`）。

不**应**用于：

- 任何对真实金钱产生约束力的行为（开户、入金、转账、申购、续存、
  提前支取等）。
- 对外发布"利率排行榜 / 推荐榜"——容易被理解为投资建议。
- 任何机器对机器的接口：例如把本仓库的 `data/products.json` 作为
  下游交易系统的"利率源"——这违反 [trading-risk.md](trading-risk.md)
  的红线。

## 与监管的关系

本仓库的维护者**不是**：
- 香港持牌的银行 / 经纪商 / 投资顾问；
- HSBC 集团成员或代理；
- 任何形式的"客户经理"。

任何把本仓库视为"金融服务"的解读都是**误读**；如果你在监管视角下
需要"持牌的"投资建议，请联系合规持牌机构。

## 相关文档

- [真实交易依赖风险](trading-risk.md)
- [指标字典](metrics.md)
- [生产部署 checklist](deployment.md)
- [告警配置](alerts.md)
