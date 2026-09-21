/**
 * Narrowing and sorting: `allData` in, `filtered` out.
 *
 * Nothing here touches the DOM. `applyFilters` used to end by calling the four
 * render functions; that tail now lives in `refresh()` in `index.js`, because a
 * filter module that called the renderer and a renderer that re-filtered on
 * sort would be a cycle.
 */
import { getStatuses, lacksReason, sumRows } from "../../taxonomy.js";
import { sortGrouped, sortRows } from "../../sorting.js";
import { $ } from "../../dom.js";
import {
    DATE_FILTERS, FILTERS, chosenRawScopes, chosenScopes, detailSort,
    getAllData, getConditions, getMissingOnly, getScopeGroups, getSummaryRows,
    setConditions, setFiltered, setMissingOnly,
} from "./state.js";

/**
 * What to run when `clearNarrowing` has to repaint controls that `render.js`
 * owns.
 *
 * A callback rather than an import: `render.js` already imports this module
 * for `countsByScope`, so this module importing `render.js` back would be the
 * cycle Step 8 checks for. Installed once by `index.js`.
 */
let onCleared = () => {};

/** Installed once by `initDetailView`. */
export function setOnCleared(fn) { onCleared = fn; }

/** The active grouping keys, from the toolbar control. */
export function groupBy() {
    const v = $("#detailGroupBy").value;
    return v ? v.split(",") : [];
}

/**
 * Recompute `filtered` from the active filters, then redraw everything that
 * depends on it: stats, chips, table, pager and charts.
 *
 * The status choice is not among them — it decided which cases are here at all
 * — and neither is the scope choice, which `rebuild` applied on the way in.
 *
 * A case with no `test_date` is excluded as soon as either date bound is set.
 */
export function applyFilters() {
    const values = Object.fromEntries(
        [...FILTERS, ...DATE_FILTERS].map(({ id }) => [id, $("#" + id).value]));
    const q = $("#filterSearch").value.trim().toLowerCase();

    let filtered = getAllData().filter((d) => {
        for (const { id, field } of FILTERS) {
            if (values[id] && d[field] !== values[id]) return false;
        }
        // Empty means every scope, so an unpressed strip narrows nothing.
        if (chosenRawScopes.size && !chosenRawScopes.has(d.scope)) return false;
        if (getConditions().deviceFamily && d.device_family !== getConditions().deviceFamily) return false;
        if (getConditions().sheet && d.sheet !== getConditions().sheet) return false;
        const from = values.filterDateFrom;
        const to = values.filterDateTo;
        if (from && (!d.test_date || d.test_date < from)) return false;
        if (to && (!d.test_date || d.test_date > to)) return false;
        if (q && !matchesSearch(d, q)) return false;
        if (getMissingOnly() && !lacksReason(d)) return false;
        return true;
    });

    const keys = groupBy();
    const numeric = new Set(["row_num"]);
    filtered = keys.length
        ? sortGrouped(filtered, keys, detailSort, numeric, null)
        : sortRows(filtered, detailSort, numeric);
    setFiltered(filtered);
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

/** Every case of every status, per scope group, from the summary rows. */
export function countsByScope() {
    const counts = {};
    getScopeGroups().forEach((g) => {
        const totals = sumRows(getSummaryRows().filter((r) => r.scope === g.key));
        // Every status, not `total`: an excluded status is a case this screen
        // can list, and a card that would not count it is a card that lies
        // about how many rows pressing it adds.
        counts[g.key] = getStatuses().reduce((n, s) => n + (totals[s.key] || 0), 0);
    });
    return counts;
}

/** The scope groups that count toward the total — the selection this view opens on. */
export function defaultScopes() {
    chosenScopes.clear();
    getScopeGroups().filter((g) => g.counted !== false)
        .forEach((g) => chosenScopes.add(g.key));
}

/**
 * Clear everything that narrows the list, leaving the selection alone.
 *
 * The statuses and the scopes are deliberately untouched: they are what decides
 * which cases exist on this screen at all, and a "Clear all" that emptied the
 * table would be offering to show you nothing. The grouping choice is left too.
 */
export function clearNarrowing() {
    [...FILTERS, ...DATE_FILTERS].forEach(({ id }) => { $("#" + id).value = ""; });
    chosenRawScopes.clear();
    $("#filterSearch").value = "";
    setConditions({ deviceFamily: "", sheet: "" });
    setMissingOnly(false);
    onCleared();
}
