# 告警配置 / Alerts Configuration

本文件描述**轻量级**告警接入方案。本仓库 **当前不内置** 告警发送器；
本节是给运维 / 部署方的指引，建议把告警逻辑放到外部 cron + webhook
（如 GitHub Actions、Cron-job.org、Healthchecks.io、Grafana），**不要**把
告警渠道凭证写进本仓库。

> 设计原则：告警**只触发"该人工看一眼"的事件**，不直接做决策。本看板
> 任何输出都不构成投资建议；告警也不应被理解为"买 / 卖信号"。

## 三类告警

### 1. 抓取健康度告警 / Scraper Health

> 目的：第一时间发现页面结构变化、网络封锁、上游 5xx 之类的"看板没数据
> 可看"问题。

| 触发条件 | 严重度 | 推荐渠道 |
|----------|--------|----------|
| `python -m app.scraper` 退出码非 0 | P1 | 邮件 / IM 立刻通知 |
| `summary.count == 0` | P1 | 同上；通常意味着页面结构变了 |
| `summary.count` 较上次下降 > 20% | P2 | IM 通知，人工 review |
| `summary.currencies` / `summary.tenors` 集合变化 | P2 | 同上 |
| 距上次成功 `fetched_at` > 36 小时 | P2 | "数据陈旧"告警 |

实现建议：把 `app/scraper.py` 包装进一个 GitHub Actions workflow，配合
[Healthchecks.io](https://healthchecks.io/) 的 ping URL：

```yaml
# .github/workflows/scrape.yml (示例，未启用)
on:
  schedule: [{ cron: "17 1 * * *" }]   # 每天 09:17 HKT
  workflow_dispatch:
jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - name: Scrape
        run: python -m app.scraper
      - name: Healthchecks ping
        if: success()
        run: curl -fsS --retry 3 "${{ secrets.HEALTHCHECKS_PING_URL }}"
      - name: Commit & push if changed
        run: |
          git config user.name "scraper-bot"
          git config user.email "scraper-bot@users.noreply.github.com"
          git add data/products.json
          git diff --cached --quiet || git commit -m "data: refresh products.json"
          git push
```

`HEALTHCHECKS_PING_URL` 走 GitHub Secrets；URL 本身不入库。Healthchecks
会在该 URL 在 cron 周期内"没被 ping 到"时自动告警。

### 2. 数据语义告警 / Data Semantic（用户自定义阈值）

> 目的：用户感兴趣的"利率突变 / 突破阈值"提示。**仅做提示**，不做决策。

推荐用一个本地（或外部）JSON 描述阈值，**不在仓库 commit**（避免把
个人偏好打进 git 历史）：

```jsonc
// alerts.local.json （示例，已加入 .gitignore，不会被 commit）
{
  "version": 1,
  "channels": {
    "default": { "type": "webhook", "url_env": "ALERT_WEBHOOK_URL" }
  },
  "rules": [
    {
      "id": "hkd-12m-above-4pct",
      "description": "HKD 12 个月期定存任一余额段利率 ≥ 4.0%",
      "match": { "currency": "HKD", "tenor": "12 months" },
      "metric": "rate",
      "op": ">=",
      "threshold": 4.0,
      "channel": "default",
      "cooldown_hours": 24
    },
    {
      "id": "usd-1m-rate-drop-50bps",
      "description": "USD 1 个月期定存利率较上一快照下跌 ≥ 50 bps",
      "match": { "currency": "USD", "tenor": "1 month" },
      "metric": "rate_delta_vs_previous",
      "op": "<=",
      "threshold": -0.5,
      "channel": "default",
      "cooldown_hours": 6
    },
    {
      "id": "staleness",
      "description": "数据陈旧超过 36 小时",
      "match": "global",
      "metric": "staleness_minutes",
      "op": ">",
      "threshold": 2160,
      "channel": "default",
      "cooldown_hours": 12
    }
  ]
}
```

字段说明：

| 字段 | 说明 |
|------|------|
| `channels[].type` | 当前只规划 `webhook`；未来可扩 `email`、`telegram`。 |
| `channels[].url_env` | **凭证从环境变量读**；不要把 webhook URL 写进 JSON。 |
| `rules[].match` | `currency` / `tenor` / `balance_band` 任意子集；或 `"global"`。 |
| `rules[].metric` | 见 [指标字典 § 派生指标](metrics.md#派生指标--derived-metrics)。 |
| `rules[].op` | `>=` / `<=` / `>` / `<` / `==`。 |
| `rules[].threshold` | 与 `metric` 同单位（`rate` 是 % p.a.，`rate_delta` 也是 % p.a.，`staleness_minutes` 是分钟）。 |
| `rules[].cooldown_hours` | 同一规则在该时间窗内最多触发一次，避免风暴。 |

**消费此配置的执行器（建议实现位置）**：单独脚本 `tools/check_alerts.py`
（**本任务不实现**，仅给出落点），由 GH Actions 在 scrape 成功后调用：

```bash
# 伪代码：
python tools/check_alerts.py \
  --data data/products.json \
  --prev data/products.prev.json \
  --rules alerts.local.json
```

退出码：`0` = 无触发；`1` = 有触发并已通知；`2` = 配置 / 数据错误。

### 3. 部署 / 站点可用性告警 / Site Availability

| 检查 | 工具 | 节奏 |
|------|------|------|
| GitHub Pages URL HTTP 200 | UptimeRobot / Statuscake / Healthchecks.io | 每 5–15 分钟 |
| `data/products.json` 可访问且 JSON valid | 同上 + 自定义脚本 | 每小时 |
| `data/products.json` 中 `fetched_at` 距今 < 48h | 同上 | 每小时 |

最小可用脚本（可挂到任意 cron）：

```bash
URL="https://<your-github-username>.github.io/hsbc-hk-products-dashboard/data/products.json"
JSON=$(curl -fsS "$URL") || { echo "FETCH FAILED" >&2; exit 1; }
FETCHED_AT=$(echo "$JSON" | python3 -c 'import sys,json; print(json.load(sys.stdin)["fetched_at"])')
AGE_S=$(( $(date +%s) - $(date -u -d "$FETCHED_AT" +%s 2>/dev/null || gdate -u -d "$FETCHED_AT" +%s) ))
echo "data age (seconds): $AGE_S"
[ "$AGE_S" -lt 172800 ] || { echo "DATA STALE > 48h" >&2; exit 2; }
```

## 关于"投资告警"的红线

- **不**根据告警自动下单 / 联动任何交易接口。
- **不**把告警措辞写成"建议买入 / 卖出"；只写客观事实（"X 利率达到 Y"）。
- **不**把个人持仓 / 客户号 / 账户号写进告警载荷。
- 告警 webhook URL 视为低敏感度凭证，不在 PR 描述、issue、日志里
  打印；通过 Secrets 注入。

## 相关文档

- [指标字典](metrics.md)
- [数据源策略](data-sources.md)
- [生产部署 checklist](deployment.md)
- [监控与日志](observability.md)
