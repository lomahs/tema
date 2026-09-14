/**
 * Productivity view: executed cases per working day, per member.
 *
 * Sits under the daily table but deliberately ignores its filters — it answers
 * "how much does each member get through", a question about the whole dataset,
 * so `/api/productivity` does the counting and this module only draws it. That
 * is also why it re-renders on sort and never on a filter change.
 *
 * Owns the productivity dataset and its sort state.
 */
import { $, esc } from "../dom.js";
import { makeSortable, paintSortIndicators, sortableTh, sortRows } from "../sorting.js";
import { getExecutedStatuses, toneFor } from "../taxonomy.js";
import { getTarget, onTargetChange, setTarget } from "../target.js";

/** @type {Object[]} rows from /api/productivity */
let prodData = [];

/** Members are worth reading fastest-first, so the default sort is descending. */
const DEFAULT_SORT = { col: "productivity", asc: false };

/** @type {import("../sorting.js").SortState} */
const prodSort = { ...DEFAULT_SORT };

/** Columns that are not one of the executed statuses. */
const NUMERIC_BASE = ["executed", "days", "productivity"];

/**
 * Wire the target input. Call once, at startup.
 *
 * This view owns the *control*; `target.js` owns the value, because the Daily
 * chart reads it too. Typing here redraws both.
 */
export function initProductivityView() {
    const input = $("#productivityTarget");
    input.value = String(getTarget());
    input.addEventListener("change", () => {
        // `setTarget` returns what it actually adopted, so a refused value
        // (blank, zero, negative) corrects itself in the box rather than
        // leaving the reader looking at a number the table did not use.
        input.value = String(setTarget(input.value));
    });
    onTargetChange(renderProductivity);
}

/**
 * Attainment against the target, as a bar and a percentage.
 *
 * @param {number} rate Cases per day.
 * @returns {string} HTML.
 */
function attainCell(rate) {
    const pct = Math.round((rate / getTarget()) * 100);
    const tone = pct >= 100 ? "success" : pct >= 80 ? "warn" : "danger";
    return `<td class="progress-col"><span class="progress-cell">
        <span class="progress progress--sm" role="img" aria-label="${pct}% of target">
            <span class="progress-seg" style="width:${Math.min(100, pct)}%;
                  background:var(--tone-${tone})"></span>
        </span>
        <span class="num" data-tone="${tone}">${pct}%</span>
    </span></td>`;
}

const SELECTOR = "#productivityHead th.sortable";

/**
 * Build the header from the taxonomy and make it sortable.
 *
 * This replaces `#productivityHead`'s contents, discarding the previous header
 * cells and their listeners, so `makeSortable` rebinds here rather than
 * stacking duplicates — the same arrangement the daily header uses.
 */
export function renderProductivityHead() {
    const statusHeads = getExecutedStatuses().map((s) =>
        sortableTh(s.key, s.label, { cls: "num band", tone: toneFor(s.key) })).join("");

    $("#productivityHead").innerHTML =
        sortableTh("pic", "PIC")
        + statusHeads
        // Centred: these three are the member's own figures rather than part of
        // the status band, and centring is what sets them apart from it.
        + sortableTh("executed", "Executed", { cls: "num center" })
        + sortableTh("days", "Working days", { cls: "num center" })
        + sortableTh("productivity", "Cases / day", { cls: "num center" })
        + `<th class="progress-col">Attainment</th>`;

    makeSortable(SELECTOR, prodSort, renderProductivity);
    paintSortIndicators(SELECTOR, prodSort);
}

/**
 * Adopt a fresh dataset: reset the sort to fastest-first and redraw.
 *
 * Call {@link renderProductivityHead} first — the header must reflect the
 * current taxonomy before the body is drawn against it, and the sort indicator
 * is painted onto the header cells this function finds.
 *
 * @param {Object[]} data `/api/productivity` body.
 */
export function initProductivity(data) {
    prodData = data;
    prodSort.col = DEFAULT_SORT.col;
    prodSort.asc = DEFAULT_SORT.asc;
    paintSortIndicators(SELECTOR, prodSort);
    renderProductivity();
}

/** Sort the rows by the active column and redraw the table. */
function renderProductivity() {
    const statuses = getExecutedStatuses();
    const numeric = new Set([...NUMERIC_BASE, ...statuses.map((s) => s.key)]);
    const rows = sortRows(prodData, prodSort, numeric);

    if (!rows.length) {
        $("#productivityBody").innerHTML =
            `<tr class="empty-row"><td colspan="${statuses.length + 5}">`
            + "No executed cases yet.</td></tr>";
        $("#productivityFoot").innerHTML = "";
        return;
    }

    $("#productivityBody").innerHTML = rows.map((r) => `<tr>
        <td>${esc(r.pic)}</td>
        ${statuses.map((s) => {
            const v = r[s.key] || 0;
            return `<td class="num band${v ? "" : " zero"}" `
                 + `data-tone="${esc(toneFor(s.key))}">${v || ""}</td>`;
        }).join("")}
        <td class="num center">${r.executed}</td>
        <td class="num center">${r.days}</td>
        <td class="num center"><b>${r.productivity.toFixed(2)}</b></td>
        ${attainCell(r.productivity)}
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
        ${statuses.map((s) => `<td class="num band">${sum(s.key) || 0}</td>`).join("")}
        <td class="num center">${executed}</td>
        <td class="num center">${days}</td>
        <td class="num center">${rate.toFixed(2)}</td>
        ${attainCell(rate)}
    </tr>`;
}
