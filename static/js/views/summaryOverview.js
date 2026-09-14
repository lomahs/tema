/**
 * The Summary overview: the state of things, above the tables.
 *
 * Laid out as the design canvas draws it — a row of KPI cards, then a grid of
 * panels: the result breakdown, and what happened today.
 *
 * `missing_reason` survives as the "Missing reason" KPI figure only. The list
 * of those rows was drawn here and has been removed; the count is the part that
 * belongs on a screen answering "where do we stand", and the rows themselves
 * are found in the workbook.
 *
 * Summary answers "how does each file and device stand". It did not answer the
 * question asked first and most often — *are we on track, and what is blocking
 * us* — because that answer only exists once every row is added up, and the
 * per-table footers each stop at their own scope.
 *
 * Everything here is derived, not fetched. The figures come from `sumRows` over
 * the same `/api/summary` rows the tables draw, so the strip cannot disagree
 * with the numbers underneath it; the activity line comes from `/api/daily`,
 * which `main.js` already has in hand. No endpoint was added for this view.
 *
 * Which statuses count as executed, as review, or as outside the plan is read
 * from the taxonomy, never named here — the same rule the rest of the UI
 * follows, so a new status in `parser/result_status.json` lands in the bar, the
 * legend and the figures without a change to this file.
 */
import { $, esc } from "../dom.js";
import {
    colourFor, getExecutedStatuses, getReviewStatuses, getStatuses,
    isExcluded, sumRows, toneFor,
} from "../taxonomy.js";

/**
 * Where a KPI card's "View →" goes. Set by `main.js`, which owns the views.
 *
 * A callback rather than an import: Summary reaching into `views/detail.js`
 * directly is the coupling that was deliberately removed from this screen, and
 * a card that navigates is not a reason to put it back.
 *
 * The second argument names a filter the destination should apply — `main.js`
 * translates it, because only it knows which module owns that view's state.
 *
 * @type {(view: string, filter?: string) => void}
 */
let onJump = () => {};

/**
 * Tell the overview where its cards lead. Call once, at startup.
 * @param {(view: string, filter?: string) => void} fn
 */
export function setJumpHandler(fn) {
    onJump = fn;
}

/** Thousands separators: these run to five figures on a real folder. */
const fmt = (n) => Number(n || 0).toLocaleString();

/** "2026-09-08" -> "09-08". The year is the same on every row that matters. */
const shortDate = (d) => String(d || "").slice(5);

/**
 * The statuses a progress bar may draw, in taxonomy order.
 *
 * Excluded statuses are left out for the reason the dashed `band--aside` rule
 * exists in the table: `total` does not include them, so a bar that drew them
 * would not add up to its own denominator.
 *
 * @returns {import("../taxonomy.js").Status[]}
 */
function countedStatuses() {
    return getStatuses().filter((s) => !isExcluded(s.key));
}

/**
 * Sum a set of statuses out of a totals object.
 * @param {Object} totals Output of `sumRows`.
 * @param {import("../taxonomy.js").Status[]} statuses
 * @returns {number}
 */
function sumOf(totals, statuses) {
    return statuses.reduce((acc, s) => acc + (totals[s.key] || 0), 0);
}

/**
 * A stacked bar of every counted status, in taxonomy order.
 *
 * Painted with `colourFor`, which is the same stepped-tone function the charts
 * use — so a status is the same colour in the bar, in its badge, in its band
 * column and in the doughnut, by construction rather than by coincidence.
 *
 * @param {Object} totals Output of `sumRows`.
 * @param {string} [cls] Extra class, for the smaller per-scope bars.
 * @returns {string} HTML.
 */
export function progressBar(totals, cls = "") {
    const total = totals.total || 0;
    if (!total) return "";

    const segs = countedStatuses()
        .filter((s) => totals[s.key] > 0)
        .map((s) => {
            const pct = (totals[s.key] / total) * 100;
            return `<span class="progress-seg" style="width:${pct.toFixed(3)}%;`
                + `background:${colourFor(s.key)}"`
                + ` title="${esc(s.label)}: ${fmt(totals[s.key])}"></span>`;
        }).join("");

    // One image with one label, rather than a dozen focusable slivers: a screen
    // reader wants the breakdown as a sentence, not as twelve unlabelled spans.
    const desc = countedStatuses()
        .filter((s) => totals[s.key] > 0)
        .map((s) => `${s.label} ${totals[s.key]}`).join(", ");

    return `<div class="progress ${cls}" role="img"
                 aria-label="${esc(desc)}">${segs}</div>`;
}

/**
 * Executed-versus-plan for one set of rows, as a percentage.
 *
 * Exported because the Summary table's Executed column draws the same figure
 * per row: one definition of "executed", used by the KPI card, the scope
 * heading and every row beneath it.
 *
 * @param {Object} totals Output of `sumRows`, or any row carrying status counts.
 * @returns {number} 0-100, rounded.
 */
