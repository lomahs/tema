/**
 * Click-to-sort table headers, shared by the detail and daily views.
 */
import { $$ } from "./dom.js";

/**
 * @typedef {{col: string|null, asc: boolean}} SortState
 *   `col === null` means unsorted. Each view owns one of these.
 */

/**
 * Wire up header cells so clicking one cycles asc -> desc -> unsorted.
 *
 * Listeners are attached to the elements matching `selector` **at call time**.
 * Call this once for headers that live in the static template, but call it
 * again after any render that replaces the header cells — the replaced elements
 * take their old listeners with them, so this rebinds rather than duplicates.
 *
 * @param {string} selector CSS selector for the sortable `<th>` elements.
 * @param {SortState} state Mutated in place to record the active sort.
 * @param {() => void} onRender Re-renders the body once the state changes.
 */
export function makeSortable(selector, state, onRender) {
    $$(selector).forEach((th) => th.addEventListener("click", () => {
        const col = th.dataset.col;
        if (state.col === col) {
            if (state.asc) state.asc = false;
            else { state.col = null; state.asc = true; }
        } else {
            state.col = col;
            state.asc = true;
        }
        $$(selector).forEach((t) => t.classList.remove("sort-asc", "sort-desc"));
        if (state.col) th.classList.add(state.asc ? "sort-asc" : "sort-desc");
        onRender();
    }));
}

/**
 * Sort a copy of `rows` according to `state`.
 *
 * @param {Object[]} rows Not mutated.
 * @param {SortState} state
 * @param {Set<string>} numericCols Columns compared as numbers; everything else
 *   is compared as a case-insensitive string.
 * @returns {Object[]} `rows` itself when unsorted, otherwise a sorted copy.
 */
export function sortRows(rows, state, numericCols) {
    if (!state.col) return rows;
    const isNum = numericCols.has(state.col);
    return rows.slice().sort((a, b) => {
        const va = isNum ? (a[state.col] || 0) : String(a[state.col] || "").toLowerCase();
        const vb = isNum ? (b[state.col] || 0) : String(b[state.col] || "").toLowerCase();
        const cmp = isNum ? va - vb : va.localeCompare(vb);
        return state.asc ? cmp : -cmp;
    });
}
