/**
 * Detail view: stat figures, filters, the case table, and the charts.
 *
 * Owns the full case list and the derived filtered / grouped / paged state.
 *
 * Grouping is optional here, unlike Summary and Daily. A flat list of cases is
 * the right default — you often want to scan or sort across every file at once
 * — so the group-by control starts at "No grouping" and paging counts rows.
 * Turn grouping on and paging counts groups instead, so a file never straddles
 * a page boundary.
 */
import { $, esc } from "../dom.js";
import { renderCharts, resizeCharts } from "../charts.js";
import { populateSelect, uniqueOf } from "../filters.js";
import { renderGroupedTable, toggleGroup } from "../groupedTable.js";
import { renderPagination } from "../pagination.js";
import { makeSortable, paintSortIndicators, sortableTh, sortGrouped, sortRows } from "../sorting.js";
import { getStatuses, requiresReason, toneFor } from "../taxonomy.js";

const PAGE_SIZE = 50;

/** Groups per page once grouping is on. */
const GROUP_PAGE_SIZE = 8;

const DEFAULT_EXPANDED = true;

/** @type {Object[]} every case from /api/data */
let allData = [];
/** @type {Object[]} `allData` after filters and sorting */
let filtered = [];
let currentPage = 1;

/** @type {Set<string>} which groups are open */
const expanded = new Set();

/** @type {import("../sorting.js").SortState} */
const detailSort = { col: null, asc: true };

/** Columns, in order. `col` is the sort key; a blank one is not sortable. */
const COLUMNS = [
    { col: "", label: "#", cls: "num" },
    { col: "file_name", label: "File" },
    { col: "sheet", label: "Sheet" },
    { col: "device", label: "Device" },
    { col: "row_num", label: "Row", cls: "num" },
    { col: "case_no", label: "Case no" },
    { col: "scope", label: "Scope" },
    { col: "result", label: "Result" },
    { col: "test_date", label: "Date" },
    { col: "pic", label: "PIC" },
    { col: "ticket_id", label: "Ticket ID" },
    { col: "note", label: "Note" },
];

/** Selects and inputs that narrow the list, with the label used on their chip. */
const FILTERS = [
    { id: "filterFile", field: "file_name", label: "File" },
    { id: "filterDevice", field: "device", label: "Device" },
    { id: "filterScope", field: "scope", label: "Scope" },
    { id: "filterResult", field: "result", label: "Result" },
    { id: "filterPIC", field: "pic", label: "PIC" },
];
const DATE_FILTERS = [
    { id: "filterDateFrom", label: "From" },
    { id: "filterDateTo", label: "To" },
];

/**
 * Attach the filter, search, grouping, clear and chart-toggle listeners. Call
 * once, at startup.
 *
 * The sortable headers are regenerated per taxonomy load, so they are bound in
 * {@link renderDetailHead} instead — binding them here as well would stack a
 * second listener and make one click sort twice.
 */
export function initDetailView() {
    const rerender = () => { currentPage = 1; applyFilters(); };

    [...FILTERS, ...DATE_FILTERS].forEach(({ id }) =>
        $("#" + id).addEventListener("change", rerender));
    $("#filterSearch").addEventListener("input", rerender);
    $("#detailGroupBy").addEventListener("change", rerender);

    $("#btnClearFilters").addEventListener("click", () => {
        clearFilters();
        rerender();
    });

    $("#btnToggleCharts").addEventListener("click", () => {
        const strip = $("#chartsRow");
        const show = strip.hidden;
        strip.hidden = !show;
        $("#btnToggleCharts").setAttribute("aria-expanded", String(show));
        $("#btnToggleCharts").textContent = show ? "Hide charts" : "Show charts";
        // Chart.js sizes to its container, which was 0x0 while the strip was hidden.
        if (show) resizeCharts();
    });
}

/** Clear every filter, leaving the grouping choice alone. */
function clearFilters() {
    [...FILTERS, ...DATE_FILTERS].forEach(({ id }) => { $("#" + id).value = ""; });
    $("#filterSearch").value = "";
}

/**
 * Build the detail header and make it sortable.
 *
 * Generated rather than written into the template so the sort buttons and their
 * `aria-sort` targets are built the same way as every other table's.
 */
export function renderDetailHead() {
    $("#detailHead").innerHTML = COLUMNS.map((c) => c.col
        ? sortableTh(c.col, c.label, { cls: c.cls || "" })
        : `<th${c.cls ? ` class="${c.cls}"` : ""}>${esc(c.label)}</th>`).join("");
    makeSortable("#detailHead th.sortable", detailSort, () => { currentPage = 1; applyFilters(); });
    paintSortIndicators("#detailHead th.sortable", detailSort);
}

