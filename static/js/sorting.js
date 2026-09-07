/**
 * Click-to-sort table headers, shared by every view.
 *
 * The clickable thing is a real `<button>` inside the `<th>`, and the sort
 * direction is announced through `aria-sort` on the `<th>` itself — a bare
 * `<th>` with a click listener is invisible to anyone not using a mouse.
 */
import { $$, esc } from "./dom.js";

/**
 * @typedef {{col: string|null, asc: boolean}} SortState
 *   `col === null` means unsorted. Each view owns one of these.
 */

/**
 * Markup for one sortable header cell.
 *
 * @param {string} col The data key this column sorts on.
 * @param {string} label
 * @param {Object} [opts]
 * @param {string} [opts.cls] Extra classes for the `<th>` (`num`, `band`, ...).
 * @param {string} [opts.tone] Status tone, colouring the header like its column.
 * @returns {string} HTML.
 */
export function sortableTh(col, label, { cls = "", tone = "" } = {}) {
    return `<th class="sortable${cls ? " " + cls : ""}"${tone ? ` data-tone="${esc(tone)}"` : ""}>`
        + `<button type="button" data-col="${esc(col)}">${esc(label)}</button></th>`;
}

/**
 * Paint the `aria-sort` attributes for the active column.
 *
 * Kept separate from {@link makeSortable} because a view that resets its sort
 * on a fresh dataset needs to repaint without rebinding.
 *
 * @param {string} selector CSS selector for the sortable `<th>` elements.
 * @param {SortState} state
 */
export function paintSortIndicators(selector, state) {
    $$(selector).forEach((th) => {
        const col = th.querySelector("button")?.dataset.col;
        if (state.col && col === state.col) {
            th.setAttribute("aria-sort", state.asc ? "ascending" : "descending");
        } else {
            th.removeAttribute("aria-sort");
        }
    });
}

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
    $$(selector).forEach((th) => {
        const button = th.querySelector("button");
        if (!button) return;
        button.addEventListener("click", () => {
            const col = button.dataset.col;
            if (state.col === col) {
                if (state.asc) state.asc = false;
                else { state.col = null; state.asc = true; }
            } else {
                state.col = col;
                state.asc = true;
            }
            paintSortIndicators(selector, state);
            onRender();
        });
    });
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

/**
 * Sort grouped data at both levels: the groups by their rolled-up value, and
 * the rows inside each group.
 *
 * Sorting a grouped table by "NG descending" has to mean *the worst file first*,
 * not just the worst row first, so the group order comes from the aggregate
 * rather than from whichever child happens to sort highest.
 *
 * @param {Object[]} rows
 * @param {string[]} groupBy
 * @param {SortState} state
 * @param {Set<string>} numericCols
 * @param {(rows: Object[]) => Object} aggregate
 * @returns {Object[]} Rows reordered so grouping yields sorted groups.
 */
export function sortGrouped(rows, groupBy, state, numericCols, aggregate) {
    if (!state.col || !groupBy.length) return sortRows(rows, state, numericCols);

    const key = groupBy[0];
    const buckets = new Map();
    rows.forEach((r) => {
        const k = String(r[key] ?? "");
        if (!buckets.has(k)) buckets.set(k, []);
        buckets.get(k).push(r);
    });

    // A group is ordered by its own roll-up when the active column is one the
    // aggregate produces; otherwise the group key itself is the sensible order.
    const rolled = [...buckets.entries()].map(([k, group]) => ({
        k, group, agg: aggregate ? aggregate(group) : {},
    }));
    const sortable = rolled.map(({ k, agg }) => ({
        ...agg, [key]: k,
    }));
    const order = sortRows(sortable, state, numericCols).map((r) => r[key]);

    const out = [];
    order.forEach((k) => {
        const bucket = buckets.get(k);
        out.push(...sortRows(bucket, state, numericCols));
    });
    return out;
}
