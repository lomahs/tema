/**
 * Member tab, second card: plan against actual, member by day.
 *
 * One week on screen at a time (Monday to Friday), and on the right the whole
 * phase through yesterday — Plan, Actual, Δ, On plan and Unplanned — which does
 * not move as the reader pages. Actual is worked: executed plus what left the
 * pile unrun (Cancel), the measure every plan figure in the app uses.
 *
 * Every figure is the server's: `/api/member/totals` for the columns on the
 * right, `/api/member/week/<monday>` for the cells. What happens here is
 * arranging them and turning a cell's state and sign into a tone — the same
 * split `views/planning/cells.js` keeps. Paging is reported back through
 * `onPage`, because fetching a week is `index.js`'s business.
 */
import { $, esc } from "../../dom.js";
import { makeSortable, paintSortIndicators, sortableTh, sortRows } from "../../sorting.js";

/** @type {(index: number) => void} */
let onPage = () => {};

/** What was last drawn, so a sort can redraw without refetching. */
let last = null;

/** Name order by default, which is the order the server sends. */
const sort = { col: null, asc: true };

const SELECTOR = "#memberMatrix th.sortable";
const NUMERIC = new Set(["planned", "actual", "delta", "adherence", "unplanned"]);

/**
 * Wire the pager. Call once, at startup.
 * @param {{onPage: (index: number) => void}} opts
 */
export function initMatrix(opts) {
    onPage = opts.onPage;
    $("#memberMatrixHead").addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-act]");
        if (!btn || !last) return;
        const act = btn.dataset.act;
        if (act === "prev") onPage(last.index - 1);
        else if (act === "next") onPage(last.index + 1);
        else if (act === "current") onPage(last.current);
    });
}

/**
 * A signed figure, with a real minus sign.
 * @param {number} n
 */
function signed(n) {
    return n > 0 ? `+${n.toLocaleString()}` : n < 0 ? `−${Math.abs(n).toLocaleString()}` : "0";
}

/** @param {?number} n A delta, or null. */
function deltaTone(n) {
    return n === null || n === undefined ? "muted" : n > 0 ? "success" : n < 0 ? "danger" : "neutral";
}

/** The thresholds Attainment has always used: on plan, close, behind. */
function ratioTone(r) {
    return r === null || r === undefined ? "muted" : r >= 1 ? "success" : r >= 0.8 ? "warn" : "danger";
}

