/**
 * Summary view: one flat table per scope group, each with its own totals row.
 *
 * FPT work and JP work are separate commitments, so they are reported as
 * separate tables. A single table adding them together answers no question
 * anyone asks, and the two rarely move for the same reason. The backend splits
 * the rows; which Scope belongs to which table is configured in
 * `parser/scope_groups.json`, so this module never names a scope itself.
 *
 * The tables are deliberately **not** grouped internally. Every row carries its
 * own file and device, which is what makes it sortable on any column, readable
 * without opening anything, and safe to select and paste into Excel — a roll-up
 * row interleaved among the data would paste as a duplicate total.
 *
 * Sorting is shared: the tables have identical columns, so clicking "NG" ought
 * to mean "worst first" everywhere at once rather than in one table only.
 *
 * Owns the summary dataset, the scope group list and the single sort state.
 */
import { $, esc } from "../dom.js";
import { renderGroupedTable } from "../groupedTable.js";
import { makeSortable, paintSortIndicators, sortableTh, sortRows } from "../sorting.js";
import { getStatuses, statusCells, statusHeadCells, sumRows } from "../taxonomy.js";

/** @typedef {{key: string, label: string}} ScopeGroup */

/** @type {Object[]} rows from /api/summary, each carrying its scope group key */
let groups = [];
/** @type {ScopeGroup[]} the tables to draw, in config order */
let scopes = [];

/** @type {import("../sorting.js").SortState} shared by every table */
const sort = { col: null, asc: true };

/** No expansion here — the tables are flat — but the widget wants the set. */
const noExpansion = new Set();

/**
 * Adopt a fresh dataset and draw it.
 * @param {{groups: Object[], scopes: ScopeGroup[]}} data `/api/summary` body.
 */
export function renderSummary(data) {
    groups = data.groups || [];
    scopes = data.scopes || [];
    render();
}

/**
 * Build every table: markup first, then bodies.
 *
 * The whole container is replaced on each render, which is what lets
 * `makeSortable` bind here without stacking a second listener on a header that
 * outlived the last draw — the old headers are gone with their listeners.
 */
function render() {
    const container = $("#summaryTables");

    // An empty group is not drawn: a team with no JP work should not have to
    // scroll past an empty JP table to reach the numbers it does have.
    const present = scopes
        .map((s) => ({ scope: s, rows: groups.filter((r) => r.scope === s.key) }))
        .filter(({ rows }) => rows.length);

    if (!present.length) {
        container.innerHTML = `<p class="empty-note">No test cases loaded.</p>`;
        return;
    }

    // Addressed by position, not by scope key: a key is configured text and
    // would need escaping to survive an id attribute and a selector round trip.
    container.innerHTML = present.map(({ scope }, i) => `
        <section class="scope-block">
            <div class="toolbar">
                <strong>${esc(scope.label)}</strong>
                <div class="toolbar-end">
                    <span class="count" id="summaryCount-${i}"></span>
                </div>
            </div>
            <div class="scroll-x">
                <table class="ledger">
                    <thead><tr id="summaryHead-${i}"></tr></thead>
                    <tbody id="summaryBody-${i}"></tbody>
                    <tfoot id="summaryFoot-${i}"></tfoot>
                </table>
            </div>
        </section>`).join("");

    present.forEach(({ rows }, i) => renderTable(i, rows));
}

/**
 * Fill one scope group's header, body and totals row.
 *
 * @param {number} i The block's position among the drawn tables.
 * @param {Object[]} rows That group's rows, unsorted.
 */
function renderTable(i, rows) {
    const head = `#summaryHead-${i}`;
    $(head).innerHTML =
        sortableTh("file", "File")
        + sortableTh("device", "Device")
        + statusHeadCells(sortableTh);
    // Every table re-renders, not just the one clicked: the sort state is shared,
    // so leaving the others alone would show two different orders at once.
    makeSortable(`${head} th.sortable`, sort, render);
    paintSortIndicators(`${head} th.sortable`, sort);

    const numeric = new Set(["total", ...getStatuses().map((s) => s.key)]);
    const sorted = sortRows(rows, sort, numeric);

    renderGroupedTable({
        container: `#summaryBody-${i}`,
        rows: sorted,
        totalCols: 3 + getStatuses().length,
        expanded: noExpansion,
        // Every row stands on its own: both identity columns are filled in, so
        // a copied selection is complete without the header above it.
        renderLabelCells: (r) => `<td>${esc(r.file)}</td><td>${esc(r.device)}</td>`,
        labelCols: 2,
        renderValues: (r) => statusCells(r, { blankZeros: true }),
        onToggle: () => {},
        emptyMessage: "No test cases loaded.",
    });

    const totals = sumRows(rows);
    $(`#summaryFoot-${i}`).innerHTML =
        `<tr><td colspan="2">Total</td>${statusCells(totals)}</tr>`;
    $(`#summaryCount-${i}`).textContent =
        `${rows.length} row${rows.length === 1 ? "" : "s"}`;
}
