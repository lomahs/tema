/**
 * Summary view: one card per scope group, each holding a flat table.
 *
 * FPT work and JP work are separate commitments, so they are reported as
 * separate tables. A single table adding them together answers no question
 * anyone asks, and the two rarely move for the same reason. The backend splits
 * the rows; which Scope belongs to which table is configured in
 * `parser/scope_groups.json`, so this module never names a scope itself.
 *
 * That is the one place this screen departs from the design canvas, which has a
 * single table and a Scope dropdown. Everything else it draws is the design's:
 * the Device and File selects, the Rows combined/split toggle, the Executed
 * progress column, the condition chips and the Prev/Next/Show-all footer. The
 * Scope select is the one control that would be meaningless here — the scope is
 * the heading of the card you are already reading.
 *
 * The filters are shared across the cards, for the reason the sort is: the
 * tables have identical columns, so "iPad only" ought to mean the same thing
 * everywhere at once rather than in whichever table you happened to set it in.
 * Paging is *not* shared — a page number only means something within one table.
 *
 * The tables are deliberately **not** grouped internally. Every row carries its
 * own file and device, which is what makes it sortable on any column, readable
 * without opening anything, and safe to select and paste into Excel — a roll-up
 * row interleaved among the data would paste as a duplicate total.
 *
 * Owns the summary dataset, the scope group list, the shared filter and sort
 * state, and each card's page. The KPI cards and panels above the tables are
 * `summaryOverview.js` — it owns none of that state and re-renders on a
 * different trigger, so it is kept out of here.
 */
import { $, esc } from "../dom.js";
import { populateSelect, uniqueOf } from "../filters.js";
import { renderGroupedTable } from "../groupedTable.js";
import { renderPageFooter } from "../pagination.js";
import { makeSortable, paintSortIndicators, sortableTh, sortRows } from "../sorting.js";
import { getStatuses, statusCells, statusHeadCells, sumRows } from "../taxonomy.js";
import { executedPct, progressBar, renderOverview, scopeProgress } from "./summaryOverview.js";

/** @typedef {{key: string, label: string}} ScopeGroup */

/** Files per page, per card. The design's page size. */
const PAGE_SIZE = 10;

/** @type {Object[]} rows from /api/summary, each carrying its scope group key */
let groups = [];
/** @type {ScopeGroup[]} the tables to draw, in config order */
let scopes = [];

/** @type {import("../sorting.js").SortState} shared by every table */
const sort = { col: null, asc: true };

/**
 * Rows per (file, device) — the granularity the backend serves and the report
 * writes — or one row per file with the devices summed.
 *
 * The design defaults to combined. This defaults to split, because per-device
 * is what this table has always shown and what the published report is keyed
 * on; collapsing it silently would be a change of meaning, not of layout.
 *
 * @type {"split"|"combined"}
 */
let grouping = "split";

/** @type {Map<string, {page: number, showAll: boolean}>} keyed by scope key */
const paging = new Map();

/** No expansion here — the tables are flat — but the widget wants the set. */
const noExpansion = new Set();

const FILTERS = ["#summaryFilterDevice", "#summaryFilterFile"];

/**
 * Wire the shared controls. Call once, at startup.
 *
 * They live in the static template, so unlike the sortable headers they are
 * never replaced and must only be bound a single time.
 */
export function initSummaryView() {
    FILTERS.forEach((sel) => $(sel).addEventListener("change", () => {
        paging.clear();
        render();
    }));

    $("#btnSummaryGrouping").addEventListener("click", () => {
        grouping = grouping === "split" ? "combined" : "split";
        paging.clear();
        render();
    });

    $("#btnClearSummaryFilters").addEventListener("click", () => {
        FILTERS.forEach((sel) => { $(sel).value = ""; });
        paging.clear();
        render();
    });
}

/**
 * Adopt a fresh dataset and draw it.
 *
 * The overview is drawn once here rather than inside `render()`: it reports
 * over every row regardless of order, so re-sorting or paging a table must not
 * redraw it.
 *
 * @param {{groups: Object[], scopes: ScopeGroup[], missing_reason: Object[]}} data
 *   `/api/summary` body.
 * @param {Object[]} [dailyRows] `/api/daily` rows, for the activity line.
 */