export function executedPct(totals) {
    const total = totals.total || 0;
    return total ? Math.round((sumOf(totals, getExecutedStatuses()) / total) * 100) : 0;
}

/**
 * A scope block's own bar and percentage, for the heading strip above its table.
 * @param {Object[]} rows That scope group's summary rows.
 * @returns {string} HTML.
 */
export function scopeProgress(rows) {
    const totals = sumRows(rows);
    if (!totals.total) return "";
    return `<span class="scope-pct">${executedPct(totals)}% executed</span>`
        + progressBar(totals, "progress--sm");
}

/**
 * What happened on the most recent day anyone tested, and how that compares
 * with the day before.
 *
 * Deliberately *per-day activity* rather than a cumulative progress delta.
 * `daily_rows` drops cases with no date, so a running total taken from it would
 * not reconcile with Summary's total, and a percentage that silently disagreed
 * with the figure beside it is worse than no percentage at all. A count of what
 * was executed on a given day is exact.
 *
 * @param {Object[]} dailyRows `/api/daily` rows.
 * @returns {{date: string, executed: number, delta: number|null,
 *            prevDate: string|null}|null} `prevDate` is the day the delta is
 *   measured against — the label has to name *that* day, not the latest one.
 */
function lastDayActivity(dailyRows) {
    if (!dailyRows || !dailyRows.length) return null;
    const executedStatuses = getExecutedStatuses();

    const byDate = new Map();
    dailyRows.forEach((r) => {
        const n = executedStatuses.reduce((acc, s) => acc + (r[s.key] || 0), 0);
        byDate.set(r.date, (byDate.get(r.date) || 0) + n);
    });

    const dates = [...byDate.keys()].sort();
    if (!dates.length) return null;

    const date = dates[dates.length - 1];
    const executed = byDate.get(date) || 0;
    const prevDate = dates.length > 1 ? dates[dates.length - 2] : null;
    const prev = prevDate === null ? null : byDate.get(prevDate) || 0;
    return { date, executed, prevDate, delta: prev === null ? null : executed - prev };
}

/**
 * One KPI card.
 *
 * A card with an action is a `<button>`, not a `<div>` with a handler: it is
 * operated by keyboard and announced as a control for free, which a clickable
 * div is not. The action itself is a callback handed in from `main.js` — this
 * module must not import a view to reach one.
 *
 * @param {{label: string, value: string, tone?: string, sub?: string,
 *          action?: string, jump?: string}} f
 * @returns {string} HTML.
 */
function kpi(f) {
    const tone = f.tone ? ` data-tone="${esc(f.tone)}"` : "";
    const inner = `
        <span class="kpi-head">
            <span class="eyebrow">${esc(f.label)}</span>
            ${f.action ? `<span class="kpi-action">${esc(f.action)}</span>` : ""}
        </span>
        <span class="kpi-value"${tone}>${esc(f.value)}</span>
        <span class="kpi-sub">${esc(f.sub || "")}</span>`;

    return f.jump
        ? `<button type="button" class="kpi kpi--link" data-jump="${esc(f.jump)}"`
          + `${f.filter ? ` data-filter="${esc(f.filter)}"` : ""}>${inner}</button>`
        : `<div class="kpi">${inner}</div>`;
}

/**
 * Today's work, per file — the design's "Today's progress" panel.
 *
 * Derived from the `/api/daily` rows this module already receives, so it needs
 * no endpoint of its own and cannot disagree with the Daily view.
 *
 * @param {Object[]} dailyRows `/api/daily` rows.
 * @param {?{date: string}} activity The last day anyone tested.
 * @returns {string} HTML.
 */
function todayPanel(dailyRows, activity) {
    const today = new Date();
    const iso = `${today.getFullYear()}-`
        + `${String(today.getMonth() + 1).padStart(2, "0")}-`
        + `${String(today.getDate()).padStart(2, "0")}`;

    const mine = (dailyRows || []).filter((r) => r.date === iso);
    const head = mine.length
        ? `${fmt(sumRows(mine).total)} cases · `
          + `${new Set(mine.map((r) => r.file)).size} files`
        : iso;

    let body;
    if (!mine.length) {
        body = `<p class="panel-empty">${activity
            ? `No cases executed today. Last activity ${esc(activity.date)}.`
            : "No execution recorded yet."}</p>`;
    } else {
        const files = [...new Set(mine.map((r) => r.file))]
            .map((file) => {
                const sub = mine.filter((r) => r.file === file);
                const totals = sumRows(sub);
                const names = [...new Set(sub.map((r) => r.pic).filter(Boolean))];
                const pics = names.slice(0, 3).join(" / ")
                    + (names.length > 3 ? ` +${names.length - 3}` : "");
                const chips = countedStatuses()
                    .filter((st) => totals[st.key] > 0)
                    .map((st) => `<span class="badge" data-tone="${esc(toneFor(st.key))}">`
                        + `${esc(st.label)} ${fmt(totals[st.key])}</span>`).join("");
                return { file, total: totals.total, pics, chips };
            })
            .sort((a, b) => b.total - a.total);

        body = `<ul class="today-list">${files.map((f) => `
            <li class="today-row">
                <div class="today-line">
                    <span class="today-file">${esc(f.file)}</span>
                    <span class="num">${fmt(f.total)}</span>
                </div>
                <div class="today-line">
                    <span class="muted">${esc(f.pics)}</span>
                    <span class="chips chips--tight">${f.chips}</span>
                </div>
            </li>`).join("")}</ul>`;
    }

    return `<section class="card">
        <div class="card-head card-head--row">
            <h2>Today's progress</h2>
            <span class="count">${esc(head)}</span>
        </div>
        ${body}
    </section>`;
}

