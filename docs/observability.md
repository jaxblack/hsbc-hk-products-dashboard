# 监控 / 日志 / 故障降级 / Observability & Degradation

本仓库是一个零状态静态站点 + 一个 CLI scraper；不需要复杂的监控栈。
本文件提供**最小可用**的 observability 建议，可以用 GitHub Actions +
免费工具完成。

## 监控四问

任何对外服务都应该能回答：

1. **它还活着吗？**（liveness）
2. **它的数据还新鲜吗？**（freshness）
3. **它的数据还正确吗？**（validity）
4. **如果挂了，谁会知道、多久知道？**（alerting SLA）

下面针对本看板逐一作答。

### 1. liveness（是否还活着）

- 探针：HTTP `GET` 部署 URL（例 `https://<user>.github.io/hsbc-hk-products-dashboard/`）
- 期望：HTTP 200 + 响应体含 `HSBC HK 公開產品看板` 字符串
- 频率：5–15 分钟 / 次
- 工具：UptimeRobot / Statuscake / Pingdom / Healthchecks.io HTTP check

### 2. freshness（数据是否新鲜）

- 探针：`GET data/products.json`，解析 `fetched_at`
- 期望：`now() - fetched_at < 48h`（建议阈值；告警分级见 [alerts.md](alerts.md)）
- 频率：1 小时 / 次
- 工具：cron + 几行 bash（见 [alerts.md § 3](alerts.md#3-部署--站点可用性告警--site-availability)）

### 3. validity（数据是否合法）

最小校验脚本（可以接到任意 CI / cron）：

```bash
URL="https://<user>.github.io/hsbc-hk-products-dashboard/data/products.json"
python3 - "$URL" <<'PY'
import json, sys, urllib.request, urllib.error
url = sys.argv[1]
try:
    raw = urllib.request.urlopen(url, timeout=20).read()
except urllib.error.URLError as e:
    print(f"FETCH_FAIL: {e}", file=sys.stderr)
    sys.exit(1)
try:
    data = json.loads(raw)
except json.JSONDecodeError as e:
    print(f"JSON_INVALID: {e}", file=sys.stderr)
    sys.exit(2)
assert isinstance(data.get("products"), list), "products[] missing"
assert data["summary"]["count"] == len(data["products"]), "count mismatch"
assert data["summary"]["count"] > 0, "empty products"
for p in data["products"]:
    assert isinstance(p["rate"], (int, float)), f"rate not number: {p['name']}"
    assert 0 <= p["rate"] <= 30, f"rate out of band: {p['name']}={p['rate']}"
print("OK")
PY
```

非零退出码触发告警；具体阈值见 [alerts.md § 1](alerts.md#1-抓取健康度告警--scraper-health)。

### 4. alerting SLA（多久通知到人）

| 严重度 | 渠道 | 期望到达延迟 |
|--------|------|----------------|
| P1（数据全无 / 站点不可达） | IM + 邮件 | < 15 分钟 |
| P2（数据陈旧 / 结构变更） | IM | < 1 小时 |
| P3（单条数据可疑 / 利率突变） | IM 静默频道 | < 6 小时 |

## 日志 / Logging

### 当前

- `app/scraper.py` 通过 `print()` 写 stdout / stderr；非零退出码代表
  "本批数据不可信，不要覆盖"。
- 静态前端无日志（也不应该加任何"打点"，那会引入第三方追踪）。

### 推荐增强（按需，不在本任务范围）

- scraper 改成 `logging` 而非 `print`，至少分 `INFO` / `WARNING` / `ERROR`
  三档；ERROR 必带 stack。
- 抓取的 raw HTML 在 ERROR 时保存到 `_debug/{ISO}.html`（**已**通过
  `.gitignore` 排除 commit），方便事后 diff 上游变更。
- GitHub Actions 的 workflow 日志保留期延长（Settings → Actions →
  Artifact and log retention），至少 30 天。
- **不要**接任何第三方 APM（Sentry / Datadog 等）：本仓库的 ROI 不
  支撑维护成本，且会引入凭证管理负担。

### 不要做

- ❌ 不要把抓取到的全部 HTML 入库或上 S3；HSBC 页面有版权 / ToS。
- ❌ 不要在日志里 echo 任何 cookie / header；scraper 当前只发标准
  `User-Agent`，保持现状。
- ❌ 不要在前端 `console.log` 任何 PII。本前端不接收用户输入，正常
  情况下 console 应当几乎是干净的。

## 降级路径 / Degradation Paths

按"故障严重度递增"列出，每一步都有明确的兜底姿态。

### Level 0 — 一切正常

- scraper 每日运行成功 → 提交新 `products.json` → Actions 发布 → Pages 可
  访问 → 新鲜度探针绿色 → 静默。

### Level 1 — 单次抓取失败（24h 内可自愈）

- scraper 非零退出 → CI 不覆盖 `data/products.json` → Pages 沿用旧数据
- 前端 `fetched_at` 距今变大，但仍可用
- "陈旧"探针仍未触发（< 36h）
- **行动**：无需立即介入；观察下一轮 cron。

### Level 2 — 抓取连续失败 ≥ 24h

- "陈旧"探针 P2 告警触发
- **行动**：人工跑 `python -m app.scraper` 本地复现 → 若是 HSBC 改版，
  按 [Level 3](#level-3--页面结构变更) 流程处理；若是网络 / WAF 临时问题，
  观察恢复。
- **降级展示**：可选地在 `data/STATUS.txt` 写入一句"数据暂停更新，最后
  成功 fetched_at = ..."；前端可读取该文件并 banner 展示（**当前未
  实现**，建议但非必需）。

### Level 3 — 页面结构变更（`summary.count == 0` 或解析全错）

- scraper 退出码非 0，旧 `products.json` 保留
- P1 告警触发
- **行动**：
  1. 把上游 HTML 抓一份到本地（`curl -A "<UA>" "$SOURCE_URL" > debug.html`）。
  2. 与上一份对比 `git log -- data/products.json | head`，定位上次成功时间。
  3. 修 `app/scraper.py` 的选择器；本地跑通后再提 PR。
  4. 在 `docs/changelog/` 留一笔（**当前未启用**，可按需补建）。
- **降级展示**：同 Level 2。

### Level 4 — GitHub Pages 故障

- liveness 探针 P1
- **行动**：
  - 临时切到备份镜像（推荐预先在 Cloudflare Pages / Vercel Static 上保留
    一份热备）。
  - 修改 DNS / README / 入口链接。
- **预案**：建议日常就把仓库连到两个免费静态托管服务，保留两条
  URL，平时只暴露主入口。

### Level 5 — 决定下线 / 长期不维护

- **必做**：
  - 在 `index.html` 顶部加 banner："本看板已停止更新，数据截止
    `<fetched_at>`，请直接访问 HSBC 官网。"
  - 在 README 顶部加同样的提示。
  - 关闭 cron workflow（避免持续产生空提交 / 报错）。
  - 把仓库 archive。
- **不要**：
  - 不要直接删数据让前端 404，那会让用户陷入更困惑的状态。
  - 不要悄无声息下线；明确告知用户"该去哪查实时数据"。

## 故障演练（建议季度一次）

| 演练项 | 目的 | 步骤 |
|--------|------|------|
| 注入"空 JSON"看前端表现 | 验证 UI 在 0 条数据时不崩 | 临时把 `data/products.json` 改成 `{"summary":{"count":0},"products":[]}` 部署。 |
| 注入"陈旧 timestamp"看告警 | 验证 freshness 探针真的能触发 | 把 `fetched_at` 改成 7 天前并部署。 |
| 模拟"上游 5xx" | 验证 scraper 不会写坏文件 | 改 `SOURCE_URL` 指向 `https://httpstat.us/503` 本地运行。 |
| 模拟"结构变更" | 验证解析能 fail-loud | 改 `SOURCE_URL` 指向 `https://example.com` 本地运行；应非零退出。 |

演练后请把临时改动回滚（`git restore` / `git reset --hard`），并把
"演练已完成"写在 `docs/changelog/` 或 PR 描述里。

## 相关文档

- [告警配置](alerts.md)
- [生产部署 checklist](deployment.md)
- [数据延迟与免责](data-latency.md)
- [指标字典 § Invariants](metrics.md#数据质量约束--invariants)
