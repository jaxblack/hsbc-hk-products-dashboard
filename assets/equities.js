/**
 * HK Equities monitoring — static client module.
 *
 * Loads data/hk_equities.json (relative path; works from file:// preview and
 * GitHub Pages root), renders:
 *   - overview cards (index, breadth, avg change, turnover)
 *   - macro / micro analysis cards
 *   - a sortable + filterable watchlist
 *   - a per-stock metric detail drawer with indicator tooltips
 *   - risk notes + an indicator glossary
 *   - a refresh-status pill with manual + (simulated) auto refresh
 *
 * Sample snapshot only — NOT a live market feed. Side-effect free except for
 * DOM manipulation; the only network call is the local JSON fetch.
 */
(function () {
  "use strict";

  const DATA_URL = "data/hk_equities.json";

  const els = {
    refreshStatus: document.getElementById("eq-refresh-status"),
    refreshDot: document.getElementById("eq-refresh-dot"),
    refreshText: document.getElementById("eq-refresh-text"),
    refreshBtn: document.getElementById("eq-refresh-btn"),
    autoRefresh: document.getElementById("eq-auto-refresh"),
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

  // If the section is not present (e.g. page variant without equities), bail.
  if (!els.body || !els.table) return;

  const state = {
    raw: null,
    stocks: [],
    glossary: {},
    sortKey: "change_pct",
    sortDir: "desc",
    selected: null,
    filters: { sector: "__ALL__", trend: "__ALL__", search: "" },
    autoTimer: null,
  };

  // ---- Helpers -------------------------------------------------------------
  const escapeHtml = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[m]);

  const isNum = (n) => typeof n === "number" && isFinite(n);

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

  // Compact CNY/HKD-style money: 亿 / 万.
  function fmtMoney(n) {
    if (!isNum(n)) return "—";
    const abs = Math.abs(n);
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

  function dirClass(n) {
    if (!isNum(n) || n === 0) return "flat";
    return n > 0 ? "up" : "down";
  }

  function ovDirClass(n) {
    if (!isNum(n) || n === 0) return "ov-flat";
    return n > 0 ? "ov-up" : "ov-down";
  }

  function uniqueSorted(arr) {
    return Array.from(new Set(arr.filter((x) => x !== undefined && x !== null && x !== "")))
      .sort((a, b) => String(a).localeCompare(String(b), "zh-Hans-CN"));
  }

  function setRefresh(text, kind) {
    if (els.refreshText) els.refreshText.textContent = text;
    if (!els.refreshStatus) return;
    els.refreshStatus.classList.remove("ok", "warn", "loading");
    if (kind) els.refreshStatus.classList.add(kind);
  }

  function compareValues(a, b, key) {
    const numKeys = ["price", "change_pct", "change_abs", "turnover", "volume", "pe_ttm", "pb", "dividend_yield", "market_cap"];
    if (numKeys.includes(key)) {
      const av = isNum(a) ? a : Number.NEGATIVE_INFINITY;
      const bv = isNum(b) ? b : Number.NEGATIVE_INFINITY;
      return av - bv;
    }
    return String(a == null ? "" : a).localeCompare(String(b == null ? "" : b), "zh-Hans-CN");
  }

  // ---- Render: overview ----------------------------------------------------
  function renderOverview() {
    const s = state.raw && state.raw.summary ? state.raw.summary : {};
    const idx = s.index || {};
    const cards = [
      {
        label: escapeHtml(idx.name || "恒生指数"),
        value: isNum(idx.value) ? fmtNum(idx.value) : "—",
        sub: isNum(idx.change_pct)
          ? `<span class="ov-sub ${ovDirClass(idx.change_pct)}">${fmtPct(idx.change_pct)} (${idx.change_abs > 0 ? "+" : ""}${fmtNum(idx.change_abs)})</span>`
          : "",
        cls: ovDirClass(idx.change_pct),
      },
      {
        label: "涨 / 跌 / 平",
        value: `${s.advancers ?? "—"} / ${s.decliners ?? "—"} / ${s.unchanged ?? "—"}`,
        sub: `<span class="ov-sub muted">${state.stocks.length} 只标的</span>`,
        cls: "",
      },
      {
        label: "平均涨跌幅",
        value: isNum(s.avg_change_pct) ? fmtPct(s.avg_change_pct) : "—",
        sub: "",
        cls: ovDirClass(s.avg_change_pct),
      },
      {
        label: "总成交额",
        value: fmtMoney(s.total_turnover),
        sub: `<span class="ov-sub muted">HKD</span>`,
        cls: "",
      },
    ];
    els.overview.innerHTML = cards
      .map(
        (c) => `
        <div class="overview-card">
          <span class="ov-label">${c.label}</span>
          <span class="ov-value ${c.cls}">${c.value}</span>
          ${c.sub || ""}
        </div>`,
      )
      .join("");
  }

  // ---- Render: macro / micro ----------------------------------------------
  function renderMacro() {
    const m = state.raw && state.raw.macro;
    if (!m) {
      els.macro.querySelector(".analysis-body").innerHTML = '<p class="muted">暂无宏观数据。</p>';
      return;
    }
    const regime = String(m.regime || "neutral");
    const regimeLabel = { positive: "偏多", negative: "偏空", neutral: "中性" }[regime] || regime;
    const head = `<span class="regime-pill ${escapeHtml(regime)}">${escapeHtml(regimeLabel)}</span>`;
    els.macro.querySelector("h3").innerHTML = `宏观环境 <span class="hint">Macro</span> ${head}`;
    const rows = (m.drivers || [])
      .map(
        (d) => `
        <div class="analysis-row">
          <span class="a-label"><span class="stance ${escapeHtml(d.stance || "neutral")}"></span>${escapeHtml(d.label)}</span>
          <span class="a-meta">
            <span class="a-value">${escapeHtml(d.value)}</span>
            ${d.note ? `<span class="a-note">${escapeHtml(d.note)}</span>` : ""}
          </span>
        </div>`,
      )
      .join("");
    els.macro.querySelector(".analysis-body").innerHTML = rows || '<p class="muted">暂无宏观数据。</p>';
  }

  function renderMicro() {
    const m = state.raw && state.raw.micro;
    if (!m) {
      els.micro.querySelector(".analysis-body").innerHTML = '<p class="muted">暂无微观数据。</p>';
      return;
    }
    const rows = (m.items || [])
      .map(
        (it) => `
        <div class="analysis-row">
          <span class="a-label"><span class="stance ${escapeHtml(it.stance || "neutral")}"></span>${escapeHtml(it.label)}</span>
          <span class="a-meta"><span class="a-value">${escapeHtml(it.value)}</span></span>
        </div>`,
      )
      .join("");
    els.micro.querySelector(".analysis-body").innerHTML = rows || '<p class="muted">暂无微观数据。</p>';
  }

  // ---- Render: filters -----------------------------------------------------
  function renderFilters() {
    const sectors = uniqueSorted(state.stocks.map((s) => s.sector));
    els.filterSector.innerHTML =
      '<option value="__ALL__">全部</option>' +
      sectors.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
  }

  function applyFilters() {
    const { sector, trend, search } = state.filters;
    const q = search.trim().toLowerCase();
    return state.stocks.filter((s) => {
      if (sector !== "__ALL__" && s.sector !== sector) return false;
      if (trend !== "__ALL__" && (s.trend || "flat") !== trend) return false;
      if (q) {
        const hay = [s.name, s.name_en, s.ticker, s.code, s.sector]
          .map((x) => String(x || "").toLowerCase())
          .join(" | ");
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function applySort(rows) {
    const dir = state.sortDir === "desc" ? -1 : 1;
    return rows.slice().sort((a, b) => dir * compareValues(a[state.sortKey], b[state.sortKey], state.sortKey));
  }

  // ---- Render: table -------------------------------------------------------
  function renderTable() {
    const rows = applySort(applyFilters());

    if (rows.length === 0) {
      els.body.innerHTML =
        '<tr><td colspan="7" class="empty">当前筛选下无匹配标的，请调整板块 / 趋势 / 关键字。</td></tr>';
    } else {
      els.body.innerHTML = rows
        .map((s) => {
          const dc = dirClass(s.change_pct);
          const sel = state.selected === s.ticker ? "selected" : "";
          return `
          <tr data-ticker="${escapeHtml(s.ticker)}" class="${sel}" tabindex="0">
            <td>
              <span class="eq-name">
                <span class="nm">${escapeHtml(s.name)}</span>
                <span class="cd">${escapeHtml(s.code || s.ticker)}</span>
              </span>
            </td>
            <td>${escapeHtml(s.sector)}</td>
            <td class="num">${fmtNum(s.price)}</td>
            <td class="num chg ${dc}">${fmtPct(s.change_pct)}</td>
            <td class="num">${fmtMoney(s.turnover)}</td>
            <td class="num">${isNum(s.pe_ttm) ? fmtNum(s.pe_ttm, 1) : "—"}</td>
            <td class="num">${isNum(s.dividend_yield) ? s.dividend_yield.toFixed(2) + "%" : "—"}</td>
          </tr>`;
        })
        .join("");
    }

    // header sort indicators
    els.table.querySelectorAll("thead th[data-sort]").forEach((th) => {
      th.classList.remove("sort-asc", "sort-desc");
      if (th.dataset.sort === state.sortKey) {
        th.classList.add(state.sortDir === "asc" ? "sort-asc" : "sort-desc");
      }
    });
  }

  // ---- Render: detail drawer ----------------------------------------------
  function metricCell(label, value, tipKey) {
    const tip = tipKey && state.glossary[tipKey] ? state.glossary[tipKey] : "";
    const info = tip ? `<span class="m-info" title="${escapeHtml(tip)}">i</span>` : "";
    return `
      <div class="metric">
        <span class="m-label">${escapeHtml(label)}${info}</span>
        <span class="m-value">${value}</span>
      </div>`;
  }

  function renderDetail(ticker) {
    const s = state.stocks.find((x) => x.ticker === ticker);
    if (!s) return;
    state.selected = ticker;

    els.detailTitle.textContent = `${s.name}（${s.code || s.ticker}）指标详情`;
    els.detailHint.textContent = `${s.sector || ""}`;

    const dc = dirClass(s.change_pct);
    const chgTxt = `${fmtPct(s.change_pct)} ${isNum(s.change_abs) ? `(${s.change_abs > 0 ? "+" : ""}${fmtNum(s.change_abs)})` : ""}`;

    // 52-week range marker position (0..100%)
    let rangeHtml = "";
    if (isNum(s.week52_low) && isNum(s.week52_high) && s.week52_high > s.week52_low && isNum(s.price)) {
      const pct = Math.max(0, Math.min(100, ((s.price - s.week52_low) / (s.week52_high - s.week52_low)) * 100));
      rangeHtml = `
        <div class="range-bar" aria-label="52周区间位置">
          <div class="rb-track"><div class="rb-mark" style="left:${pct.toFixed(1)}%"></div></div>
          <div class="rb-legend"><span>52周低 ${fmtNum(s.week52_low)}</span><span>现价 ${fmtNum(s.price)}</span><span>52周高 ${fmtNum(s.week52_high)}</span></div>
        </div>`;
    }

    els.detailBody.innerHTML = `
      <div class="detail-head">
        <span class="price-big">${fmtNum(s.price)}</span>
        <span class="chg ${dc}" style="font-size:16px;">${chgTxt}</span>
        <span class="sector-tag">${escapeHtml(s.sector || "")}</span>
      </div>
      <div class="detail-grid">
        ${metricCell("开盘", fmtNum(s.open), "open")}
        ${metricCell("昨收", fmtNum(s.prev_close), "prev_close")}
        ${metricCell("最高", fmtNum(s.day_high), "day_high")}
        ${metricCell("最低", fmtNum(s.day_low), "day_low")}
        ${metricCell("成交量", fmtVolume(s.volume), "volume")}
        ${metricCell("成交额", fmtMoney(s.turnover), "turnover")}
        ${metricCell("总市值", fmtMoney(s.market_cap), "market_cap")}
        ${metricCell("PE (TTM)", isNum(s.pe_ttm) ? fmtNum(s.pe_ttm, 1) : "—", "pe_ttm")}
        ${metricCell("PB", isNum(s.pb) ? fmtNum(s.pb, 2) : "—", "pb")}
        ${metricCell("股息率", isNum(s.dividend_yield) ? s.dividend_yield.toFixed(2) + "%" : "—", "dividend_yield")}
        ${metricCell("Beta", isNum(s.beta) ? fmtNum(s.beta, 2) : "—", "beta")}
      </div>
      ${rangeHtml}
      ${s.note ? `<p class="detail-note">📝 ${escapeHtml(s.note)}</p>` : ""}
    `;

    // reflect selection in table
    els.body.querySelectorAll("tr[data-ticker]").forEach((tr) => {
      tr.classList.toggle("selected", tr.dataset.ticker === ticker);
    });
  }

  // ---- Render: risk + glossary --------------------------------------------
  function renderRisk() {
    const notes = (state.raw && state.raw.risk_notes) || [];
    els.riskList.innerHTML = notes.length
      ? notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")
      : '<li class="muted">暂无额外风险提示。</li>';

    const g = state.glossary || {};
    const keys = Object.keys(g);
    els.glossary.innerHTML = keys.length
      ? keys.map((k) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(g[k])}</dd>`).join("")
      : '<dd class="muted">暂无指标解释。</dd>';
  }

  // ---- Tooltips on table headers ------------------------------------------
  function applyHeaderTooltips() {
    els.table.querySelectorAll("th[data-tip]").forEach((th) => {
      const key = th.dataset.tip;
      const tip = state.glossary[key];
      if (tip) {
        th.setAttribute("data-tiptext", tip);
        th.setAttribute("title", tip); // a11y / no-CSS fallback
      }
    });
  }

  // ---- Wire-up -------------------------------------------------------------
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

    // Row selection (click + keyboard)
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
    const secs = (state.raw && state.raw.refresh_interval_seconds) || 60;
    state.autoTimer = setInterval(() => load(true), Math.max(10, secs) * 1000);
  }
  function stopAuto() {
    if (state.autoTimer) {
      clearInterval(state.autoTimer);
      state.autoTimer = null;
    }
  }

  // ---- Load ----------------------------------------------------------------
  function fmtClock(d) {
    return d.toLocaleTimeString("zh-Hans-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  }

  async function load(isRefresh) {
    setRefresh(isRefresh ? "刷新中…" : "载入中…", "loading");
    try {
      const resp = await fetch(`${DATA_URL}?_=${Date.now()}`, { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      state.raw = json;
      state.stocks = Array.isArray(json.stocks) ? json.stocks : [];
      state.glossary = json.indicator_glossary || {};

      if (state.stocks.length === 0) {
        // Empty-data state: keep panels but show clear messaging.
        setRefresh("数据为空", "warn");
        els.overview.innerHTML =
          '<div class="overview-card"><span class="ov-label">提示</span><span class="ov-value" style="font-size:15px;">监控列表暂无标的</span></div>';
        els.body.innerHTML =
          '<tr><td colspan="7" class="empty">监控列表为空：data/hk_equities.json 中 <code>stocks[]</code> 没有数据。</td></tr>';
        renderMacro();
        renderMicro();
        renderRisk();
        return;
      }

      renderOverview();
      renderMacro();
      renderMicro();
      renderFilters();
      applyHeaderTooltips();
      renderTable();
      renderRisk();

      // Keep selection if still present; otherwise default to the first row.
      if (state.selected && state.stocks.some((s) => s.ticker === state.selected)) {
        renderDetail(state.selected);
      } else if (state.stocks.length) {
        renderDetail(state.stocks[0].ticker);
      }

      const label = json.as_of_label || json.fetched_at || "";
      const isOpen = json.market_status === "open";
      const statusKind = isOpen ? "ok" : "warn";
      const marketTxt = isOpen ? "开市" : "休市";
      const clock = fmtClock(new Date());
      setRefresh(`${marketTxt} · ${label || "示例快照"} · 刷新于 ${clock}`, statusKind);
    } catch (err) {
      // Error state: visible, actionable, non-fatal.
      // eslint-disable-next-line no-console
      console.error("[equities] failed to load", DATA_URL, err);
      setRefresh(`✗ 载入失败：${err.message || err}`, "warn");
      els.overview.innerHTML =
        '<div class="overview-card"><span class="ov-label">状态</span><span class="ov-value ov-down" style="font-size:15px;">数据载入失败</span></div>';
      els.body.innerHTML = `<tr><td colspan="7" class="empty">
        无法读取 <code>${escapeHtml(DATA_URL)}</code>：${escapeHtml(err.message || String(err))}<br />
        请通过 <code>python -m http.server</code> 本地预览，或经由 GitHub Pages 访问（<code>file://</code> 下 fetch 会被浏览器 CORS 拦截）。
      </td></tr>`;
      const macroBody = els.macro && els.macro.querySelector(".analysis-body");
      const microBody = els.micro && els.micro.querySelector(".analysis-body");
      if (macroBody) macroBody.innerHTML = '<p class="muted">—</p>';
      if (microBody) microBody.innerHTML = '<p class="muted">—</p>';
    }
  }

  // ---- Bootstrap -----------------------------------------------------------
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