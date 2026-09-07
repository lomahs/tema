/**
 * Summary view: files rolled up over their devices, plus the cases that are
 * missing a reason.
 *
 * The per-file roll-up rows are new — the API reports one row per (file,
 * device), and "how is this file doing overall" was previously a question the
 * app could not answer without adding up columns by eye.
 *
 * Owns the summary dataset, its sort state and its expansion state.
 */
import { $, esc } from "../dom.js";
import { renderGroupedTable, setAllGroups, toggleGroup } from "../groupedTable.js";
import { makeSortable, paintSortIndicators, sortableTh, sortGrouped } from "../sorting.js";
import { getStatuses, statusCells, statusHeadCells, sumRows, toneFor } from "../taxonomy.js";

const GROUP_BY = ["file"];
const DEFAULT_EXPANDED = true;

/** @type {Object[]} rows from /api/summary */
let groups = [];
/** @type {Object[]} the cases owing a ticket id or a note */
let missing = [];
/** @type {Set<string>} which files are open */
const expanded = new Set();

/** @type {import("../sorting.js").SortState} */
const sort = { col: null, asc: true };

/** Set by {@link initSummaryView}; opens a case in the detail view. */
let jumpToCase = () => {};

/**
 * Wire the controls that live in the static template. Call once, at startup.
 *
 * @param {Object} opts
 * @param {(c: Object) => void} opts.onJumpToCase Hands a missing-reason case to
 *   the detail view. Passed in rather than imported, so this module keeps
 *   knowing nothing about `views/detail.js`.
 */
export function initSummaryView({ onJumpToCase }) {
    jumpToCase = onJumpToCase;

    document.querySelectorAll('[data-expand="summary"]').forEach((btn) =>
        btn.addEventListener("click", () => {
            setAllGroups(expanded, groups, GROUP_BY, (r, k) => r[k], btn.dataset.all === "1");
            renderSummaryBody();
        }));
}

/**
 * Build the summary header from the taxonomy and make it sortable.
 *
 * Separate from the body render because the columns depend only on the status
 * list, not on the data. This replaces the header cells, so `makeSortable`
 * rebinds here rather than stacking duplicate listeners.
 */
export function renderSummaryHead() {
    $("#summaryHead").innerHTML =
        sortableTh("file", "File / device") + statusHeadCells(sortableTh);
    makeSortable("#summaryHead th.sortable", sort, renderSummaryBody);
    paintSortIndicators("#summaryHead th.sortable", sort);
}

/**
 * Adopt a fresh dataset and draw it.
 * @param {{groups: Object[], missing_reason: Object[]}} data `/api/summary` body.
 */
export function renderSummary(data) {
    groups = data.groups;
    missing = data.missing_reason;
    renderSummaryBody();
    renderMissingReason();
}

/** Column count, for the empty-state colspan. */
function totalCols() {
    return 2 + getStatuses().length;
}

/** Sort, group and draw the table plus its totals row. */
function renderSummaryBody() {
    const numeric = new Set(["total", ...getStatuses().map((s) => s.key)]);
    const rows = sortGrouped(groups, GROUP_BY, sort, numeric, sumRows);

    renderGroupedTable({
        container: "#summaryBody",
        rows,
        groupBy: GROUP_BY,
        aggregate: sumRows,
        renderValues: statusCells,
        renderLabelCells: (r) =>
            `<td class="cell-label" style="--depth:1">`
            + `<span class="twisty twisty--leaf"></span>${esc(r.device)}</td>`,
        labelCols: 1,
        totalCols: totalCols(),
        expanded,
        defaultExpanded: DEFAULT_EXPANDED,
        onToggle: (path) => {
            toggleGroup(expanded, path, DEFAULT_EXPANDED);
            renderSummaryBody();
        },
        emptyMessage: "No test cases loaded.",
    });

    const totals = sumRows(groups);
    $("#summaryFoot").innerHTML = `<tr><td>Total</td>${statusCells(totals)}</tr>`;
}

/**
 * Draw the cases owing a reason, or hide the section when there are none.
 *
 * Selecting a row opens it in the detail view — the list was previously a dead
 * end, naming problems with no way to reach them.
 */
function renderMissingReason() {
    const wrapper = $("#missingReasonWrapper");
    if (!missing.length) { wrapper.hidden = true; return; }
    wrapper.hidden = false;

    $("#missingReasonBody").innerHTML = missing.map((c, i) => `<tr tabindex="0" role="button"
        data-i="${i}" title="Open in Detail">
        <td>${esc(c.file)}</td><td>${esc(c.sheet)}</td>
        <td>${esc(c.device)}</td><td class="num">${c.row}</td>
        <td class="mono">${esc(c.case_no)}</td>
        <td><span class="badge" data-tone="${esc(toneFor(c.status || "Other"))}">${esc(c.result)}</span></td>
    </tr>`).join("");

    $("#missingReasonBody").querySelectorAll("tr[data-i]").forEach((tr) => {
        const open = () => jumpToCase(missing[Number(tr.dataset.i)]);
        tr.addEventListener("click", open);
        tr.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
        });
    });
}