export function renderSummary(data, dailyRows) {
    groups = data.groups || [];
    scopes = data.scopes || [];
    paging.clear();

    populateSelect("#summaryFilterDevice", uniqueOf(groups, "device"));
    populateSelect("#summaryFilterFile", uniqueOf(groups, "file"));

    renderOverview(data, dailyRows);
    render();
}

/** The shared filters, applied. */
function filtered() {
    const device = $("#summaryFilterDevice").value;
    const file = $("#summaryFilterFile").value;
    return groups.filter((r) => (!device || r.device === device) && (!file || r.file === file));
}

/**
 * Collapse a scope group's rows to one per file.
 *
 * The Device cell then reports how many devices were summed rather than naming
 * one — a cell reading "iPad" on a row that also counts an iPhone would be a
 * lie, and an empty one would look like missing data.
 *
 * @param {Object[]} rows
 * @returns {Object[]}
 */
function combine(rows) {
    const byFile = new Map();
    rows.forEach((r) => {
        if (!byFile.has(r.file)) byFile.set(r.file, []);
        byFile.get(r.file).push(r);
    });
    return [...byFile.entries()].map(([file, sub]) => {
        const devices = new Set(sub.map((r) => r.device).filter(Boolean)).size;
        return {
            ...sumRows(sub),
            file,
            device: devices ? `${devices} device${devices === 1 ? "" : "s"}` : "—",
        };
    });
}

/** The chips describing what is filtered out, and how to put it back. */
function chips() {
    const active = [
        { sel: "#summaryFilterDevice", label: "Device" },
        { sel: "#summaryFilterFile", label: "File" },
    ].filter(({ sel }) => $(sel).value);

    if (!active.length) return "";

    return `<div class="chips">
        <span class="eyebrow">Filtered</span>
        ${active.map(({ sel, label }) => `<span class="chip">
            ${esc(label)}: ${esc($(sel).value)}
            <button type="button" data-clear="${esc(sel)}" aria-label="Remove filter">×</button>
        </span>`).join("")}
        <button type="button" class="btn btn-quiet btn-sm" id="btnClearSummaryChips">Clear all</button>
    </div>`;
}

/**
 * Build every card: markup first, then bodies.
 *
 * The whole container is replaced on each render, which is what lets
 * `makeSortable` bind here without stacking a second listener on a header that
 * outlived the last draw — the old headers are gone with their listeners.
 */
function render() {
    const container = $("#summaryTables");
    const rows = filtered();

    $("#btnSummaryGrouping").textContent = grouping === "split" ? "Split" : "Combined";

    // An empty group is not drawn: a team with no JP work should not have to
    // scroll past an empty JP table to reach the numbers it does have.
    const present = scopes
        .map((s) => ({ scope: s, rows: rows.filter((r) => r.scope === s.key) }))
        .filter((p) => p.rows.length)
        .map((p) => ({ ...p, rows: grouping === "combined" ? combine(p.rows) : p.rows }));

    if (!present.length) {
        container.innerHTML = `<p class="empty-note">No test cases match these filters.</p>`;
        return;
    }

    // Addressed by position, not by scope key: a key is configured text and
    // would need escaping to survive an id attribute and a selector round trip.
    container.innerHTML = chips() + present.map(({ scope, rows: r }, i) => `
        <section class="card card--table">
            <div class="card-head card-head--row">
                <h2>${esc(scope.label)}</h2>
                <!-- Each group carries its own bar: FPT and JP are separate
                     commitments, so one of them running behind is a fact the
                     combined figure above would hide. -->
                ${scopeProgress(r)}
                <span class="count">${r.length} row${r.length === 1 ? "" : "s"}</span>
            </div>
            <div class="scroll-x scroll-x--flush scroll-x--rows">
                <table class="ledger">
                    <thead><tr id="summaryHead-${i}"></tr></thead>
                    <tbody id="summaryBody-${i}"></tbody>
                    <tfoot id="summaryFoot-${i}"></tfoot>
                </table>
            </div>
            <div class="card-foot" id="summaryFooter-${i}"></div>
        </section>`).join("");

    container.querySelectorAll("[data-clear]").forEach((b) =>
        b.addEventListener("click", () => {
            $(b.dataset.clear).value = "";
            paging.clear();
            render();
        }));
    const clearAll = $("#btnClearSummaryChips");
    if (clearAll) clearAll.addEventListener("click", () => $("#btnClearSummaryFilters").click());

    present.forEach(({ scope, rows: r }, i) => renderTable(i, scope, r));
}

