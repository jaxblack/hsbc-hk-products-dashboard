# 生产部署 / Production Deployment

本仓库可以以两种姿态部署：

1. **静态站点（推荐 / 默认）**：把 `index.html + assets/ + data/products.json`
   推到 GitHub Pages、Cloudflare Pages、Vercel Static 之类的静态托管。已附带
   `.github/workflows/pages.yml`。
2. **legacy FastAPI 服务**：`app/main.py` 提供 `/`、`/health`、`/api/products`，
   仅用于本地开发；**不建议**作为对外服务部署。

> ⚠️ 本看板仅用于**研究和价格比对**。任何生产部署都必须保留首页免责
> 声明，不允许通过任何参数 / 开关把它隐藏掉。

## 部署前 checklist（**逐项打勾**）

### 数据 / 内容

- [ ] `data/products.json` 中 `fetched_at` 距今 < 24 小时；超过则先跑一次
      `python -m app.scraper`。
- [ ] `summary.count > 0`；为 0 不要部署。
- [ ] `index.html` 顶部免责声明可见、未被修改、未被注释掉。
- [ ] README 中的 GitHub Pages URL 已替换为实际账号 / 组织名。

### 流水线 / CI

- [ ] `.github/workflows/pages.yml` 在 main 上至少跑过一次成功。
- [ ] GitHub → Settings → Pages → Source 已设为 **GitHub Actions**。
- [ ] 已设置 cron 触发的 scrape workflow（参见 [alerts.md § 抓取健康度](alerts.md#1-抓取健康度告警--scraper-health)）。
- [ ] 已挂上"Pages URL 可用性"探针（UptimeRobot / Healthchecks）。
- [ ] 已挂上"`data/products.json` 新鲜度"探针（脚本见 alerts.md）。

### 安全 / 合规

- [ ] 仓库内 **无任何凭证**：grep `password|secret|token|api[_-]?key|cookie`
      均无匹配（CI 之外）。
- [ ] 仓库内 **无客户 PII**：grep 账号号 / 身份证号 / 邮箱白名单。
- [ ] 仓库内 **无内部 URL**：grep `127.0.0.1|localhost|intranet|hsbc-internal` 等。
- [ ] `_probe.py / _probes/ / _smoke.py / _inspect.py / _verify.py` 等
      scratch 文件未被提交（`.gitignore` 已覆盖）。
- [ ] 站点未对外暴露任何"代客查询 / 代客下单"入口。
- [ ] 任何告警 webhook URL 走 GitHub Secrets，**不在**仓库 / CI logs 里
      明文出现。

### 性能 / 体验

- [ ] `data/products.json` 大小合理（当前约 150 KB；> 2 MB 时应拆分或
      考虑分页加载）。
- [ ] 静态资源（`assets/dashboard.{css,js}`）总大小 < 100 KB（避免
      首屏阻塞）。
- [ ] 页面在桌面和移动端可正常显示；表格在窄屏可滚动。

### 法务 / 合规（强烈建议人工 review）

- [ ] 与 HSBC HK 官网 [Terms of Use](https://www.hsbc.com.hk/terms-of-use/)
      抓取条款对照，确认本仓库仅抓"公开 quote 列表"页面，频率
      ≤ 每日 1 次，且未绕过反爬措施。
- [ ] README / 首页明确写明"非投资建议、与 HSBC 无关联、信息以官方
      为准"。
- [ ] 如部署到 hsbc 雇员 / 客户可见的渠道，请额外做内部合规 review。

## 环境变量 / Environment Variables

本仓库**当前没有任何必需环境变量**（静态站点 + 公开页面抓取），但以下
是已规划 / 推荐的环境变量名约定，新增功能时请沿用，避免命名漂移：

| 变量名 | 出现位置 | 默认 | 说明 |
|--------|----------|------|------|
| `HSBC_HK_SOURCE_URL` | `app/scraper.py`（未来） | 见 `SOURCE_URL` 常量 | 覆盖抓取源 URL，主要用于本地针对 fixture HTML 调试。 |
| `HSBC_HK_HTTP_TIMEOUT_SECONDS` | 同上 | `30` | scraper 请求超时（秒）。 |
| `HSBC_HK_USER_AGENT` | 同上 | 见 `USER_AGENT` 常量 | 覆盖 UA；调整时务必保持"可识别的浏览器 UA"，避免被 WAF 误判。 |
| `HSBC_HK_DATA_PATH` | 同上 | `data/products.json` | 覆盖输出路径，方便分支并行抓取。 |
| `HEALTHCHECKS_PING_URL` | GitHub Secrets | — | 抓取成功后 ping，触发健康度告警。 |
| `ALERT_WEBHOOK_URL` | GitHub Secrets | — | 告警出口（IM / 邮件中继）；见 [alerts.md](alerts.md)。 |
| `PAGES_BASE_URL` | 部署侧 | — | 部署站点的对外 URL，仅用于"可用性探针"脚本读取。 |

**强约束**：
- 任何凭证（webhook URL、token、API key）**只能**通过环境变量 / Secrets
  注入，不允许出现在 `*.json / *.yml / *.py / *.md` 任何文件里。
- 不要新增数据库 / Redis / S3 这类有状态依赖；本仓库的核心价值是"零状态、
  纯静态、易审计"。

## 部署目标矩阵

| 目标 | 推荐度 | 备注 |
|------|--------|------|
| GitHub Pages | ✅ 推荐 | 已附带 workflow；零运维成本。 |
| Cloudflare Pages | ✅ 推荐 | 构建命令留空 / Output dir = `/`，复制 `index.html + assets + data`。 |
| Vercel Static | ✅ 可用 | 同 Cloudflare Pages 流程。 |
| Netlify Static | ✅ 可用 | 同上。 |
| 自建 Nginx | ⚠️ 仅当受控环境 | 必须挂 HTTPS + HSTS；并需自带可用性探针。 |
| Docker 化 FastAPI 服务 | ⛔ 不推荐对外 | 仅本地 dev；对外引入鉴权 / 合规负担，不值得。 |

## 故障降级 / Degradation

> 详见 [observability.md § 降级路径](observability.md#降级路径--degradation-paths)。
> 这里只列总览：

1. **抓取失败 1 次** → 看板沿用上一份 `data/products.json`；前端继续读，
   但 `fetched_at` 距今变大，触发"陈旧"告警。
2. **抓取连续失败 ≥ 24h** → P1 告警 + 在 Pages 上放置 `data/STATUS.txt`
   说明"数据暂停更新，原因排查中"。
3. **页面结构变更**（`summary.count == 0`） → scraper 非零退出，CI 不
   覆盖现有 JSON；同时 P1 告警人工 review；UI 维持上一版本。
4. **GitHub Pages 故障** → 走备份镜像（建议同时部署 Cloudflare Pages 作
   secondary）；切换 DNS / 修改主入口链接。
5. **整站下线** → 在 README / 域名首页贴 `STATUS.md` 维护说明，说明
   恢复时间预期。

## 回滚

静态部署的回滚就是 `git revert` 然后等 Actions 重跑：

```bash
git revert <bad-commit-sha>
git push origin main
```

`data/products.json` 单独回滚：

```bash
git checkout <good-sha> -- data/products.json
git commit -m "data: rollback products.json to <good-sha>"
git push origin main
```

不要直接在 web UI 上手改 `data/products.json`；所有数据变更都应来自
scraper，可追溯。

## 相关文档

- [告警配置](alerts.md)
- [监控与日志](observability.md)
- [数据延迟与免责](data-latency.md)
- [真实交易依赖风险](trading-risk.md)
