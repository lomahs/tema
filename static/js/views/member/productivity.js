/**
 * Member tab, first card: productivity per member.
 *
 * Throughput is executed cases over the days a member actually tested, through
 * yesterday. Beside the executed band sit the statuses a plan counts as done
 * but nobody ran — Cancel, as shipped — drawn aside, because Executed plus
 * those is exactly the Actual the matrix below measures against the plan.
 *
 * Every figure is the server's (`/api/member/productivity`), the Team row and
 * the NG rate included; this module owns the sort and draws.
 */
import { $, esc } from "../../dom.js";
import { makeSortable, paintSortIndicators, sortableTh, sortRows } from "../../sorting.js";
import {
    getExecutedStatuses, getFailedStatuses, getWorkedAsideStatuses, toneFor,
} from "../../taxonomy.js";

/** @type {Object|null} the last `/api/member/productivity` body */
let data = null;

/** Members are worth reading fastest-first, so the default sort is descending. */
const DEFAULT_SORT = { col: "productivity", asc: false };

/** @type {import("../../sorting.js").SortState} */
const sort = { ...DEFAULT_SORT };

const SELECTOR = "#memberProdHead th.sortable";

/** The NG rate column's heading, named after the statuses it counts. */
function failLabel() {
    const failed = getFailedStatuses();
    return failed.length === 1 ? `${failed[0].label} rate` : "Fail rate";
}

/**
 * Build the header from the taxonomy and make it sortable.
 *
 * Replaces `#memberProdHead`'s cells, taking their listeners with them, so
 * `makeSortable` rebinds here rather than stacking duplicates.
 */
export function renderProductivityHead() {
    const executed = getExecutedStatuses().map((s, i) => sortableTh(s.key, s.label,
        { cls: `num band${i ? "" : " band--first"}`, tone: toneFor(s.key) })).join("");
    const aside = getWorkedAsideStatuses().map((s) => sortableTh(s.key, s.label,
        { cls: "num band band--aside", tone: toneFor(s.key) })).join("");

    $("#memberProdHead").innerHTML =
        sortableTh("pic", "PIC")
        + executed + aside
        + sortableTh("executed", "Executed", { cls: "num center" })
        + sortableTh("days", "Working days", { cls: "num center" })
        + sortableTh("productivity", "Cases / day", { cls: "num center" })
        // Only when the taxonomy has a status both executed and an issue —
        // with none, the column would read the same dash for everyone.
        + (getFailedStatuses().length
            ? sortableTh("ng_rate", failLabel(), { cls: "num center" }) : "")
        + sortableTh("attainment", "Attainment", { cls: "progress-col" });

    makeSortable(SELECTOR, sort, render);
    paintSortIndicators(SELECTOR, sort);
}

/**
 * Adopt a fresh body. The sort survives: a plan save or a reload is not a
 * reason to lose the order somebody chose.
 *
 * @param {Object} body `/api/member/productivity` response.
 */
export function setProductivity(body) {
    data = body;
    render();
}

/**
 * Attainment against what this member was planned for, through yesterday.
 *
 * A member nobody planned has no attainment rather than 0% — they are not
 * behind, they were never given a figure to meet.
 *
 * @param {?number} ratio `attainment` as served: actual over plan, or null.
 * @returns {string} HTML.
 */
function attainCell(ratio) {
    if (ratio === null || ratio === undefined) {
        return `<td class="progress-col"><span class="zero"`
             + ` title="No planned day before today names this member">—</span></td>`;
    }
    const pct = Math.round(ratio * 100);
    const tone = pct >= 100 ? "success" : pct >= 80 ? "warn" : "danger";
    return `<td class="progress-col"><span class="progress-cell">
        <span class="progress progress--sm" role="img" aria-label="${pct}% of plan">
            <span class="progress-seg" style="width:${Math.min(100, pct)}%;
                  background:var(--tone-${tone})"></span>
        </span>
        <span class="num" data-tone="${tone}">${pct}%</span>
    </span></td>`;
}

/**
 * One NG-rate cell, or nothing when the taxonomy has no failing status.
 * @param {?number} rate 0–1, or null with nothing executed.
 * @returns {string} HTML.
 */
function rateCell(rate) {
    if (!getFailedStatuses().length) return "";
    if (rate === null || rate === undefined) return `<td class="num center zero">—</td>`;
    return `<td class="num center" data-tone="danger">${(rate * 100).toFixed(1)}%</td>`;
}

/**
 * The status band of one row: executed statuses, then the aside ones.
 * @param {Object} r
 * @param {boolean} blank Blank zeros (member rows) rather than print them (Team).
 */
function bandCells(r, blank) {
    const cell = (s, cls) => {
        const v = r[s.key] || 0;
        return `<td class="num ${cls}${v || !blank ? "" : " zero"}" `
             + `data-tone="${esc(toneFor(s.key))}">${v || (blank ? "" : "0")}</td>`;
    };
    return getExecutedStatuses().map((s, i) => cell(s, `band${i ? "" : " band--first"}`)).join("")
         + getWorkedAsideStatuses().map((s) => cell(s, "band band--aside")).join("");
}

function render() {
    if (!data) return;
    const aside = getWorkedAsideStatuses();
    $("#memberProdNote").innerHTML = `Through <b>${esc(data.through)}</b> — today is half a day.`
        + (aside.length
            ? ` Executed plus ${esc(aside.map((s) => s.label).join(" and "))} is each`
              + " member's Actual against the plan below."
            : "");

    const numeric = new Set(["executed", "days", "productivity", "ng_rate", "attainment",
        ...getExecutedStatuses().map((s) => s.key), ...aside.map((s) => s.key)]);
    const rows = sortRows(data.rows, sort, numeric);
    const span = 5 + getExecutedStatuses().length + aside.length
        + (getFailedStatuses().length ? 1 : 0);

    if (!rows.length) {
        $("#memberProdBody").innerHTML =
            `<tr class="empty-row"><td colspan="${span}">No cases dated before today yet.</td></tr>`;
        $("#memberProdFoot").innerHTML = "";
        return;
    }

    $("#memberProdBody").innerHTML = rows.map((r) => `<tr>
        <td>${esc(r.pic)}</td>
        ${bandCells(r, true)}
        <td class="num center">${r.executed}</td>
        <td class="num center">${r.days}</td>
        <td class="num center"><b>${r.productivity.toFixed(2)}</b></td>
        ${rateCell(r.ng_rate)}
        ${attainCell(r.attainment)}
    </tr>`).join("");

    // `days` on the Team row is person-days, which is the denominator a team
    // rate wants — the server sums it that way.
    const t = data.team;
    $("#memberProdFoot").innerHTML = `<tr>
        <td>Team</td>
        ${bandCells(t, false)}
        <td class="num center">${t.executed}</td>
        <td class="num center">${t.days}</td>
        <td class="num center">${t.productivity.toFixed(2)}</td>
        ${rateCell(t.ng_rate)}
        ${attainCell(t.attainment)}
    </tr>`;
}
