/**
 * Summary view: a flat row per (file, device), plus the cases owing a reason.
 *
 * The main table is deliberately **not** grouped. Every row carries its own
 * file and device, which is what makes it sortable on any column, readable
 * without opening anything, and safe to select and paste into Excel — a
 * roll-up row interleaved among the data would paste as a duplicate total.
 *
 * The issue list underneath is the opposite case: nobody copies it, and it is
 * long and repetitive, so that is where collapsing earns its keep.
 *
 * Owns the summary dataset, both sort states and the issue list's expansion.
 */
import { $, esc } from "../dom.js";
import { renderGroupedTable, setAllGroups, toggleGroup } from "../groupedTable.js";
import { makeSortable, paintSortIndicators, sortableTh, sortRows } from "../sorting.js";
import { getStatuses, statusCells, statusHeadCells, sumRows, toneFor } from "../taxonomy.js";

/** @type {Object[]} rows from /api/summary */
let groups = [];
/** @type {Object[]} the cases owing a ticket id or a note */
let missing = [];

/** @type {Set<string>} which issue groups are open */
const expanded = new Set();
const ISSUE_DEFAULT_EXPANDED = true;

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

    $("#issueGroupBy").addEventListener("change", renderMissingReason);

    document.querySelectorAll('[data-expand="issues"]').forEach((btn) =>
        btn.addEventListener("click", () => {
            setAllGroups(expanded, missing, issueGroupBy(), (r, k) => String(r[k] ?? ""),
                         btn.dataset.all === "1");
            renderMissingReason();
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
        sortableTh("file", "File")
        + sortableTh("device", "Device")
        + statusHeadCells(sortableTh);
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
    expanded.clear();
    renderSummaryBody();
    renderMissingReason();
}

/** Sort and draw the flat table plus its totals row. */
function renderSummaryBody() {
    const numeric = new Set(["total", ...getStatuses().map((s) => s.key)]);
    const rows = sortRows(groups, sort, numeric);

    renderGroupedTable({
        container: "#summaryBody",
        rows,
        totalCols: 3 + getStatuses().length,
        expanded,
        // Every row stands on its own: both identity columns are filled in, so
        // a copied selection is complete without the header above it.
        renderLabelCells: (r) => `<td>${esc(r.file)}</td><td>${esc(r.device)}</td>`,
        labelCols: 2,
        renderValues: (r) => statusCells(r, { blankZeros: true }),
        onToggle: () => {},
        emptyMessage: "No test cases loaded.",
    });

    const totals = sumRows(groups);
    $("#summaryFoot").innerHTML = `<tr><td colspan="2">Total</td>${statusCells(totals)}</tr>`;
    $("#summaryCount").textContent = `${rows.length} row${rows.length === 1 ? "" : "s"}`;
}

/** The active grouping keys for the issue list. */
function issueGroupBy() {
    const v = $("#issueGroupBy").value;
    return v ? v.split(",") : [];
}

/**
 * Draw the cases owing a reason, or hide the section when there are none.
 *
 * Grouped, unlike the table above: this list is read to chase things up, never
 * copied, and collapsing it turns forty scattered rows into a handful of
 * headings you can work through. Selecting a row opens it in the detail view —
 * it was previously a dead end, naming problems with no way to reach them.
 */
function renderMissingReason() {
    const wrapper = $("#missingReasonWrapper");
    if (!missing.length) { wrapper.hidden = true; return; }
    wrapper.hidden = false;

    // Object identity is stable here — the rows come straight from the payload
    // — so the click handler can find its case without an index in the DOM.
    const indexOf = new Map(missing.map((c, i) => [c, i]));
    const keys = issueGroupBy();

    renderGroupedTable({
        container: "#missingReasonBody",
        rows: missing,
        groupBy: keys,
        mode: "span",
        summarise: (g) => `${g.length} case${g.length === 1 ? "" : "s"}`,
        totalCols: 6,
        expanded,
        defaultExpanded: ISSUE_DEFAULT_EXPANDED,
        renderLabelCells: () => "",
        labelCols: 0,
        leafAttrs: (c) => `data-i="${indexOf.get(c)}" tabindex="0" role="button" title="Open in Detail"`,
        renderValues: (c) => `<td>${esc(c.file)}</td><td>${esc(c.sheet)}</td>`
            + `<td>${esc(c.device)}</td><td class="num">${c.row}</td>`
            + `<td class="mono">${esc(c.case_no)}</td>`
            + `<td><span class="badge" data-tone="${esc(toneFor(c.status))}">${esc(c.result)}</span></td>`,
        onToggle: (path) => {
            toggleGroup(expanded, path, ISSUE_DEFAULT_EXPANDED);
            renderMissingReason();
        },
        emptyMessage: "Nothing owing a reason.",
    });

    $("#missingReasonBody").querySelectorAll("tr[data-i]").forEach((tr) => {
        const open = () => jumpToCase(missing[Number(tr.dataset.i)]);
        tr.addEventListener("click", open);
        tr.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
        });
    });

    $("#issueCount").textContent = `${missing.length} case${missing.length === 1 ? "" : "s"}`;
}
