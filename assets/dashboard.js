/**
 * HSBC HK Products Dashboard — static client.
 *
 * Loads data/products.json (relative path, works from both file:// preview
 * and GitHub Pages root deployment), renders a sortable + filterable table,
 * and shows a "no data" panel for categories the MVP does not yet cover.
 *
 * Side-effect free except for DOM manipulation. No analytics, no network
 * call other than the local JSON fetch.
 */
(function () {
  "use strict";

  // ---- DOM handles ---------------------------------------------------------
  const els = {
    statusLoad: document.getElementById("status-load"),
    statusFetched: document.getElementById("status-fetched"),
    statusTotal: document.getElementById("status-total"),
    statusFiltered: document.getElementById("status-filtered"),
    filterCategory: document.getElementById("filter-category"),
    filterCurrency: document.getElementById("filter-currency"),
    filterSearch: document.getElementById("filter-search"),
    filterReset: document.getElementById("filter-reset"),
    body: document.getElementById("products-body"),
    table: document.getElementById("products-table"),
  };

  /** Categories the scraper does NOT cover yet — surfaced explicitly to the user. */
  const NON_COVERED_CATEGORIES = [
    "Funds & Wealth Management",
    "Structured Products & Bonds",
    "FX & Precious Metals",
  ];

  // ---- State ---------------------------------------------------------------
  /** @type {{products: Array<Object>, fetched_at: string}} */
  const state = {
    raw: null,
    products: [],
    sortKey: "currency",
    sortDir: "asc",
    filters: { category: "__ALL__", currency: "__ALL__", search: "" },
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

  function fmtRate(r) {
    if (typeof r !== "number" || !isFinite(r)) return "—";
    // Always show at least 2 decimal places so 0.15 and 1.20 line up visually.
    return r.toFixed(2);
  }

  function uniqueSorted(arr) {
    return Array.from(new Set(arr.filter((x) => x !== undefined && x !== null && x !== "")))
      .sort((a, b) => String(a).localeCompare(String(b)));
  }

  function setStatus(msg, kind) {
    els.statusLoad.textContent = msg;
    els.statusLoad.classList.remove("warn", "ok");
    if (kind === "warn") els.statusLoad.classList.add("warn");
    if (kind === "ok") els.statusLoad.classList.add("ok");
  }

  // Tenor sort key — turns "1 week" / "3 months" / "12 months" into a number
  // so the UI sorts chronologically rather than alphabetically.
  function tenorRank(t) {
    if (!t) return Number.POSITIVE_INFINITY;
    const m = String(t).trim().toLowerCase().match(/^(\d+(?:\.\d+)?)\s*(day|days|week|weeks|month|months|year|years)/);
    if (!m) return Number.POSITIVE_INFINITY;
    const n = parseFloat(m[1]);
    const unit = m[2];
    if (unit.startsWith("day")) return n;
    if (unit.startsWith("week")) return n * 7;
    if (unit.startsWith("month")) return n * 30;
    if (unit.startsWith("year")) return n * 365;
    return Number.POSITIVE_INFINITY;
  }

  function compareValues(a, b, key) {
    if (key === "rate") {
      const av = typeof a === "number" ? a : Number.NEGATIVE_INFINITY;
      const bv = typeof b === "number" ? b : Number.NEGATIVE_INFINITY;
      return av - bv;
    }
    if (key === "tenor") {
      return tenorRank(a) - tenorRank(b);
    }
    return String(a == null ? "" : a).localeCompare(String(b == null ? "" : b));
  }

  // ---- Render --------------------------------------------------------------
  function renderFilters() {
    const cats = uniqueSorted(state.products.map((p) => p.category));
    const ccys = uniqueSorted(state.products.map((p) => p.currency));

    els.filterCategory.innerHTML =
      '<option value="__ALL__">全部</option>' +
      cats.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");

    els.filterCurrency.innerHTML =
      '<option value="__ALL__">全部</option>' +
      ccys.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
  }

  function applyFilters() {
    const { category, currency, search } = state.filters;
    const q = search.trim().toLowerCase();
    return state.products.filter((p) => {
      if (category !== "__ALL__" && p.category !== category) return false;
      if (currency !== "__ALL__" && p.currency !== currency) return false;
      if (q) {
        const hay = [
          p.name, p.category, p.currency, p.tenor,
          p.balance_band, p.risk_level, p.fee,
        ].map((x) => String(x || "").toLowerCase()).join(" | ");
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function applySort(rows) {
    const { sortKey, sortDir } = state;
    const dir = sortDir === "desc" ? -1 : 1;
    return rows.slice().sort((a, b) => dir * compareValues(a[sortKey], b[sortKey], sortKey));
  }

  function renderTable() {
    const rows = applySort(applyFilters());
    els.statusFiltered.textContent = `${rows.length} 條`;

    if (rows.length === 0) {
      els.body.innerHTML =
        '<tr><td colspan="7" class="empty">當前篩選下無匹配條目，請調整類別 / 幣種 / 關鍵字。</td></tr>';
      return;
    }

    const html = rows
      .map(
        (p) => `
        <tr>
          <td>${escapeHtml(p.category)}</td>
          <td>${escapeHtml(p.currency)}</td>
          <td>${escapeHtml(p.tenor)}</td>
          <td>${escapeHtml(p.balance_band)}</td>
          <td class="num">${fmtRate(p.rate)}</td>
          <td>${escapeHtml(p.risk_level)}</td>
          <td>${escapeHtml(p.fee)}</td>
        </tr>`,
      )
      .join("");
    els.body.innerHTML = html;

    // Update header sort indicators
    els.table.querySelectorAll("thead th[data-sort]").forEach((th) => {
      th.classList.remove("sort-asc", "sort-desc");
      if (th.dataset.sort === state.sortKey) {
        th.classList.add(state.sortDir === "asc" ? "sort-asc" : "sort-desc");
      }
    });
  }

  // ---- Wire-up -------------------------------------------------------------
  function wireEvents() {
    els.filterCategory.addEventListener("change", (e) => {
      state.filters.category = e.target.value;
      renderTable();
    });
    els.filterCurrency.addEventListener("change", (e) => {
      state.filters.currency = e.target.value;
      renderTable();
    });
    els.filterSearch.addEventListener("input", (e) => {
      state.filters.search = e.target.value;
      renderTable();
    });
    els.filterReset.addEventListener("click", () => {
      state.filters = { category: "__ALL__", currency: "__ALL__", search: "" };
      els.filterCategory.value = "__ALL__";
      els.filterCurrency.value = "__ALL__";
      els.filterSearch.value = "";
      renderTable();
    });
    els.table.querySelectorAll("thead th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (state.sortKey === key) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = key;
          state.sortDir = key === "rate" ? "desc" : "asc";
        }
        renderTable();
      });
    });
  }

  function showCoverageGaps(coveredCategories) {
    // (Optional) we already render a static fallback for missing categories
    // in HTML; here we tag any expected-but-missing ones with the live count.
    const list = document.getElementById("missing-categories");
    if (!list) return;
    NON_COVERED_CATEGORIES.forEach((c) => {
      if (coveredCategories.includes(c)) return; // covered → no banner needed
    });
    // Annotate the static items with a small footer noting last fetch.
  }

  async function main() {
    setStatus("載入中…");
    try {
      const resp = await fetch("data/products.json", { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      state.raw = json;
      state.products = Array.isArray(json.products) ? json.products : [];
      els.statusFetched.textContent = json.fetched_at || "—";
      els.statusTotal.textContent = `${state.products.length} 條`;
      if (state.products.length === 0) {
        setStatus("數據為空", "warn");
      } else {
        setStatus("✓ 已載入 (僅含定存)", "ok");
      }
      renderFilters();
      renderTable();
      const covered = uniqueSorted(state.products.map((p) => p.category));
      showCoverageGaps(covered);
    } catch (err) {
      console.error("[dashboard] failed to load data/products.json:", err);
      setStatus("✗ 載入失敗 — 請執行抓取腳本", "warn");
      els.statusFetched.textContent = "—";
      els.statusTotal.textContent = "—";
      els.statusFiltered.textContent = "—";
      els.body.innerHTML = `<tr><td colspan="7" class="empty">
        無法讀取 <code>data/products.json</code>：${escapeHtml(err.message || err)}<br />
        請先在本地執行 <code>python -m app.scraper</code>，再用 <code>python -m http.server</code> 預覽，或經由 GitHub Pages 訪問。
      </td></tr>`;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    wireEvents();
    main();
  });
})();