/**
 * Fill one scope group's header, body, totals row and footer.
 *
 * @param {number} i The card's position among the drawn tables.
 * @param {ScopeGroup} scope
 * @param {Object[]} rows That group's rows, unsorted.
 */
function renderTable(i, scope, rows) {
    const head = `#summaryHead-${i}`;
    $(head).innerHTML =
        sortableTh("file", "File")
        + sortableTh("device", "Device")
        + statusHeadCells(sortableTh)
        // Not sortable, deliberately: it is a redrawing of the band beside it,
        // so a reader who wants that order has Total and the status columns.
        + `<th class="progress-col">Executed</th>`;
    // Every table re-renders, not just the one clicked: the sort state is shared,
    // so leaving the others alone would show two different orders at once.
    makeSortable(`${head} th.sortable`, sort, render);
    paintSortIndicators(`${head} th.sortable`, sort);

    const numeric = new Set(["total", ...getStatuses().map((s) => s.key)]);
    const sorted = sortRows(rows, sort, numeric);

    const state = paging.get(scope.key) || { page: 1, showAll: false };
    const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
    const page = Math.min(Math.max(1, state.page), pageCount);
    const visible = state.showAll
        ? sorted
        : sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    renderGroupedTable({
        container: `#summaryBody-${i}`,
        rows: visible,
        totalCols: 4 + getStatuses().length,
        expanded: noExpansion,
        // Every row stands on its own: both identity columns are filled in, so
        // a copied selection is complete without the header above it.
        renderLabelCells: (r) => `<td>${esc(r.file)}</td><td>${esc(r.device)}</td>`,
        labelCols: 2,
        renderValues: (r) => statusCells(r, { blankZeros: true }) + progressCell(r),
        onToggle: () => {},
        emptyMessage: "No test cases loaded.",
    });

    // The footer totals **every** row in the group, not the visible page — it
    // answers "where does this scope stand", which paging must not change.
    const totals = sumRows(sorted);
    $(`#summaryFoot-${i}`).innerHTML =
        `<tr><td colspan="2">Total</td>${statusCells(totals)}${progressCell(totals)}</tr>`;

    renderFooter(i, scope, sorted.length, page, pageCount, state.showAll);
}

/**
 * The Executed cell: the row's own progress bar, and the percentage beside it.
 *
 * The same `progressBar` the overview and the scope headings use, so a row, its
 * group and the whole load are all painted by one function.
 *
 * @param {Object} row A summary row, or a totals object.
 * @returns {string} HTML.
 */
function progressCell(row) {
    if (!row.total) return `<td class="progress-col"></td>`;
    return `<td class="progress-col"><span class="progress-cell">`
        + progressBar(row, "progress--sm")
        + `<span class="num">${executedPct(row)}%</span>`
        + `</span></td>`;
}

/**
 * One card's footer, from the shared widget.
 *
 * Review draws the same thing, so the markup and the paging arithmetic live in
 * `pagination.js` rather than here — two footers that drifted would be two
 * different answers to "is this all of it".
 */
function renderFooter(i, scope, count, page, pageCount, showAll) {
    const state = () => paging.get(scope.key) || { page: 1, showAll: false };
    renderPageFooter({
        container: `#summaryFooter-${i}`,
        totalItems: count,
        pageSize: PAGE_SIZE,
        currentPage: page,
        showAll,
        unit: "file",
        onPageChange: (p) => { paging.set(scope.key, { ...state(), page: p }); render(); },
        onToggleAll: (all) => { paging.set(scope.key, { page: 1, showAll: all }); render(); },
    });
}