/**
 * Draw the overview.
 *
 * @param {{groups: Object[], missing_reason: Object[]}} data `/api/summary`.
 * @param {Object[]} dailyRows `/api/daily`, for the activity line.
 */
export function renderOverview(data, dailyRows) {
    const host = $("#summaryOverview");
    const groups = data.groups || [];

    if (!groups.length) {
        host.innerHTML = "";
        host.hidden = true;
        return;
    }
    host.hidden = false;

    const totals = sumRows(groups);
    const executed = sumOf(totals, getExecutedStatuses());
    const review = sumOf(totals, getReviewStatuses());
    const owing = (data.missing_reason || []).length;
    const activity = lastDayActivity(dailyRows);

    // "Executed", never "Done": an NG is work carried out and is not a pass.
    // A bar labelled "70% done" beside a red NG column would be a lie the
    // reader has no way to catch.
    // Passed, not "OK": which statuses count as a pass is the taxonomy's
    // business, and `tone: success` is the only thing in it that says so.
    const passed = sumOf(totals, getStatuses().filter((s) => toneFor(s.key) === "success"));
    const files = new Set(groups.map((g) => g.file)).size;

    // "Executed", never "Done": an NG is work carried out and is not a pass.
    // A bar labelled "70% done" beside a red NG column would be a lie the
    // reader has no way to catch.
    const cards = [
        {
            label: "In plan",
            value: fmt(totals.total),
            sub: `${fmt(files)} file${files === 1 ? "" : "s"}`,
        },
        {
            label: `Executed · ${executedPct(totals)}%`,
            value: fmt(executed),
            // Named for the day being compared *against*, not the latest one:
            // "−89 vs 09-08" on the 8th says nothing.
            sub: activity && activity.delta !== null
                ? `${activity.delta >= 0 ? "+" : "−"}${fmt(Math.abs(activity.delta))}`
                  + ` vs ${shortDate(activity.prevDate)}`
                : `of ${fmt(totals.total)}`,
        },
        {
            label: "Pass rate",
            value: `${executed ? Math.round((passed / executed) * 100) : 0}%`,
            tone: "success",
            sub: `${fmt(passed)} of ${fmt(executed)} executed`,
        },
        {
            label: "To review",
            value: fmt(review),
            tone: "warn",
            sub: "open work",
            action: "View →",
            jump: "detail",
        },
        {
            label: "Missing reason",
            value: fmt(owing),
            tone: owing ? "danger" : "muted",
            sub: owing ? "no ticket, no note" : "all accounted for",
            action: owing ? "View →" : "",
            jump: owing ? "detail" : "",
            // Review opens narrowed to exactly these cases. The figure there can
            // be smaller and legitimately so: `needs_reason` may name a status
            // that is not a `review` one, and such a case is not in that view.
            filter: "missing",
        },
    ];

    // Label, share and count on one grid so the three columns line up down the
    // panel — the design's breakdown list, which a flowed inline legend is not.
    const legend = countedStatuses()
        .filter((s) => totals[s.key] > 0)
        .map((s) => `<li class="legend-item">
            <span class="swatch" style="background:${colourFor(s.key)}"></span>
            <span class="legend-label">${esc(s.label)}</span>
            <span class="legend-pct num">${
                totals.total ? ((totals[s.key] / totals.total) * 100).toFixed(1) : "0.0"}%</span>
            <span class="legend-count num">${fmt(totals[s.key])}</span>
        </li>`).join("");

    host.innerHTML = `
        <div class="kpis">${cards.map(kpi).join("")}</div>
        <div class="panels">
            <section class="card">
                <div class="card-head card-head--row">
                    <h2>Result breakdown</h2>
                    <span class="count">${fmt(totals.total)} in plan</span>
                </div>
                ${progressBar(totals)}
                <ul class="progress-legend">${legend}</ul>
            </section>
            ${todayPanel(dailyRows, activity)}
        </div>`;

    host.querySelectorAll(".kpi--link").forEach((b) =>
        b.addEventListener("click", () => onJump(b.dataset.jump, b.dataset.filter)));
}
