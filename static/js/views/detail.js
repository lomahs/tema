/**
 * Detail view: stat cards, filters, the paginated case table, and the charts.
 *
 * Owns the full case list and the derived filtered/paged state.
 */
import { $, esc } from "../dom.js";
import { renderCharts } from "../charts.js";
import { populateSelect, uniqueOf } from "../filters.js";
import { renderPagination } from "../pagination.js";
import { makeSortable, sortRows } from "../sorting.js";
import { badgeFor, getStatuses, requiresReason } from "../taxonomy.js";

const PAGE_SIZE = 50;

/** @type {Object[]} every case from /api/data */
let allData = [];
/** @type {Object[]} `allData` after filters and sorting */
let filtered = [];
let currentPage = 1;

/** @type {import("../sorting.js").SortState} */
const detailSort = { col: null, asc: true };

const FILTER_IDS = ["filterFile", "filterDevice", "filterScope", "filterResult", "filterPIC"];
const DATE_FILTER_IDS = ["filterDateFrom", "filterDateTo"];

/**
 * Attach the filter, clear-button and column-sort listeners. Call once, at
 * startup.
 *
 * The detail table's `<th class="sortable">` cells are written into the static
 * template and never regenerated, so they must be bound exactly once — binding
 * them per data load would stack listeners and make one click sort twice.
 */
export function initDetailView() {
    const rerender = () => { currentPage = 1; applyFilters(); };

    [...FILTER_IDS, ...DATE_FILTER_IDS].forEach((id) =>
        $("#" + id).addEventListener("change", rerender));

    $("#btnClearFilters").addEventListener("click", () => {
        [...FILTER_IDS, ...DATE_FILTER_IDS].forEach((id) => { $("#" + id).value = ""; });
        rerender();
    });

    makeSortable(".sortable", detailSort, rerender);
}

/**
 * Adopt a fresh dataset, refill the filter dropdowns, and redraw.
 * @param {Object[]} cases `/api/data` body, each row carrying a `status` key.
 */
export function initDetail(cases) {
    allData = cases;
    populateFilters();
    applyFilters();
}

/** Refill every filter dropdown from the values present in the data. */
function populateFilters() {
    populateSelect("#filterFile", uniqueOf(allData, "file_name"));
    populateSelect("#filterDevice", uniqueOf(allData, "device"));
    populateSelect("#filterScope", uniqueOf(allData, "scope"));
    populateSelect("#filterResult", uniqueOf(allData, "result"));
    populateSelect("#filterPIC", uniqueOf(allData, "pic"));
}

/**
 * Recompute `filtered` from the active filters, then redraw everything that
 * depends on it: stats, table, pager and charts.
 *
 * A case with no `test_date` is excluded as soon as either date bound is set.
 */
function applyFilters() {
    const ff = $("#filterFile").value;
    const fd = $("#filterDevice").value;
    const fs = $("#filterScope").value;
    const fr = $("#filterResult").value;
    const fp = $("#filterPIC").value;
    const dfrom = $("#filterDateFrom").value;
    const dto = $("#filterDateTo").value;

    filtered = allData.filter((d) => {
        if (ff && d.file_name !== ff) return false;
        if (fd && d.device !== fd) return false;
        if (fs && d.scope !== fs) return false;
        if (fr && d.result !== fr) return false;
        if (fp && d.pic !== fp) return false;
        if (dfrom && (!d.test_date || d.test_date < dfrom)) return false;
        if (dto && (!d.test_date || d.test_date > dto)) return false;
        return true;
    });

    filtered = sortRows(filtered, detailSort, new Set(["row_num"]));
    renderStats();
    renderTable();
    renderDetailPagination();
    renderCharts(filtered);
}

/** Update the stat cards and the "n / m cases" badge from `filtered`. */
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
 * Bootstrap class flagging a cell that should have been filled in.
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
 * @returns {string} `"table-danger"` or an empty string.
 */
function cellCls(d, field) {
    const v = d[field];
    if (["case_no", "file_name", "sheet", "device", "scope"].includes(field)) {
        return v ? "" : "table-danger";
    }
    if (["result", "test_date", "pic"].includes(field)) {
        const has = [d.result, d.test_date, d.pic].filter(Boolean).length;
        if (has > 0 && !v) return "table-danger";
        return "";
    }
    if (field === "ticket_id" || field === "note") {
        if (requiresReason(d.status) && !d.ticket_id && !d.note) return "table-danger";
        return "";
    }
    return "";
}

/**
 * One `<td>` for a field, carrying its validation highlight.
 * @param {Object} d
 * @param {string} field
 * @returns {string} HTML.
 */
function td(d, field) {
    const cls = cellCls(d, field);
    return `<td${cls ? ` class="${cls}"` : ""}>${esc(d[field])}</td>`;
}

/** Draw the current page of `filtered` into the table body. */
function renderTable() {
    const start = (currentPage - 1) * PAGE_SIZE;
    const page = filtered.slice(start, start + PAGE_SIZE);
    $("#dataBody").innerHTML = page.map((d, i) => `<tr>
        <td>${start + i + 1}</td>
        ${td(d, "file_name")}
        ${td(d, "sheet")}
        ${td(d, "device")}
        <td>${d.row_num}</td>
        ${td(d, "case_no")}
        ${td(d, "scope")}
        <td class="${cellCls(d, "result")}"><span class="badge ${esc(badgeFor(d.status) || "bg-secondary")}">${esc(d.result)}</span></td>
        ${td(d, "test_date")}
        ${td(d, "pic")}
        ${td(d, "ticket_id")}
        ${td(d, "note")}
    </tr>`).join("");
}

/** Draw the pager, wiring page clicks back into the table. */
function renderDetailPagination() {
    renderPagination({
        totalItems: filtered.length,
        pageSize: PAGE_SIZE,
        currentPage,
        onPageChange: (page) => {
            currentPage = page;
            renderTable();
            renderDetailPagination();
        },
    });
}
