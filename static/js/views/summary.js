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
 * the Device and File selects, the Rows toggle, the Executed
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
import { $, $$, esc } from "../dom.js";
import { populateSelect, uniqueOf } from "../filters.js";
import { groupPath, renderGroupedTable } from "../groupedTable.js";
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
 * How many rows a file gets.
 *
 * - `split` — one per (file, device): the granularity the backend serves and
 *   the report writes.
 * - `family` — one per (file, device family): "iPhone Min size" and "iPhone Max
 *   size" are two device blocks in the workbook but one handset to anyone
 *   reading the totals. Which names make a family is configured in
 *   `parser/device_groups.json` and arrives on the row as `device_family`, so
 *   this module names no device of its own.
 * - `combined` — one per file, every device summed.
 *
 * The design defaults to combined. This defaults to split, because per-device
 * is what this table has always shown and what the published report is keyed
 * on; collapsing it silently would be a change of meaning, not of layout.
 *
 * None of the three changes a total — only how many rows carry it.
 *
 * @type {"split"|"family"|"combined"}
 */
let grouping = "split";

/** The cycle the Rows button walks, and what it reads in each state. */
const GROUPINGS = [
    { key: "split", label: "Split" },
    { key: "family", label: "By device type" },
    { key: "combined", label: "Combined" },
];

/** @type {{key: string, label: string}[]} from /api/summary, for naming a family */
let families = [];

/** @type {Map<string, {page: number, showAll: boolean}>} keyed by scope key */
const paging = new Map();

/** No expansion here — the tables are flat — but the widget wants the set. */
const noExpansion = new Set();

const FILTERS = ["#summaryFilterDevice", "#summaryFilterFile"];

/**
 * Called with a file name when one is clicked.
 *
 * A file cell is a way into the file view, but this module must not import it —
 * `main.js` owns the views, the same arrangement that keeps `views/detail.js`
 * out of here for the Missing reason jump.
 */
let onOpenFile = () => {};

/**
 * Wire the shared controls. Call once, at startup.
 *
 * They live in the static template, so unlike the sortable headers they are
 * never replaced and must only be bound a single time.
 *
 * @param {{onOpenFile?: (file: string) => void}} [opts] What to do when a file
 *   name is clicked. This module does not know there is a file view.
 */
