/**
 * Daily view: progress grouped by (file, device, PIC, date).
 *
 * Owns the daily dataset and its sort state.
 */
import { $, $$, esc } from "../dom.js";
import { populateSelect, uniqueOf } from "../filters.js";
import { renderPagination } from "../pagination.js";
import { makeSortable, sortRows } from "../sorting.js";
import { getStatuses, statusCells, statusTextClass, sumRows } from "../taxonomy.js";

const PAGE_SIZE = 10;

/** @type {Object[]} rows from /api/daily */
let dailyData = [];
/** @type {Object[]} `dailyData` after filters and sorting */
let dailyRows = [];
let currentPage = 1;

/** Column the table falls back to whenever a fresh dataset is adopted. */
const DEFAULT_SORT = { col: "date", asc: true };

/** @type {import("../sorting.js").SortState} */
const dailySort = { ...DEFAULT_SORT };

const FILTER_SELECTORS = [
    "#dailyFilterFile", "#dailyFilterDevice", "#dailyFilterPIC",
    "#dailyFilterDateFrom", "#dailyFilterDateTo",
];

/**
 * Attach the filter listeners. Call once, at startup.
 *
 * The filter controls live in the static template, so unlike the sortable
 * headers they are never replaced and must only be bound a single time.
 */
export function initDailyView() {
    FILTER_SELECTORS.forEach((sel) => $(sel).addEventListener("change", renderDaily));
}

/**
 * Build the daily table header from the taxonomy and make it sortable.
 *
 * This replaces `#dailyHead`'s contents, discarding the previous header cells
 * and their listeners, so calling {@link makeSortable} here rebinds rather than
 * stacking duplicates.
 */
export function renderDailyHead() {
    const base = [["date", "Date"], ["file", "File"], ["device", "Device"],
                  ["pic", "PIC"], ["total", "Total"]];
    $("#dailyHead").innerHTML =
        base.map(([col, label]) =>
            `<th class="daily-sortable" data-col="${esc(col)}">${esc(label)}</th>`).join("")
        + getStatuses().map((s) => {
            const cls = statusTextClass(s.key).replace(" fw-bold", "");
            return `<th class="daily-sortable${cls ? " " + cls : ""}" `
                 + `data-col="${esc(s.key)}">${esc(s.label)}</th>`;
        }).join("");
    makeSortable(".daily-sortable", dailySort, renderDaily);
}

/**
 * Adopt a fresh dataset: reset the sort to oldest-date-first, refill the
 * filters, redraw.
 *
 * Call {@link renderDailyHead} first — the header must reflect the current
 * taxonomy before the body is drawn against it, and the default sort indicator
 * is written onto the header cells this function finds.
 *
 * @param {Object[]} data `/api/daily` body.
 */
export function initDaily(data) {
    dailyData = data;
    dailySort.col = DEFAULT_SORT.col;
    dailySort.asc = DEFAULT_SORT.asc;
    $$(".daily-sortable").forEach((t) => {
        t.classList.remove("sort-asc", "sort-desc");
        if (t.dataset.col === dailySort.col) t.classList.add(dailySort.asc ? "sort-asc" : "sort-desc");
    });
    populateSelect("#dailyFilterFile", uniqueOf(data, "file"));
    populateSelect("#dailyFilterDevice", uniqueOf(data, "device"));
    populateSelect("#dailyFilterPIC", uniqueOf(data, "pic"));
    renderDaily();
}

/**
 * Recompute `dailyRows` from the current filters and sort, then redraw the
 * table and its pager from the first page.
 *
 * Any change of filter or sort order reshuffles the rows, so the view goes back
 * to page 1 rather than leaving the reader on a page that now holds other data.
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
    dailyRows = sortRows(rows, dailySort, numeric);

    currentPage = 1;
    renderDailyBody();
    renderDailyPagination();
}

/**
 * Draw the current page of `dailyRows` into the table body.
 *
 * The footer stays a total over *every* filtered row, not just the visible
 * page — it answers "how much matches the filters", which paging must not
 * change.
 */
function renderDailyBody() {
    const start = (currentPage - 1) * PAGE_SIZE;
    const page = dailyRows.slice(start, start + PAGE_SIZE);

    $("#dailyBody").innerHTML = page.map((r) => `<tr>
        <td>${esc(r.date)}</td><td>${esc(r.file)}</td>
        <td>${esc(r.device)}</td><td>${esc(r.pic)}</td>
        <td>${r.total}</td>
        ${statusCells(r, true)}
    </tr>`).join("");

    const totals = sumRows(dailyRows);
    $("#dailyFoot").innerHTML = `<tr>
        <td colspan="4">Total</td>
        <td>${totals.total}</td>
        ${statusCells(totals, true)}
    </tr>`;
}

/** Draw the pager, wiring page clicks back into the table body. */
function renderDailyPagination() {
    renderPagination({
        container: "#dailyPagination",
        totalItems: dailyRows.length,
        pageSize: PAGE_SIZE,
        currentPage,
        onPageChange: (page) => {
            currentPage = page;
            renderDailyBody();
            renderDailyPagination();
        },
    });
}