/**
 * Adopt a fresh dataset, refill the filter dropdowns, and redraw.
 * @param {Object[]} cases `/api/data` body, each row carrying a `status` key.
 */
export function initDetail(cases) {
    allData = cases;
    expanded.clear();
    populateSelect("#filterFile", uniqueOf(allData, "file_name"));
    populateSelect("#filterDevice", uniqueOf(allData, "device"));
    populateSelect("#filterScope", uniqueOf(allData, "scope"));
    populateSelect("#filterResult", uniqueOf(allData, "result"));
    populateSelect("#filterPIC", uniqueOf(allData, "pic"));
    applyFilters();
}

/**
 * Focus the detail view on one case, coming from the summary view's list of
 * cases owing a reason.
 *
 * @param {{file: string, case_no: string}} c
 */
export function showCase(c) {
    clearFilters();
    $("#detailGroupBy").value = "";
    $("#filterFile").value = c.file || "";
    $("#filterSearch").value = c.case_no || "";
    currentPage = 1;
    applyFilters();
}

/** The active grouping keys, from the toolbar control. */
function groupBy() {
    const v = $("#detailGroupBy").value;
    return v ? v.split(",") : [];
}

/**
 * Recompute `filtered` from the active filters, then redraw everything that
 * depends on it: stats, chips, table, pager and charts.
 *
 * A case with no `test_date` is excluded as soon as either date bound is set.
 */
function applyFilters() {
    const values = Object.fromEntries(
        [...FILTERS, ...DATE_FILTERS].map(({ id }) => [id, $("#" + id).value]));
    const q = $("#filterSearch").value.trim().toLowerCase();

    filtered = allData.filter((d) => {
        for (const { id, field } of FILTERS) {
            if (values[id] && d[field] !== values[id]) return false;
        }
        const from = values.filterDateFrom;
        const to = values.filterDateTo;
        if (from && (!d.test_date || d.test_date < from)) return false;
        if (to && (!d.test_date || d.test_date > to)) return false;
        if (q && !matchesSearch(d, q)) return false;
        return true;
    });

    const keys = groupBy();
    const numeric = new Set(["row_num"]);
    filtered = keys.length
        ? sortGrouped(filtered, keys, detailSort, numeric, null)
        : sortRows(filtered, detailSort, numeric);

    renderStats();
    renderChips();
    renderTable();
    renderCharts(filtered);
}

/**
 * Free-text match across the fields a tester actually searches by.
 *
 * Deliberately not every field: matching on file name or device would duplicate
 * the dropdowns above and make a search for "iPhone" return everything.
 *
 * @param {Object} d
 * @param {string} q Already lower-cased.
 */
function matchesSearch(d, q) {
    return ["case_no", "ticket_id", "note", "sheet"]
        .some((f) => String(d[f] || "").toLowerCase().includes(q));
}

/** Update the stat figures and the "n / m cases" count. */
function renderStats() {
    const counts = {};
    getStatuses().forEach((s) => { counts[s.key] = 0; });
    filtered.forEach((d) => {
        if (counts[d.status] !== undefined) counts[d.status] += 1;
    });

    const setStat = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };
    setStat("statTotal", filtered.length);
    getStatuses().forEach((s) => setStat(`stat-${s.key}`, counts[s.key]));
    setStat("statFiles", new Set(filtered.map((d) => d.file_name)).size);

    $("#filteredCount").textContent = filtered.length === allData.length
        ? `${filtered.length} cases`
        : `${filtered.length} / ${allData.length} cases`;
}

/**
 * One dismissible chip per active filter.
 *
 * A select showing "iPhone 15" does not say *which* dimension it narrows once
 * you have looked away, and the date bounds are easy to forget entirely.
 */
function renderChips() {
    const chips = [];
    const push = (id, label, value) => {
        if (value) chips.push(`<span class="chip">${esc(label)}: ${esc(value)}`
            + `<button type="button" data-clear="${esc(id)}" aria-label="Clear ${esc(label)} filter">✕</button></span>`);
    };
    FILTERS.forEach(({ id, label }) => push(id, label, $("#" + id).value));
    DATE_FILTERS.forEach(({ id, label }) => push(id, label, $("#" + id).value));
    push("filterSearch", "Search", $("#filterSearch").value.trim());

    $("#detailChips").innerHTML = chips.join("");
    $("#detailChips").querySelectorAll("button[data-clear]").forEach((b) =>
        b.addEventListener("click", () => {
            $("#" + b.dataset.clear).value = "";
            currentPage = 1;
            applyFilters();
        }));
}