export function initSummaryView({ onOpenFile: open = () => {} } = {}) {
    onOpenFile = open;

    // One listener for every table: the cards are regenerated per scope group
    // on each render, and a file cell is the same link in all of them.
    $("#summaryTables").addEventListener("click", (e) => {
        const cell = e.target.closest("button[data-file]");
        if (cell) onOpenFile(cell.dataset.file);
    });

    FILTERS.forEach((sel) => $(sel).addEventListener("change", () => {
        paging.clear();
        render();
    }));

    $("#btnSummaryGrouping").addEventListener("click", () => {
        const at = GROUPINGS.findIndex((g) => g.key === grouping);
        grouping = GROUPINGS[(at + 1) % GROUPINGS.length].key;
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
    families = data.device_families || [];
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

/**
 * Collapse a scope group's rows to one per (file, device family).
 *
 * The rows arrive already carrying `device_family` — the backend classifies a
 * device name once, so the merged rows here and the published report cannot
 * disagree about which block is which handset. A device no family claims is its
 * own family, keyed by its own name, so this hides nothing: the rows still add
 * up to exactly what Split shows.
 *
 * The Device cell reads the family's configured label and says how many devices
 * it merged when it merged more than one — unlike `combine`, naming the family
 * is not a lie, but "iPhone" standing for two blocks is worth knowing.
 *
 * @param {Object[]} rows
 * @returns {Object[]}
 */
function combineByFamily(rows) {
    const byKey = new Map();
    rows.forEach((r) => {
        const key = groupPath(r.file, r.device_family ?? r.device);
        if (!byKey.has(key)) byKey.set(key, []);
        byKey.get(key).push(r);
    });
    return [...byKey.values()].map((sub) => {
        const family = sub[0].device_family ?? sub[0].device;
        const label = families.find((f) => f.key === family)?.label || family;
        const devices = new Set(sub.map((r) => r.device).filter(Boolean)).size;
        return {
            ...sumRows(sub),
            file: sub[0].file,
            device_family: family,
            device: devices > 1 ? `${label} (${devices} devices)` : label,
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

    $("#btnSummaryGrouping").textContent =
        GROUPINGS.find((g) => g.key === grouping).label;

    // An empty group is not drawn: a team with no JP work should not have to
    // scroll past an empty JP table to reach the numbers it does have.
    const present = scopes
        .map((s) => ({ scope: s, rows: rows.filter((r) => r.scope === s.key) }))
        .filter((p) => p.rows.length)
        .map((p) => ({ ...p, rows: regroup(p.rows) }));

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
                <!-- A group outside the plan says so on its own heading. Its
                     table and its bar are drawn in full — the count has to stay
                     visible — but nothing in it reaches the figures above, and
                     a reader comparing the two would otherwise find them short
                     by this table with nothing on screen explaining why. The
                     dashed rule is the one the band draws where a status
                     column stops counting. -->
                ${scope.counted === false
                    ? `<span class="chip chip--aside" title="Reported, but not counted toward the totals above">Not in total</span>`
                    : ""}
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
    alignColumns();
}

/**
 * Give every scope group's table the same column widths.
 *
 * Each card is its own `<table>`, so a browser sizes each one to its own
 * content: FPT's File column is as wide as FPT's longest file name and JP's is
 * as wide as JP's. The status bands then start at different offsets and stop
 * lining up down the page — and the whole reason these are separate tables is
 * that a reader compares them, which means reading down a column.
 *
 * So: let the browser size them naturally, measure what each column came out
 * as, take the widest across the cards and pin every table to it. Measuring
 * rather than choosing widths is what keeps this honest when the taxonomy
 * changes — a status added in the Config view widens its column here the same
 * way it widens a single table, and nothing has to be told how wide a column
 * called "Pending (保留)" is.
 *
 * Pinning needs `table-layout: fixed`, under which the first row's widths
 * govern the whole table, so the header cells are the only ones set. The
 * container is rebuilt on every `render`, so the measurement is always of
 * freshly auto-sized tables and never of the last pass's pinned ones.
 *
 * A hidden view measures as zero — `render` runs before `showView` on the load
 * path — so this bails rather than pinning every column to nothing, and
 * `main.js` calls `alignSummaryColumns` when the view is shown. That is the
 * same arrangement `resizeCharts` needs and for the same reason.
 */
function alignColumns() {
    const tables = [...$$("#summaryTables table.ledger")];
    if (tables.length < 2) return;   // one table is already consistent with itself
    if (!tables[0].offsetParent) return;   // hidden: nothing has a width yet

    const widths = [];
    tables.forEach((table) => {
        [...table.tHead.rows[0].cells].forEach((cell, i) => {
            widths[i] = Math.max(widths[i] || 0, Math.ceil(cell.getBoundingClientRect().width));
        });
    });

    const total = widths.reduce((a, w) => a + w, 0);
    tables.forEach((table) => {
        table.style.tableLayout = "fixed";
        // Stated explicitly: a fixed-layout table left to size itself is not
        // obliged to add its columns up, and the pane's `overflow` still wants
        // something definite to decide whether it has to scroll.
        table.style.width = `${total}px`;
        [...table.tHead.rows[0].cells].forEach((cell, i) => {
            cell.style.width = `${widths[i]}px`;
        });
    });
}

/**
 * Align the tables now that they can be measured.
 *
 * `main.js` calls this when Summary is shown: the load path renders while the
 * view is still hidden, where every column measures zero.
 */
export function alignSummaryColumns() {
    alignColumns();
}

/** One scope group's rows at the granularity the Rows button is set to. */
function regroup(rows) {
    if (grouping === "combined") return combine(rows);
    if (grouping === "family") return combineByFamily(rows);
    return rows;
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
        // The file name is the way into that workbook's own page. A name is
        // plain text with no separator to lose, so unlike a group path it can
        // ride in the attribute; `esc` covers the quoting.
        renderLabelCells: (r) =>
            `<td><button type="button" class="cell-link" data-file="${esc(r.file)}"`
            + ` title="Open ${esc(r.file)}">${esc(r.file)}</button></td>`
            + `<td>${esc(r.device)}</td>`,
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
