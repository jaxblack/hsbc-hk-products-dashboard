# Docs Index

生产可用性 / 运维相关文档；面向部署方、运维和审计读者。**不**包含
任何投资建议或交易接口。

| 文档 | 用途 |
|------|------|
| [metrics.md](metrics.md) | 指标字典：`data/products.json` 每个字段的语义、单位、合法范围、派生指标定义。 |
| [data-sources.md](data-sources.md) | 数据源策略：当前覆盖范围、宏观 / 微观分层、何时不该接入新源。 |
| [alerts.md](alerts.md) | 告警配置：抓取健康度 / 数据语义 / 站点可用性三类告警的轻量级落地方案。 |
| [deployment.md](deployment.md) | 生产部署 checklist、环境变量约定、部署目标矩阵、回滚流程。 |
| [observability.md](observability.md) | 监控 / 日志 / 故障降级（Level 0–5）、故障演练建议。 |
| [data-latency.md](data-latency.md) | 数据延迟来源拆解 + 标准免责声明文本。 |
| [trading-risk.md](trading-risk.md) | 真实交易依赖风险：为什么本看板**不能**驱动实际下单。 |

## 阅读顺序建议

- 第一次部署：`deployment.md` → `data-latency.md` → `alerts.md` →
  `observability.md`。
- 接入新数据源：`data-sources.md` → `metrics.md` → `alerts.md`。
- 想做下游集成 / 衍生品：先读 `trading-risk.md`，再考虑要不要做。
- 审计 / 合规视角：`data-latency.md` + `trading-risk.md` 一起读。

## 文档的边界

- 这些文档**不是**投资建议、产品推荐或合规背书。
- 文档中的"建议 / 推荐 / 阈值"都是工程经验，不构成监管要求。
- 任何关于 HSBC 产品的真实条款，**请以 HSBC 官网为准**。