/**
 * Bootstrap-free class flagging a cell that should have been filled in.
 *
 * Three different rules apply:
 * - identity fields are always mandatory;
 * - result/date/PIC are only expected once *any* of the three is filled, so an
 *   untested case is not flagged, but a half-recorded one is;
 * - ticket id and note are required together (either satisfies) for the
 *   statuses the config marks as needing a reason.
 *
 * @param {Object} d A case row.
 * @param {string} field
 * @returns {string} `"flag"` or an empty string.
 */
function cellCls(d, field) {
    const v = d[field];
    if (["case_no", "file_name", "sheet", "device", "scope"].includes(field)) {
        return v ? "" : "flag";
    }
    if (["result", "test_date", "pic"].includes(field)) {
        const has = [d.result, d.test_date, d.pic].filter(Boolean).length;
        return has > 0 && !v ? "flag" : "";
    }
    if (field === "ticket_id" || field === "note") {
        return requiresReason(d.status) && !d.ticket_id && !d.note ? "flag" : "";
    }
    return "";
}

/**
 * One `<td>` for a field, carrying its validation highlight.
 * @param {Object} d
 * @param {string} field
 * @param {string} [extra] Extra classes.
 * @returns {string} HTML.
 */
function td(d, field, extra = "") {
    const cls = [cellCls(d, field), extra].filter(Boolean).join(" ");
    return `<td${cls ? ` class="${cls}"` : ""}>${esc(d[field])}</td>`;
}

/** Every cell of one case row. */
function caseCells(d, i) {
    return `<td class="num muted">${i + 1}</td>`
        + td(d, "file_name")
        + td(d, "sheet")
        + td(d, "device")
        + `<td class="num">${d.row_num}</td>`
        + td(d, "case_no", "mono")
        + td(d, "scope")
        + `<td class="${cellCls(d, "result")}">`
        + `<span class="badge" data-tone="${esc(toneFor(d.status))}">${esc(d.result)}</span></td>`
        + td(d, "test_date", "mono")
        + td(d, "pic")
        + td(d, "ticket_id", "mono")
        + td(d, "note");
}

/** The distinct top-level group values, in their sorted order. */
function groupValues(keys) {
    const seen = [];
    filtered.forEach((r) => {
        const v = String(r[keys[0]] ?? "");
        if (!seen.includes(v)) seen.push(v);
    });
    return seen;
}

/** Draw the current page, grouped or flat, plus its pager. */
function renderTable() {
    const keys = groupBy();

    if (!keys.length) {
        const start = (currentPage - 1) * PAGE_SIZE;
        renderGroupedTable({
            container: "#dataBody",
            rows: filtered.slice(start, start + PAGE_SIZE),
            totalCols: COLUMNS.length,
            expanded,
            renderLabelCells: () => "",
            labelCols: 0,
            renderValues: (d, i) => caseCells(d, start + i),
            onToggle: () => {},
            emptyMessage: "No cases match these filters.",
        });
        renderPagination({
            totalItems: filtered.length,
            pageSize: PAGE_SIZE,
            currentPage,
            onPageChange: (page) => { currentPage = page; renderTable(); },
        });
        return;
    }

    const values = groupValues(keys);
    const start = (currentPage - 1) * GROUP_PAGE_SIZE;
    const visible = new Set(values.slice(start, start + GROUP_PAGE_SIZE));
    const rows = filtered.filter((r) => visible.has(String(r[keys[0]] ?? "")));

    renderGroupedTable({
        container: "#dataBody",
        rows,
        groupBy: keys,
        mode: "span",
        summarise: (g) => `${g.length} case${g.length === 1 ? "" : "s"}`,
        totalCols: COLUMNS.length,
        expanded,
        defaultExpanded: DEFAULT_EXPANDED,
        renderLabelCells: () => "",
        labelCols: 0,
        renderValues: (d, i) => caseCells(d, i),
        onToggle: (path) => {
            toggleGroup(expanded, path, DEFAULT_EXPANDED);
            renderTable();
        },
        emptyMessage: "No cases match these filters.",
    });

    renderPagination({
        totalItems: values.length,
        pageSize: GROUP_PAGE_SIZE,
        currentPage,
        onPageChange: (page) => { currentPage = page; renderTable(); },
    });
}