const WEEKDAY = new Intl.DateTimeFormat("en-GB", { weekday: "short", timeZone: "UTC" });
const DAY_MONTH = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const DAY_MONTH_YEAR = new Intl.DateTimeFormat("en-GB",
    { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const asDate = (iso) => new Date(`${iso}T00:00:00Z`);

/** "22 – 26 Sept 2026" */
function weekLabel(week) {
    return `${DAY_MONTH.format(asDate(week.start))} – ${DAY_MONTH_YEAR.format(asDate(week.end))}`;
}

/**
 * One (member, day) cell.
 *
 * `kind` names the state the way the Planning grid's cells do, so the two
 * screens colour a day alike: `on` / `over` / `under` for a past planned day,
 * `unplanned` for work nobody scheduled, `wip` for today, `future` for a plan
 * still ahead.
 *
 * @param {?Object} c A cell from `/api/member/week`, or undefined.
 * @param {string} who The member, for the tooltip.
 * @param {string} date
 * @returns {string} HTML.
 */
function dayCell(c, who, date) {
    if (!c) return `<td class="member-cell"></td>`;

    let kind, fig, sub;
    if (c.state === "future") {
        kind = "future";
        fig = `–/${c.planned ?? "–"}`;
        sub = "planned";
    } else if (c.state === "today") {
        kind = "wip";
        fig = c.planned === null ? `${c.actual}` : `${c.actual}/${c.planned}`;
        sub = "in progress";
    } else if (c.planned === null) {
        kind = "unplanned";
        fig = `${c.actual}`;
        sub = "unplanned";
    } else {
        kind = c.delta > 0 ? "over" : c.delta < 0 ? "under" : "on";
        fig = `${c.actual}/${c.planned}`;
        sub = signed(c.delta);
    }

    const lines = [`${who} · ${date}`];
    if (c.actual !== null) {
        lines.push(`${c.actual} done` + (c.cancel ? ` (${c.executed} executed + ${c.cancel} cancel)` : ""));
    }
    if (c.planned !== null) lines.push(`${c.planned} planned`);
    c.short.forEach((s) => lines.push(`Short on ${s.file} · ${s.device}: ${s.actual}/${s.planned}`));

    const flag = c.short.length
        ? `<span class="member-short" aria-label="${c.short.length} planned slot${
            c.short.length === 1 ? "" : "s"} short">!</span>` : "";
    return `<td class="member-cell"><span class="member-fig" data-kind="${kind}" title="${esc(lines.join("\n"))}">
        <span class="num">${fig}</span><span class="member-sub num">${esc(sub)}</span>${flag}</span></td>`;
}

/**
 * The five totals cells of one member (or the team).
 * @param {Object} t A `totals` member or team entry.
 * @returns {string} HTML.
 */
function totalCells(t) {
    // Centred, as the member's own figures are in the productivity table above:
    // they sit apart from the day cells rather than continuing them.
    const dash = `<td class="num center zero">—</td>`;
    const actualTitle = t.cancel ? ` title="${t.executed} executed + ${t.cancel} cancel"` : "";
    return `<td class="num center member-total--first">${t.planned ? t.planned.toLocaleString() : "—"}</td>`
        + `<td class="num center"${actualTitle}>${t.actual.toLocaleString()}</td>`
        + (t.delta === null ? dash
            : `<td class="num center" data-tone="${deltaTone(t.delta)}"><b>${signed(t.delta)}</b></td>`)
        + (t.adherence === null ? dash
            : `<td class="num center" data-tone="${ratioTone(t.adherence)}">${Math.round(t.adherence * 100)}%</td>`)
        + `<td class="num center${t.unplanned ? "" : " zero"}">${t.unplanned ? t.unplanned.toLocaleString() : ""}</td>`;
}

/**
 * Draw the card.
 *
 * @param {Object} view
 * @param {Object} view.totals `/api/member/totals` body.
 * @param {Object[]} view.weeks `/api/member/weeks` → `weeks`.
 * @param {number} view.index The week on screen.
 * @param {number} view.current The week holding today.
 * @param {Object} view.week `/api/member/week/<monday>` body.
 */
export function renderMatrix(view) {
    last = view;
    const { totals, weeks, index, current, week } = view;
    const wk = weeks[index];

    $("#memberMatrixHead").innerHTML = `
        <div class="card-head">
            <h2>Plan vs actual by day</h2>
            <p>Actual is executed plus Cancel. Totals are the whole phase through
               <b class="num">${esc(totals.through)}</b>; today is in progress and not counted.</p>
        </div>
        <div class="member-pager">
            <button type="button" class="btn btn-sm" data-act="prev" ${index > 0 ? "" : "disabled"}
                    aria-label="Previous week">&lsaquo;</button>
            <span class="member-week">${wk ? esc(weekLabel(wk)) : "No weeks"}</span>
            <button type="button" class="btn btn-sm" data-act="next"
                    ${index < weeks.length - 1 ? "" : "disabled"} aria-label="Next week">&rsaquo;</button>
            <button type="button" class="btn btn-sm" data-act="current"
                    ${index === current ? "disabled" : ""}>This week</button>
        </div>`;

    if (!totals.members.length || !wk) {
        $("#memberMatrix").innerHTML =
            `<p class="empty-note member-empty">Nobody is planned and nothing has been run yet.</p>`;
        return;
    }

    const days = wk.days;
    const head = `<tr>
        <th class="member-name">Member</th>
        ${days.map((d) => `<th class="member-day${d.date === totals.today ? " is-today" : ""}${
            d.in_phase ? "" : " is-out"}"${d.in_phase ? "" : ` title="Outside the phase"`}>
            <span>${esc(WEEKDAY.format(asDate(d.date)))}</span>
            <span class="num">${esc(DAY_MONTH.format(asDate(d.date)))}</span></th>`).join("")}
        ${sortableTh("planned", "Plan", { cls: "num center member-total--first" })}
        ${sortableTh("actual", "Actual", { cls: "num center" })}
        ${sortableTh("delta", "Δ", { cls: "num center" })}
        ${sortableTh("adherence", "On plan", { cls: "num center" })}
        ${sortableTh("unplanned", "Unplanned", { cls: "num center" })}
    </tr>`;

    // Nobody's row is the one that was never planned; sorting puts it last
    // regardless, beside the Team row it helps add up.
    const named = sortRows(totals.members.filter((m) => !m.aside), sort, NUMERIC);
    const rows = [...named, ...totals.members.filter((m) => m.aside)];
    const body = rows.map((m) => {
        const cells = week.cells[m.pic] || {};
        return `<tr class="${m.aside ? "row--aside" : ""}"${m.aside
            ? ` title="Cases with no PIC — nobody can be planned for them"` : ""}>
            <td class="member-name">${esc(m.pic)}</td>
            ${days.map((d) => dayCell(cells[d.date], m.pic, d.date)).join("")}
            ${totalCells(m)}
        </tr>`;
    }).join("");

    const teamDay = (d) => {
        const t = week.team[d.date];
        if (!t) return `<td class="member-cell"></td>`;
        const fig = t.planned === null ? `${t.actual}` : `${t.actual}/${t.planned}`;
        return `<td class="member-cell num"${t.delta === null ? "" : ` data-tone="${deltaTone(t.delta)}"`}
            title="${esc(t.delta === null ? "" : `Team: ${signed(t.delta)}`)}">${fig}</td>`;
    };
    const foot = `<tr><td class="member-name">Team</td>
        ${days.map(teamDay).join("")}
        ${totalCells(totals.team)}</tr>`;

    $("#memberMatrix").innerHTML = `<table class="ledger member-matrix">
        <thead>${head}</thead><tbody>${body}</tbody><tfoot>${foot}</tfoot></table>`;
    makeSortable(SELECTOR, sort, () => renderMatrix(last));
    paintSortIndicators(SELECTOR, sort);
}
