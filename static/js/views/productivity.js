/**
 * Productivity view: executed cases per working day, per member.
 *
 * Sits under the daily table but deliberately ignores its filters — it answers
 * "how much does each member get through", a question about the whole dataset,
 * so `/api/productivity` does the counting and this module only draws it.
 *
 * Owns the productivity dataset and its sort state.
 */
import { $, $$, esc } from "../dom.js";
import { makeSortable, sortRows } from "../sorting.js";
import { getExecutedStatuses, statusTextClass } from "../taxonomy.js";

/** @type {Object[]} rows from /api/productivity */
let prodData = [];

/** Members are worth reading fastest-first, so the default sort is descending. */
const DEFAULT_SORT = { col: "productivity", asc: false };

/** @type {import("../sorting.js").SortState} */
const prodSort = { ...DEFAULT_SORT };

/** Columns that are not one of the executed statuses. */
const NUMERIC_BASE = ["executed", "days", "productivity"];

/**
 * Build the header from the taxonomy and make it sortable.
 *
 * This replaces `#productivityHead`'s contents, discarding the previous header
 * cells and their listeners, so calling {@link makeSortable} here rebinds rather
 * than stacking duplicates — the same arrangement the daily header uses.
 */
export function renderProductivityHead() {
    const statusHeads = getExecutedStatuses().map((s) => {
        const cls = statusTextClass(s.key).replace(" fw-bold", "");
        return `<th class="prod-sortable${cls ? " " + cls : ""}" `
             + `data-col="${esc(s.key)}">${esc(s.label)}</th>`;
    }).join("");

    $("#productivityHead").innerHTML =
        `<th class="prod-sortable" data-col="pic">PIC</th>`
        + statusHeads
        + `<th class="prod-sortable" data-col="executed">Executed</th>`
        + `<th class="prod-sortable" data-col="days">Working days</th>`
        + `<th class="prod-sortable" data-col="productivity">Cases / day</th>`;

    makeSortable(".prod-sortable", prodSort, renderProductivity);
}

/**
 * Adopt a fresh dataset: reset the sort to fastest-first and redraw.
 *
 * Call {@link renderProductivityHead} first — the header must reflect the
 * current taxonomy before the body is drawn against it, and the default sort
 * indicator is written onto the header cells this function finds.
 *
 * @param {Object[]} data `/api/productivity` body.
 */
export function initProductivity(data) {
    prodData = data;
    prodSort.col = DEFAULT_SORT.col;
    prodSort.asc = DEFAULT_SORT.asc;
    $$(".prod-sortable").forEach((t) => {
        t.classList.remove("sort-asc", "sort-desc");
        if (t.dataset.col === prodSort.col) {
            t.classList.add(prodSort.asc ? "sort-asc" : "sort-desc");
        }
    });
    renderProductivity();
}

/** Sort the rows by the active column and redraw the table. */
function renderProductivity() {
    const statuses = getExecutedStatuses();
    const numeric = new Set([...NUMERIC_BASE, ...statuses.map((s) => s.key)]);
    const rows = sortRows(prodData, prodSort, numeric);

    $("#productivityBody").innerHTML = rows.map((r) => `<tr>
        <td>${esc(r.pic)}</td>
        ${statuses.map((s) => {
            const cls = statusTextClass(s.key);
            return `<td${cls ? ` class="${cls}"` : ""}>${r[s.key] || ""}</td>`;
        }).join("")}
        <td>${r.executed}</td>
        <td>${r.days}</td>
        <td class="fw-bold">${r.productivity.toFixed(2)}</td>
    </tr>`).join("");

    renderProductivityFoot(rows, statuses);
}

/**
 * A team row under the table.
 *
 * `days` sums to person-days rather than calendar days — two members testing on
 * the same date are two days of work — which is exactly the denominator the
 * team's average rate wants.
 *
 * @param {Object[]} rows
 * @param {import("../taxonomy.js").Status[]} statuses
 */
function renderProductivityFoot(rows, statuses) {
    const sum = (field) => rows.reduce((acc, r) => acc + (r[field] || 0), 0);
    const executed = sum("executed");
    const days = sum("days");
    const rate = days ? executed / days : 0;

    $("#productivityFoot").innerHTML = `<tr>
        <td>Team</td>
        ${statuses.map((s) => `<td>${sum(s.key) || ""}</td>`).join("")}
        <td>${executed}</td>
        <td>${days}</td>
        <td>${rate.toFixed(2)}</td>
    </tr>`;
}
