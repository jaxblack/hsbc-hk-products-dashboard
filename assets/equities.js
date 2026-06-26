/**
 * HK Equities monitoring — static client module.
 *
 * Loads the existing HK stock snapshot (`data/hk_stocks.json`) and falls back to
 * `/api/hk-stocks` when the page is served by FastAPI. The dashboard renders:
 *   - watchlist overview and status cards
 *   - derived macro / micro analysis
 *   - a sortable + filterable watchlist
 *   - per-stock core + technical + valuation metrics
 *   - provider / delay / warning states and indicator definitions
 */
(function () {
  "use strict";

  const DATA_URLS = ["data/hk_stocks.json", "/api/hk-stocks"];
  const AUTO_REFRESH_SECONDS = 120;

  const els = {
    refreshStatus: document.getElementById("eq-refresh-status"),
    refreshText: document.getElementById("eq-refresh-text"),
    refreshBtn: document.getElementById("eq-refresh-btn"),
    autoRefresh: document.getElementById("eq-auto-refresh"),
    statusAsOf: document.getElementById("eq-status-asof"),
    statusDelay: document.getElementById("eq-status-delay"),
    statusProvider: document.getElementById("eq-status-provider"),
    statusAlerts: document.getElementById("eq-status-alerts"),
    overview: document.getElementById("eq-overview"),
    macro: document.getElementById("eq-macro"),
    micro: document.getElementById("eq-micro"),
    filterSector: document.getElementById("eq-filter-sector"),
    filterTrend: document.getElementById("eq-filter-trend"),
    filterSearch: document.getElementById("eq-filter-search"),
    filterReset: document.getElementById("eq-filter-reset"),
    table: document.getElementById("eq-table"),
    body: document.getElementById("eq-body"),
    detailTitle: document.getElementById("eq-detail-title"),
    detailHint: document.getElementById("eq-detail-hint"),
    detailBody: document.getElementById("eq-detail-body"),
    riskList: document.getElementById("eq-risk-list"),
    glossary: document.getElementById("eq-glossary"),
  };

  if (!els.body || !els.table) return;

  const TIP_KEY_MAP = {
    price: "price",
    change_pct: "change_percent",
    turnover: "turnover_value",
    turnover_rate: "turnover_rate",
    volatility_daily: "volatility_30d",
    volatility_annualized: "volatility_30d",
    ma5: "moving_averages",
    ma10: "moving_averages",
    ma20: "moving_averages",
    ma50: "moving_averages",
    rsi14: "rsi_14",
    macd_line: "macd",
    macd_signal: "macd",
    macd_histogram: "macd",
    bollinger_upper: "bollinger_bands",
    bollinger_middle: "bollinger_bands",
    bollinger_lower: "bollinger_bands",
    bollinger_bandwidth: "bollinger_bands",
    market_cap: "valuation",
    pe_ttm: "valuation",
    pb: "valuation",
    eps_ttm: "valuation",
    dividend_yield: "valuation",
    factor_score: "factor_score",
  };

  const state = {
    raw: null,
    stocks: [],
    glossary: {},
    sortKey: "change_pct",
    sortDir: "desc",
    selected: null,
    filters: { sector: "__ALL__", trend: "__ALL__", search: "" },
    autoTimer: null,
    activeUrl: DATA_URLS[0],
  };

  const escapeHtml = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[m]);

  const isNum = (n) => typeof n === "number" && isFinite(n);

  function asNum(value) {
    return typeof value === "number" && isFinite(value) ? value : null;
  }

  function fmtNum(n, dp) {
    if (!isNum(n)) return "—";
    return n.toLocaleString("en-US", {
      minimumFractionDigits: dp == null ? 2 : dp,
      maximumFractionDigits: dp == null ? 2 : dp,
    });
  }

  function fmtPct(n) {
    if (!isNum(n)) return "—";
    const sign = n > 0 ? "+" : "";
    return `${sign}${n.toFixed(2)}%`;
  }

  function fmtMoney(n) {
    if (!isNum(n)) return "—";
    const abs = Math.abs(n);
    if (abs >= 1e12) return `${(n / 1e12).toFixed(2)} 万亿`;
    if (abs >= 1e8) return `${(n / 1e8).toFixed(2)} 亿`;
    if (abs >= 1e4) return `${(n / 1e4).toFixed(2)} 万`;
    return n.toLocaleString("en-US");
  }

  function fmtVolume(n) {
    if (!isNum(n)) return "—";
    if (n >= 1e8) return `${(n / 1e8).toFixed(2)} 亿股`;
    if (n >= 1e4) return `${(n / 1e4).toFixed(1)} 万股`;
    return `${n.toLocaleString("en-US")} 股`;
  }

  function fmtAsOf(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return escapeHtml(value);
    return date.toLocaleString("zh-Hans-CN", {
      timeZone: "Asia/Hong_Kong",
      hour12: false,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function getAgeMinutes(value) {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    return Math.max(0, (Date.now() - date.getTime()) / 60000);
  }

  function fmtAge(minutes) {
    if (!isNum(minutes)) return "—";
    if (minutes < 1) return "刚刚";
    if (minutes < 60) return `${Math.round(minutes)} 分钟`;
    const hours = Math.floor(minutes / 60);
    const mins = Math.round(minutes % 60);
    if (hours < 24) return mins ? `${hours} 小时 ${mins} 分钟` : `${hours} 小时`;
    const days = Math.floor(hours / 24);
    const remHours = hours % 24;
    return remHours ? `${days} 天 ${remHours} 小时` : `${days} 天`;
  }

  function uniqueSorted(arr) {
    return Array.from(new Set(arr.filter((x) => x !== undefined && x !== null && x !== "")))
      .sort((a, b) => String(a).localeCompare(String(b), "zh-Hans-CN"));
  }

  function sumBy(items, pick) {
    return items.reduce((sum, item) => sum + (asNum(pick(item)) || 0), 0);
  }

  function average(values) {
    const nums = values.filter(isNum);
    if (!nums.length) return null;
    return nums.reduce((sum, n) => sum + n, 0) / nums.length;
  }

  function dirClass(n) {
    if (!isNum(n) || n === 0) return "flat";
    return n > 0 ? "up" : "down";
  }

  function ovDirClass(n) {
    if (!isNum(n) || n === 0) return "ov-flat";
    return n > 0 ? "ov-up" : "ov-down";
  }

  function setRefresh(text, kind) {
    if (els.refreshText) els.refreshText.textContent = text;
    if (!els.refreshStatus) return;
    els.refreshStatus.classList.remove("ok", "warn", "loading");
    if (kind) els.refreshStatus.classList.add(kind);
  }

  function setStatusValue(el, text, kind) {
    if (!el) return;
    el.textContent = text;
    el.classList.remove("ok", "warn");
    if (kind) el.classList.add(kind);
  }

  function definitionFor(key) {
    return state.glossary[TIP_KEY_MAP[key] || key] || null;
  }

  function definitionText(key) {
    const def = definitionFor(key);
    if (!def) return "";
    const parts = [];
    if (def.label) parts.push(def.label);
    if (def.description) parts.push(def.description);
    if (def.formula) parts.push(`公式：${def.formula}`);
    if (def.unit) parts.push(`单位：${def.unit}`);
    return parts.join(" | ");
  }

  function providerLabel(provider) {
    if (!provider) return "未知";
    return provider.mode || provider.name || provider.source || "未知";
  }

  function providerNote(provider) {
    if (!provider) return "";
    return provider.source || provider.warning || "";
  }

  function compareValues(a, b, key) {
    const numKeys = ["price", "change_pct", "turnover", "volume", "pe_ttm", "pb", "dividend_yield", "market_cap"];
    if (numKeys.includes(key)) {
      const av = isNum(a) ? a : Number.NEGATIVE_INFINITY;
      const bv = isNum(b) ? b : Number.NEGATIVE_INFINITY;
      return av - bv;
    }
    return String(a == null ? "" : a).localeCompare(String(b == null ? "" : b), "zh-Hans-CN");
  }

  function classifyRegime(avgChange, advancers, decliners) {
    if (isNum(avgChange) && avgChange > 0.5 && advancers > decliners) return "positive";
    if (isNum(avgChange) && avgChange < -0.5 && decliners > advancers) return "negative";
    return "neutral";
  }

  function classifyStance(value) {
    if (!isNum(value)) return "neutral";
    if (value > 0.5) return "positive";
    if (value < -0.5) return "negative";
    return "neutral";
  }

  function sectorAverage(names) {
    const wanted = new Set(names);
    const matches = state.stocks.filter((stock) => wanted.has(stock.sector));
    return average(matches.map((stock) => stock.change_pct));
  }

  function countByFlag(flagNames) {
    const wanted = new Set(flagNames);
    return state.stocks.filter((stock) => stock.risk_flags.some((flag) => wanted.has(flag))).length;
  }

  function activeStockAlerts() {
    return state.stocks
      .filter((stock) => stock.alert && stock.alert.trigger && stock.alert.trigger !== "none")
      .sort((a, b) => {
        const rank = { high: 3, medium: 2, low: 1, info: 0 };
        return (rank[b.alert.severity] || 0) - (rank[a.alert.severity] || 0) || (b.factor_score || 0) - (a.factor_score || 0);
      });
  }

  function activeAlerts() {
    const alerts = [];
    const provider = state.raw && state.raw.provider;
    const ageMinutes = getAgeMinutes(state.raw && (state.raw.as_of || state.raw.generated_at));
    const delayedCount = countByFlag(["DELAYED_MARKET_DATA"]);
    const fallbackCount = countByFlag(["MOCK_DATA", "DEV_FALLBACK"]);
    const stockAlerts = activeStockAlerts();

    if (provider && provider.warning) {
      alerts.push(`行情源告警：${provider.warning}`);
    }
    if (provider && provider.fallback_used) {
      alerts.push(`行情源已切换至回退快照（${providerLabel(provider)}），当前并非可交易级实时行情。`);
    }
    if (isNum(ageMinutes) && ageMinutes > 20) {
      alerts.push(`数据延迟：最近快照距今约 ${fmtAge(ageMinutes)}。`);
    }
    if (delayedCount > 0) {
      alerts.push(`${delayedCount}/${state.stocks.length} 只标的带有 DELAYED_MARKET_DATA 标记。`);
    }
    if (fallbackCount > 0) {
      alerts.push(`${fallbackCount}/${state.stocks.length} 只标的使用 mock / fallback 数据。`);
    }
    if (stockAlerts.length > 0) {
      const highCount = stockAlerts.filter((stock) => stock.alert.severity === "high").length;
      alerts.push(
        `监控规则触发 ${stockAlerts.length} 次${highCount ? `，其中 ${highCount} 次为高优先级` : ""}。`,
      );
    }
    return Array.from(new Set(alerts));
  }

  function normalizeStock(item) {
    const price = item.price || {};
    const change = item.change || {};
    const liquidity = item.liquidity || {};
    const valuation = item.valuation || {};
    const volatility = item.volatility || {};
    const moving = item.moving_averages || {};
    const momentum = item.momentum || {};
    const macd = momentum.macd || {};
    const bollinger = (item.bands && item.bands.bollinger) || {};
    const metadata = item.metadata || {};
    const factor = item.factor || {};
    const alert = item.alert || {};
    const alerts = Array.isArray(item.alerts) ? item.alerts : [];

    return {
      ticker: item.symbol || item.ticker || "",
      code: item.code || "",
      name: item.name || item.name_en || item.symbol || "—",
      sector: item.sector || "—",
      currency: item.currency || "HKD",
      as_of: item.as_of || state.raw?.as_of || state.raw?.generated_at || "",
      source_mode: item.source_mode || providerLabel(state.raw && state.raw.provider),
      price: asNum(price.value),
      prev_close: asNum(price.previous_close),
      change_abs: asNum(change.absolute),
      change_pct: asNum(change.percent),
      trend: change.direction || dirClass(asNum(change.percent)),
      volume: asNum(liquidity.volume),
      turnover: asNum(liquidity.turnover_value),
      turnover_rate: asNum(liquidity.turnover_rate_pct),
      market_cap: asNum(valuation.market_cap),
      pe_ttm: asNum(valuation.pe_ttm),
      pb: asNum(valuation.pb_ratio),
      eps_ttm: asNum(valuation.eps_ttm),
      dividend_yield: asNum(valuation.dividend_yield_pct),
      volatility_daily: asNum(volatility.daily_30d_pct),
      volatility_annualized: asNum(volatility.annualized_30d_pct),
      ma5: asNum(moving.ma5),
      ma10: asNum(moving.ma10),
      ma20: asNum(moving.ma20),
      ma50: asNum(moving.ma50),
      rsi14: asNum(momentum.rsi14),
      macd_line: asNum(macd.line),
      macd_signal: asNum(macd.signal),
      macd_histogram: asNum(macd.histogram),
      bollinger_upper: asNum(bollinger.upper),
      bollinger_middle: asNum(bollinger.middle),
      bollinger_lower: asNum(bollinger.lower),
      bollinger_bandwidth: asNum(bollinger.bandwidth_pct),
      risk_flags: Array.isArray(metadata.risk_flags) ? metadata.risk_flags : [],
      factor_score: asNum(factor.score ?? factor.factorScore),
      factor_band: factor.band || "neutral",
      factor_components: factor.components || {},
      alert: {
        trigger: alert.trigger || "none",
        severity: alert.severity || "info",
        reason: alert.reason || "",
        matchedRules: Array.isArray(alert.matchedRules) ? alert.matchedRules : [],
      },
      alerts,
    };
  }

  function renderStatusStrip() {
    const provider = state.raw && state.raw.provider;
    const ageMinutes = getAgeMinutes(state.raw && (state.raw.as_of || state.raw.generated_at));
    const alerts = activeAlerts();
    const providerKind = provider && !provider.fallback_used ? "ok" : "warn";
    const ageKind = isNum(ageMinutes) && ageMinutes <= 20 && !(provider && provider.fallback_used) ? "ok" : "warn";

    setStatusValue(els.statusAsOf, fmtAsOf(state.raw && (state.raw.as_of || state.raw.generated_at)), ageKind);
    setStatusValue(els.statusDelay, fmtAge(ageMinutes), ageKind);
    setStatusValue(els.statusProvider, providerLabel(provider), providerKind);
    setStatusValue(els.statusAlerts, alerts.length ? `${alerts.length} 条` : "无", alerts.length ? "warn" : "ok");
  }

  function renderOverview() {
    const summary = (state.raw && state.raw.summary) || {};
    const count = state.stocks.length;
    const advancers = summary.advancing ?? 0;
    const decliners = summary.declining ?? 0;
    const unchanged = Math.max(0, count - advancers - decliners);
    const avgChange = average(state.stocks.map((stock) => stock.change_pct));
    const totalTurnover = sumBy(state.stocks, (stock) => stock.turnover);
    const fallbackCount = summary.fallback_count ?? countByFlag(["MOCK_DATA", "DEV_FALLBACK"]);
    const avgFactorScore = summary.average_factor_score ?? average(state.stocks.map((stock) => stock.factor_score));
    const provider = state.raw && state.raw.provider;

    const cards = [
      {
        label: "监控标的",
        value: `${count}`,
        sub: `<span class="ov-sub muted">${escapeHtml(providerLabel(provider))}</span>`,
        cls: "",
      },
      {
        label: "涨 / 跌 / 平",
        value: `${advancers} / ${decliners} / ${unchanged}`,
        sub: `<span class="ov-sub muted">watchlist breadth</span>`,
        cls: "",
      },
      {
        label: "平均涨跌幅",
        value: fmtPct(avgChange),
        sub: "",
        cls: ovDirClass(avgChange),
      },
      {
        label: "总成交额",
        value: fmtMoney(totalTurnover),
        sub: `<span class="ov-sub muted">HKD</span>`,
        cls: "",
      },
      {
        label: "平均 Factor Score",
        value: isNum(avgFactorScore) ? fmtNum(avgFactorScore, 1) : "—",
        sub: `<span class="ov-sub muted">${summary.alert_count ?? activeStockAlerts().length} 条规则触发</span>`,
        cls: isNum(avgFactorScore) ? ovDirClass(avgFactorScore - 50) : "",
      },
      {
        label: "回退标的",
        value: `${fallbackCount}`,
        sub: `<span class="ov-sub muted">${count ? ((fallbackCount / count) * 100).toFixed(0) : 0}% of watchlist</span>`,
        cls: fallbackCount ? "ov-down" : "ov-up",
      },
    ];

    els.overview.innerHTML = cards
      .map(
        (card) => `
        <div class="overview-card">
          <span class="ov-label">${card.label}</span>
          <span class="ov-value ${card.cls}">${card.value}</span>
          ${card.sub || ""}
        </div>`,
      )
      .join("");
  }

  function renderMacro() {
    const summary = (state.raw && state.raw.summary) || {};
    const count = state.stocks.length;
    const advancers = summary.advancing ?? 0;
    const decliners = summary.declining ?? 0;
    const avgChange = average(state.stocks.map((stock) => stock.change_pct));
    const growthAvg = sectorAverage(["Internet", "Consumer Internet", "E-Commerce", "Consumer Electronics"]);
    const defensiveAvg = sectorAverage(["Banking", "Insurance", "Telecom"]);
    const provider = state.raw && state.raw.provider;
    const ageMinutes = getAgeMinutes(state.raw && (state.raw.as_of || state.raw.generated_at));
    const regime = classifyRegime(avgChange, advancers, decliners);
    const regimeLabel = { positive: "偏多", negative: "偏空", neutral: "中性" }[regime];

    const drivers = [
      {
        label: "风险偏好",
        value: isNum(avgChange) ? fmtPct(avgChange) : "—",
        stance: regime,
        note: `${advancers}/${count} 只上涨，${decliners}/${count} 只下跌。`,
      },
      {
        label: "成长板块表现",
        value: isNum(growthAvg) ? fmtPct(growthAvg) : "—",
        stance: classifyStance(growthAvg),
        note: "互联网 / 电商 / 消费电子等高 Beta 板块均值。",
      },
      {
        label: "防御板块表现",
        value: isNum(defensiveAvg) ? fmtPct(defensiveAvg) : "—",
        stance: classifyStance(defensiveAvg),
        note: "银行 / 保险 / 电信等防御板块均值。",
      },
      {
        label: "行情源与时效",
        value: providerLabel(provider),
        stance: provider && provider.fallback_used ? "watch" : "neutral",
        note: `${fmtAge(ageMinutes)}${providerNote(provider) ? `；${providerNote(provider)}` : ""}`,
      },
    ];

    const head = `<span class="regime-pill ${regime}">${regimeLabel}</span>`;
    els.macro.querySelector("h3").innerHTML = `宏观环境 <span class="hint">Macro</span> ${head}`;
    els.macro.querySelector(".analysis-body").innerHTML = drivers
      .map(
        (driver) => `
        <div class="analysis-row">
          <span class="a-label"><span class="stance ${driver.stance}"></span>${escapeHtml(driver.label)}</span>
          <span class="a-meta">
            <span class="a-value">${escapeHtml(driver.value)}</span>
            ${driver.note ? `<span class="a-note">${escapeHtml(driver.note)}</span>` : ""}
          </span>
        </div>`,
      )
      .join("");
  }

  function renderMicro() {
    const summary = (state.raw && state.raw.summary) || {};
    const count = state.stocks.length;
    const advancers = summary.advancing ?? 0;
    const decliners = summary.declining ?? 0;
    const unchanged = Math.max(0, count - advancers - decliners);
    const leaders = state.stocks.slice().sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0));
    const top = leaders[0];
    const bottom = leaders[leaders.length - 1];
    const topTurnover = state.stocks.slice().sort((a, b) => (b.turnover || 0) - (a.turnover || 0))[0];
    const totalTurnover = sumBy(state.stocks, (stock) => stock.turnover);
    const topTurnoverShare = topTurnover && totalTurnover ? (topTurnover.turnover / totalTurnover) * 100 : null;
    const aboveMa20 = state.stocks.filter((stock) => isNum(stock.price) && isNum(stock.ma20) && stock.price >= stock.ma20).length;
    const overbought = state.stocks.filter((stock) => isNum(stock.rsi14) && stock.rsi14 >= 70).length;

    const items = [
      {
        label: "市场广度",
        value: `${advancers} 涨 / ${decliners} 跌 / ${unchanged} 平`,
        stance: advancers > decliners ? "positive" : decliners > advancers ? "negative" : "neutral",
      },
      {
        label: "领涨个股",
        value: top ? `${top.name} ${fmtPct(top.change_pct)}` : "—",
        stance: top ? dirClass(top.change_pct) : "neutral",
      },
      {
        label: "领跌个股",
        value: bottom ? `${bottom.name} ${fmtPct(bottom.change_pct)}` : "—",
        stance: bottom ? dirClass(bottom.change_pct) : "neutral",
      },
      {
        label: "量能集中度",
        value: topTurnover ? `${topTurnover.name} ${isNum(topTurnoverShare) ? `${topTurnoverShare.toFixed(1)}%` : ""}` : "—",
        stance: isNum(topTurnoverShare) && topTurnoverShare > 35 ? "watch" : "neutral",
      },
      {
        label: "站上 MA20",
        value: `${aboveMa20}/${count} 只`,
        stance: aboveMa20 > count / 2 ? "positive" : "neutral",
      },
      {
        label: "RSI > 70",
        value: `${overbought}/${count} 只`,
        stance: overbought > count / 2 ? "watch" : "neutral",
      },
    ];

    els.micro.querySelector(".analysis-body").innerHTML = items
      .map(
        (item) => `
        <div class="analysis-row">
          <span class="a-label"><span class="stance ${item.stance}"></span>${escapeHtml(item.label)}</span>
          <span class="a-meta"><span class="a-value">${escapeHtml(item.value)}</span></span>
        </div>`,
      )
      .join("");
  }

  function renderFilters() {
    const sectors = uniqueSorted(state.stocks.map((stock) => stock.sector));
    els.filterSector.innerHTML =
      '<option value="__ALL__">全部</option>' +
      sectors.map((sector) => `<option value="${escapeHtml(sector)}">${escapeHtml(sector)}</option>`).join("");
    state.filters.sector = sectors.includes(state.filters.sector) ? state.filters.sector : "__ALL__";
    els.filterSector.value = state.filters.sector;
    els.filterTrend.value = state.filters.trend;
    els.filterSearch.value = state.filters.search;
  }

  function applyFilters() {
    const { sector, trend, search } = state.filters;
    const query = search.trim().toLowerCase();
    return state.stocks.filter((stock) => {
      if (sector !== "__ALL__" && stock.sector !== sector) return false;
      if (trend !== "__ALL__" && stock.trend !== trend) return false;
      if (!query) return true;
      const haystack = [stock.name, stock.code, stock.ticker, stock.sector]
        .map((value) => String(value || "").toLowerCase())
        .join(" | ");
      return haystack.includes(query);
    });
  }

  function applySort(rows) {
    const dir = state.sortDir === "desc" ? -1 : 1;
    return rows.slice().sort((a, b) => dir * compareValues(a[state.sortKey], b[state.sortKey], state.sortKey));
  }

  function renderTable() {
    const rows = applySort(applyFilters());

    if (!rows.length) {
      els.body.innerHTML =
        '<tr><td colspan="7" class="empty">当前筛选下无匹配标的，请调整板块 / 趋势 / 关键字。</td></tr>';
    } else {
      els.body.innerHTML = rows
        .map((stock) => {
          const dc = dirClass(stock.change_pct);
          const selected = state.selected === stock.ticker ? "selected" : "";
          return `
          <tr data-ticker="${escapeHtml(stock.ticker)}" class="${selected}" tabindex="0">
            <td>
              <span class="eq-name">
                <span class="nm">${escapeHtml(stock.name)}</span>
                <span class="cd">${escapeHtml(stock.code || stock.ticker)}</span>
              </span>
            </td>
            <td>${escapeHtml(stock.sector)}</td>
            <td class="num">${fmtNum(stock.price)}</td>
            <td class="num chg ${dc}">${fmtPct(stock.change_pct)}</td>
            <td class="num">${fmtMoney(stock.turnover)}</td>
            <td class="num">${isNum(stock.pe_ttm) ? fmtNum(stock.pe_ttm, 1) : "—"}</td>
            <td class="num">${isNum(stock.dividend_yield) ? `${stock.dividend_yield.toFixed(2)}%` : "—"}</td>
          </tr>`;
        })
        .join("");
    }

    els.table.querySelectorAll("thead th[data-sort]").forEach((th) => {
      th.classList.remove("sort-asc", "sort-desc");
      if (th.dataset.sort === state.sortKey) {
        th.classList.add(state.sortDir === "asc" ? "sort-asc" : "sort-desc");
      }
    });
  }

  function metricCell(label, value, tipKey) {
    const tip = definitionText(tipKey);
    const info = tip ? `<span class="m-info" title="${escapeHtml(tip)}">i</span>` : "";
    return `
      <div class="metric">
        <span class="m-label">${escapeHtml(label)}${info}</span>
        <span class="m-value">${value}</span>
      </div>`;
  }

  function metricSection(title, metrics) {
    return `
      <section class="metric-section">
        <h4>${escapeHtml(title)}</h4>
        <div class="detail-grid">${metrics.join("")}</div>
      </section>`;
  }

  function riskFlagClass(flag) {
    return flag === "LIVE_DATA" ? "ok" : "warn";
  }

  function alertFlagClass(severity) {
    return severity === "info" ? "ok" : "warn";
  }

  function alertSeverityLabel(severity) {
    return {
      high: "高",
      medium: "中",
      low: "低",
      info: "提示",
    }[severity] || severity || "提示";
  }

  function renderDetail(ticker) {
    const stock = state.stocks.find((item) => item.ticker === ticker);
    if (!stock) return;
    state.selected = ticker;

    els.detailTitle.textContent = `${stock.name}（${stock.code || stock.ticker}）指标详情`;
    els.detailHint.textContent = `${stock.sector} · ${fmtAsOf(stock.as_of)} · ${stock.source_mode}`;

    const dc = dirClass(stock.change_pct);
    const changeText = `${fmtPct(stock.change_pct)} ${isNum(stock.change_abs) ? `(${stock.change_abs > 0 ? "+" : ""}${fmtNum(stock.change_abs)})` : ""}`;
    const flagList = stock.risk_flags.length
      ? stock.risk_flags
          .map((flag) => `<span class="flag ${riskFlagClass(flag)}">${escapeHtml(flag)}</span>`)
          .join("")
      : '<span class="flag ok">NO_EXTRA_FLAGS</span>';
    const alertFlagList = stock.alert.matchedRules.length
      ? stock.alert.matchedRules
          .map((rule) => `<span class="flag ${alertFlagClass(stock.alert.severity)}">${escapeHtml(rule)}</span>`)
          .join("")
      : '<span class="flag ok">NO_MATCHED_RULES</span>';

    const coreMetrics = [
      metricCell("现价", fmtNum(stock.price), "price"),
      metricCell("涨跌幅", fmtPct(stock.change_pct), "change_pct"),
      metricCell("涨跌额", isNum(stock.change_abs) ? fmtNum(stock.change_abs) : "—", "change_pct"),
      metricCell("成交量", fmtVolume(stock.volume), "turnover"),
      metricCell("成交额", fmtMoney(stock.turnover), "turnover"),
      metricCell("换手率", isNum(stock.turnover_rate) ? `${stock.turnover_rate.toFixed(2)}%` : "—", "turnover_rate"),
      metricCell("总市值", fmtMoney(stock.market_cap), "market_cap"),
    ];
    const alertMetrics = [
      metricCell("Factor Score", isNum(stock.factor_score) ? fmtNum(stock.factor_score, 1) : "—", "factor_score"),
      metricCell("Alert Trigger", escapeHtml(stock.alert.trigger || "none"), "factor_score"),
      metricCell("Alert Severity", escapeHtml(alertSeverityLabel(stock.alert.severity)), "factor_score"),
    ];
    const technicalMetrics = [
      metricCell("30日波动率", isNum(stock.volatility_daily) ? `${stock.volatility_daily.toFixed(2)}%` : "—", "volatility_daily"),
      metricCell("30日年化波动", isNum(stock.volatility_annualized) ? `${stock.volatility_annualized.toFixed(2)}%` : "—", "volatility_annualized"),
      metricCell("MA5", fmtNum(stock.ma5), "ma5"),
      metricCell("MA10", fmtNum(stock.ma10), "ma10"),
      metricCell("MA20", fmtNum(stock.ma20), "ma20"),
      metricCell("MA50", fmtNum(stock.ma50), "ma50"),
      metricCell("RSI(14)", isNum(stock.rsi14) ? fmtNum(stock.rsi14, 2) : "—", "rsi14"),
      metricCell("MACD Line", fmtNum(stock.macd_line, 4), "macd_line"),
      metricCell("MACD Signal", fmtNum(stock.macd_signal, 4), "macd_signal"),
      metricCell("MACD Histogram", fmtNum(stock.macd_histogram, 4), "macd_histogram"),
      metricCell("布林上轨", fmtNum(stock.bollinger_upper), "bollinger_upper"),
      metricCell("布林中轨", fmtNum(stock.bollinger_middle), "bollinger_middle"),
      metricCell("布林下轨", fmtNum(stock.bollinger_lower), "bollinger_lower"),
      metricCell("布林带宽", isNum(stock.bollinger_bandwidth) ? `${stock.bollinger_bandwidth.toFixed(2)}%` : "—", "bollinger_bandwidth"),
    ];
    const valuationMetrics = [
      metricCell("PE (TTM)", isNum(stock.pe_ttm) ? fmtNum(stock.pe_ttm, 1) : "—", "pe_ttm"),
      metricCell("PB", isNum(stock.pb) ? fmtNum(stock.pb, 2) : "—", "pb"),
      metricCell("EPS (TTM)", isNum(stock.eps_ttm) ? fmtNum(stock.eps_ttm, 2) : "—", "eps_ttm"),
      metricCell("股息率", isNum(stock.dividend_yield) ? `${stock.dividend_yield.toFixed(2)}%` : "—", "dividend_yield"),
    ];

    els.detailBody.innerHTML = `
      <div class="detail-head">
        <span class="price-big">${fmtNum(stock.price)}</span>
        <span class="chg ${dc}" style="font-size:16px;">${changeText}</span>
        <span class="sector-tag">${escapeHtml(stock.sector)}</span>
      </div>
      ${metricSection("Alert / Factor", alertMetrics)}
      <p class="detail-note">${escapeHtml(stock.alert.reason || "当前未触发额外规则。")}</p>
      ${metricSection("核心指标", coreMetrics)}
      ${metricSection("技术指标", technicalMetrics)}
      ${metricSection("估值 / 分红", valuationMetrics)}
      <div class="flag-list">${flagList}</div>
      <div class="flag-list">${alertFlagList}</div>
    `;

    els.body.querySelectorAll("tr[data-ticker]").forEach((tr) => {
      tr.classList.toggle("selected", tr.dataset.ticker === ticker);
    });
  }

  function renderRisk() {
    const notes = activeAlerts();
    const stockAlerts = activeStockAlerts().slice(0, 6);
    if (state.raw && state.raw.disclaimer) notes.push(state.raw.disclaimer);
    stockAlerts.forEach((stock) => {
      notes.push(
        `${stock.name}（${stock.code || stock.ticker}）[${alertSeverityLabel(stock.alert.severity)}] ${stock.alert.trigger}：${stock.alert.reason}（matchedRules: ${stock.alert.matchedRules.join(", ") || "none"}）`,
      );
    });
    els.riskList.innerHTML = notes.length
      ? notes.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
      : '<li class="muted">暂无活动告警，但仍请以交易所 / 券商官方实时数据为准。</li>';

    const entries = Object.entries(state.glossary);
    els.glossary.innerHTML = entries.length
      ? entries
          .map(([key, def]) => {
            const label = def.label || key;
            const extra = [
              def.description,
              def.formula ? `公式：${def.formula}` : "",
              def.unit ? `单位：${def.unit}` : "",
            ]
              .filter(Boolean)
              .join("；");
            return `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(extra)}</dd>`;
          })
          .join("")
      : '<dd class="muted">暂无指标解释。</dd>';
  }

  function applyHeaderTooltips() {
    els.table.querySelectorAll("th[data-tip]").forEach((th) => {
      const tip = definitionText(th.dataset.tip);
      if (tip) {
        th.setAttribute("data-tiptext", tip);
        th.setAttribute("title", tip);
      }
    });
  }

  function wireEvents() {
    els.filterSector.addEventListener("change", (e) => {
      state.filters.sector = e.target.value;
      renderTable();
    });
    els.filterTrend.addEventListener("change", (e) => {
      state.filters.trend = e.target.value;
      renderTable();
    });
    els.filterSearch.addEventListener("input", (e) => {
      state.filters.search = e.target.value;
      renderTable();
    });
    els.filterReset.addEventListener("click", () => {
      state.filters = { sector: "__ALL__", trend: "__ALL__", search: "" };
      els.filterSector.value = "__ALL__";
      els.filterTrend.value = "__ALL__";
      els.filterSearch.value = "";
      renderTable();
    });
    els.table.querySelectorAll("thead th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        const numericDefault = ["price", "change_pct", "turnover", "pe_ttm", "dividend_yield"].includes(key);
        if (state.sortKey === key) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = key;
          state.sortDir = numericDefault ? "desc" : "asc";
        }
        renderTable();
      });
    });
    els.body.addEventListener("click", (e) => {
      const tr = e.target.closest("tr[data-ticker]");
      if (tr) renderDetail(tr.dataset.ticker);
    });
    els.body.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const tr = e.target.closest("tr[data-ticker]");
      if (tr) {
        e.preventDefault();
        renderDetail(tr.dataset.ticker);
      }
    });
    if (els.refreshBtn) els.refreshBtn.addEventListener("click", () => load(true));
    if (els.autoRefresh) {
      els.autoRefresh.addEventListener("change", (e) => {
        if (e.target.checked) startAuto();
        else stopAuto();
      });
    }
  }

  function startAuto() {
    stopAuto();
    state.autoTimer = setInterval(() => load(true), AUTO_REFRESH_SECONDS * 1000);
  }

  function stopAuto() {
    if (state.autoTimer) {
      clearInterval(state.autoTimer);
      state.autoTimer = null;
    }
  }

  async function fetchSnapshot() {
    let lastError = null;
    for (const url of DATA_URLS) {
      try {
        const resp = await fetch(`${url}${url.includes("?") ? "&" : "?"}_=${Date.now()}`, { cache: "no-store" });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        state.activeUrl = url;
        return await resp.json();
      } catch (err) {
        lastError = err;
      }
    }
    throw lastError || new Error("No snapshot source available");
  }

  async function load(isRefresh) {
    setRefresh(isRefresh ? "刷新中…" : "载入中…", "loading");
    try {
      const json = await fetchSnapshot();
      state.raw = json;
      state.glossary = (json.metadata && json.metadata.indicator_definitions) || {};
      state.stocks = Array.isArray(json.watchlist) ? json.watchlist.map(normalizeStock) : [];

      if (!state.stocks.length) {
        renderStatusStrip();
        els.overview.innerHTML =
          '<div class="overview-card"><span class="ov-label">提示</span><span class="ov-value" style="font-size:15px;">监控列表暂无标的</span></div>';
        els.body.innerHTML =
          '<tr><td colspan="7" class="empty">监控列表为空：港股快照中的 <code>watchlist[]</code> 没有数据。</td></tr>';
        els.macro.querySelector(".analysis-body").innerHTML = '<p class="muted">暂无宏观数据。</p>';
        els.micro.querySelector(".analysis-body").innerHTML = '<p class="muted">暂无微观数据。</p>';
        renderRisk();
        setRefresh("数据为空", "warn");
        return;
      }

      renderStatusStrip();
      renderOverview();
      renderMacro();
      renderMicro();
      renderFilters();
      applyHeaderTooltips();
      renderTable();
      renderRisk();

      if (state.selected && state.stocks.some((stock) => stock.ticker === state.selected)) {
        renderDetail(state.selected);
      } else {
        renderDetail(state.stocks[0].ticker);
      }

      const provider = json.provider;
      const ageMinutes = getAgeMinutes(json.as_of || json.generated_at);
      const label = fmtAsOf(json.as_of || json.generated_at);
      const warn = activeAlerts().length > 0 || (provider && provider.fallback_used);
      setRefresh(
        `${providerLabel(provider)} · 快照 ${label} · 延迟 ${fmtAge(ageMinutes)}`,
        warn ? "warn" : "ok",
      );
    } catch (err) {
      console.error("[equities] failed to load HK stock snapshot:", err);
      setRefresh(`✗ 载入失败：${err.message || err}`, "warn");
      setStatusValue(els.statusAsOf, "—", "warn");
      setStatusValue(els.statusDelay, "—", "warn");
      setStatusValue(els.statusProvider, "读取失败", "warn");
      setStatusValue(els.statusAlerts, "读取失败", "warn");
      els.overview.innerHTML =
        '<div class="overview-card"><span class="ov-label">状态</span><span class="ov-value ov-down" style="font-size:15px;">数据载入失败</span></div>';
      els.body.innerHTML = `<tr><td colspan="7" class="empty">
        无法读取港股快照：${escapeHtml(err.message || String(err))}<br />
        已尝试：<code>${DATA_URLS.map((url) => escapeHtml(url)).join("</code>、<code>")}</code>
      </td></tr>`;
      els.macro.querySelector(".analysis-body").innerHTML = '<p class="muted">—</p>';
      els.micro.querySelector(".analysis-body").innerHTML = '<p class="muted">—</p>';
      els.detailBody.innerHTML = '<p class="muted">无法加载指标详情，请检查本地静态文件或 FastAPI 接口。</p>';
      els.riskList.innerHTML = '<li>港股快照读取失败，请检查 data/hk_stocks.json 或 /api/hk-stocks。</li>';
      els.glossary.innerHTML = '<dd class="muted">暂无指标解释。</dd>';
    }
  }

  function init() {
    wireEvents();
    load(false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
