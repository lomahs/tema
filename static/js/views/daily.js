/**
 * Daily view: progress grouped by date, with each date rolling up the
 * (file, device, PIC) rows beneath it.
 *
 * Paging here counts **date groups**, not rows — a page that cut a date in half
 * would make the roll-up above it a lie. `pagination.js` needs no change for
 * that; it is handed the group count.
 *
 * Owns the daily dataset, its sort state and its expansion state.
 */
import { $, esc } from "../dom.js";
import { populateSelect, uniqueOf } from "../filters.js";
import { groupPath, renderGroupedTable, setAllGroups, toggleGroup } from "../groupedTable.js";
import { renderPagination } from "../pagination.js";
import { makeSortable, paintSortIndicators, sortableTh, sortGrouped } from "../sorting.js";
import { getStatuses, statusCells, statusHeadCells, sumRows } from "../taxonomy.js";

/** Dates per page. A date is a group, however many rows it holds. */
const PAGE_SIZE = 10;

const GROUP_BY = ["date"];

/** Most dates are history; the one being worked on is the one worth opening. */
const DEFAULT_EXPANDED = false;

/** @type {Object[]} rows from /api/daily */
let dailyData = [];
/** @type {Object[]} `dailyData` after filters and sorting */
let dailyRows = [];
let currentPage = 1;

/** @type {Set<string>} which dates are open */
const expanded = new Set();

/** A daily log reads newest-first. */
const DEFAULT_SORT = { col: "date", asc: false };

/** @type {import("../sorting.js").SortState} */
const dailySort = { ...DEFAULT_SORT };

const FILTER_SELECTORS = [
    "#dailyFilterFile", "#dailyFilterDevice", "#dailyFilterPIC",
    "#dailyFilterDateFrom", "#dailyFilterDateTo",
];

/**
 * Attach the filter, clear and expand-all listeners. Call once, at startup.
 *
 * These controls live in the static template, so unlike the sortable headers
 * they are never replaced and must only be bound a single time.
 */
export function initDailyView() {
    FILTER_SELECTORS.forEach((sel) => $(sel).addEventListener("change", renderDaily));

    $("#btnClearDailyFilters").addEventListener("click", () => {
        FILTER_SELECTORS.forEach((sel) => { $(sel).value = ""; });
        renderDaily();
    });

    document.querySelectorAll('[data-expand="daily"]').forEach((btn) =>
        btn.addEventListener("click", () => {
            setAllGroups(expanded, dailyRows, GROUP_BY, (r, k) => r[k], btn.dataset.all === "1");
            renderDailyBody();
        }));
}

/**
 * Build the daily header from the taxonomy and make it sortable.
 *
 * This replaces `#dailyHead`'s contents, discarding the previous header cells
 * and their listeners, so `makeSortable` rebinds here rather than stacking
 * duplicates.
 */
export function renderDailyHead() {
    $("#dailyHead").innerHTML =
        sortableTh("date", "Date")
        + sortableTh("file", "File")
        + sortableTh("device", "Device")
        + sortableTh("pic", "PIC")
        + statusHeadCells(sortableTh);
    makeSortable("#dailyHead th.sortable", dailySort, renderDaily);
    paintSortIndicators("#dailyHead th.sortable", dailySort);
}

/**
 * Adopt a fresh dataset: reset the sort to newest-first, open the most recent
 * date, refill the filters, redraw.
 *
 * Call {@link renderDailyHead} first — the header must reflect the current
 * taxonomy before the body is drawn against it.
 *
 * @param {Object[]} data `/api/daily` body.
 */
export function initDaily(data) {
    dailyData = data;
    dailySort.col = DEFAULT_SORT.col;
    dailySort.asc = DEFAULT_SORT.asc;
    paintSortIndicators("#dailyHead th.sortable", dailySort);

    // Everything closed except the latest date: a log of thirty days should
    // open on the day you are actually working on.
    expanded.clear();
    const latest = data.reduce((max, r) => (r.date > max ? r.date : max), "");
    if (latest) expanded.add(groupPath(latest));

    populateSelect("#dailyFilterFile", uniqueOf(data, "file"));
    populateSelect("#dailyFilterDevice", uniqueOf(data, "device"));
    populateSelect("#dailyFilterPIC", uniqueOf(data, "pic"));
    renderDaily();
}

/** Column count, for colspans. */
function totalCols() {
    return 5 + getStatuses().length;
}

/**
 * Recompute `dailyRows` from the current filters and sort, then redraw from the
 * first page.
 *
 * Any change of filter or sort reshuffles the rows, so the view goes back to
 * page 1 rather than leaving the reader on a page that now holds other data.
 *
 * Dates are compared as ISO strings, which orders correctly without parsing.
 */
function renderDaily() {
    const ff = $("#dailyFilterFile").value;
    const fd = $("#dailyFilterDevice").value;
    const fp = $("#dailyFilterPIC").value;
    const dfrom = $("#dailyFilterDateFrom").value;
    const dto = $("#dailyFilterDateTo").value;

    const rows = dailyData.filter((r) => {
        if (ff && r.file !== ff) return false;
        if (fd && r.device !== fd) return false;
        if (fp && r.pic !== fp) return false;
        if (dfrom && r.date < dfrom) return false;
        if (dto && r.date > dto) return false;
        return true;
    });

    const numeric = new Set(["total", ...getStatuses().map((s) => s.key)]);
    dailyRows = sortGrouped(rows, GROUP_BY, dailySort, numeric, sumRows);

    currentPage = 1;
    renderDailyBody();
}

/** The distinct dates, in the order they appear after sorting. */
function pageDates() {
    const seen = [];
    dailyRows.forEach((r) => { if (!seen.includes(r.date)) seen.push(r.date); });
    return seen;
}

/**
 * Draw the current page of date groups.
 *
 * The footer totals **every** filtered row, not just the visible page — it
 * answers "how much matches the filters", which paging must not change.
 */
function renderDailyBody() {
    const dates = pageDates();
    const start = (currentPage - 1) * PAGE_SIZE;
    const visible = new Set(dates.slice(start, start + PAGE_SIZE));
    const rows = dailyRows.filter((r) => visible.has(r.date));

    renderGroupedTable({
        container: "#dailyBody",
        rows,
        groupBy: GROUP_BY,
        aggregate: sumRows,
        renderValues: statusCells,
        renderLabelCells: (r) => `<td></td>`
            + `<td>${esc(r.file)}</td><td>${esc(r.device)}</td><td>${esc(r.pic)}</td>`,
        labelCols: 4,
        totalCols: totalCols(),
        expanded,
        defaultExpanded: DEFAULT_EXPANDED,
        onToggle: (path) => {
            toggleGroup(expanded, path, DEFAULT_EXPANDED);
            renderDailyBody();
        },
        emptyMessage: "No days match these filters.",
    });

    const totals = sumRows(dailyRows);
    $("#dailyFoot").innerHTML =
        `<tr><td colspan="4">Total</td>${statusCells(totals)}</tr>`;

    renderPagination({
        container: "#dailyPagination",
        totalItems: dates.length,
        pageSize: PAGE_SIZE,
        currentPage,
        onPageChange: (page) => { currentPage = page; renderDailyBody(); },
    });
}
