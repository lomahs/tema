/**
 * Daily view: progress grouped by date and then by file, with each level
 * rolling up the (device, PIC) rows beneath it.
 *
 * The second level exists because a file otherwise repeats on every row of a
 * date — a day with four files across two devices and three testers listed the
 * same workbook name a dozen times.
 *
 * Paging here counts **date groups**, not rows — a page that cut a date in half
 * would make the roll-up above it a lie. `pagination.js` needs no change for
 * that; it is handed the group count.
 *
 * Owns the daily dataset, its sort state and its expansion state.
 */
import { $, esc } from "../dom.js";
import { populateSelect, uniqueOf } from "../filters.js";
import { groupPath, renderGroupedTable, setAllGroups, toggleGroup } from "../groupedTable.js";
import { renderPagination } from "../pagination.js";
import { makeSortable, paintSortIndicators, sortableTh, sortGrouped } from "../sorting.js";
import {
    executedIn, getStatuses, statusCells, statusHeadCells, sumRows,
} from "../taxonomy.js";
import { hasPlan, onPlanChange } from "../plan.js";
import { getDailyPlan } from "../api.js";

/** Dates per page. A date is a group, however many rows it holds. */
const PAGE_SIZE = 10;

const GROUP_BY = ["date", "file"];

/** Most dates are history; the one being worked on is the one worth opening. */
const DEFAULT_EXPANDED = false;

/** @type {Object[]} rows from /api/daily */
let dailyData = [];
/**
 * Running total of executed cases by date, over the filtered rows.
 *
 * Cumulative is the one figure on this table that cannot be computed from the
 * rows of a single day, so it is worked out once per render and looked up.
 * @type {Map<string, number>}
 */
let cumulative = new Map();
/** The largest of (any day's executed, the plan) — the chart's ceiling. */
let chartMax = 1;
/** Executed cases per date over the filtered rows — the chart's bars. */
let executedByDate = new Map();
/**
 * `/api/plan/daily` for the current filters, by date: `{planned, worked,
 * attain}`. The server narrows the plan and the worked cases by the same
 * filters and divides, so nothing here measures anything against a plan.
 * @type {Map<string, {planned: ?number, worked: number, attain: ?number}>}
 */
let planByDate = new Map();
/** Bumped per request, so a slow answer for old filters cannot land last. */
let planRequest = 0;
/** @type {Object[]} `dailyData` after filters and sorting */
let dailyRows = [];
let currentPage = 1;

/** @type {Set<string>} which dates are open */
const expanded = new Set();

/** A daily log reads newest-first. */
const DEFAULT_SORT = { col: "date", asc: false };

/** @type {import("../sorting.js").SortState} */
const dailySort = { ...DEFAULT_SORT };

const FILTER_SELECTORS = [
    "#dailyFilterFile", "#dailyFilterDevice", "#dailyFilterPIC",
    "#dailyFilterDateFrom", "#dailyFilterDateTo",
];

/**
 * Called with a status figure's context when one is pressed.
 *
 * Daily counts the plan, not the scope groups, so the context it hands over
 * names a day and whatever the row narrows it to — never a scope. The
 * destination falls back to the groups in the plan, which is the same coverage.
 *
 * @type {(ctx: Object) => void}
 */
let onDrillIn = () => {};

/**
 * Attach the filter, clear and expand-all listeners. Call once, at startup.
 *
 * These controls live in the static template, so unlike the sortable headers
 * they are never replaced and must only be bound a single time.
 */
export function initDailyView({ onDrillIn: drill = () => {} } = {}) {
    onDrillIn = drill;
    FILTER_SELECTORS.forEach((sel) => $(sel).addEventListener("change", renderDaily));

    // A status figure is a way into the cases counted on that day. The click is
    // stopped here because the whole group row is a toggle: without this, asking
    // for a day's NGs would also collapse the day.
    const drillFrom = (e) => {
        const figure = e.target.closest("button[data-status]");
        if (!figure) return;
        e.stopPropagation();
        onDrillIn({ ...figure.dataset });
    };
    $("#dailyBody").addEventListener("click", drillFrom);
    $("#dailyFoot").addEventListener("click", drillFrom);

    $("#btnClearDailyFilters").addEventListener("click", () => {
        FILTER_SELECTORS.forEach((sel) => { $(sel).value = ""; });
        renderDaily();
    });

    // The plan line and the Plan/Attain columns are read off the plan for that
    // date, so a day saved in Planning has to reach this view. It hears about
    // it through `plan.js` rather than from Planning, which it never imports.
    onPlanChange(renderDaily);

    document.querySelectorAll('[data-expand="daily"]').forEach((btn) =>
        btn.addEventListener("click", () => {
            setAllGroups(expanded, dailyRows, GROUP_BY, (r, k) => r[k], btn.dataset.all === "1");
            renderDailyBody();
        }));
}

/**
 * Build the daily header from the taxonomy and make it sortable.
 *
 * This replaces `#dailyHead`'s contents, discarding the previous header cells
 * and their listeners, so `makeSortable` rebinds here rather than stacking
 * duplicates.
 */
export function renderDailyHead() {
    $("#dailyHead").innerHTML =
        sortableTh("date", "Date")
        + sortableTh("file", "File")
        + sortableTh("device", "Device")
        + sortableTh("pic", "PIC")
        + statusHeadCells(sortableTh)
        // The design's daily-log columns. They are answers about a *day*, so
        // they are filled on the date rows and left blank below them — a plan
        // for one device of one file is not a figure anyone set.
        + `<th class="num">Executed</th>`
        + `<th class="num">Plan</th>`
        + `<th class="num">Attain</th>`
        + `<th class="num">Members</th>`
        + `<th class="progress-col">Cumulative</th>`;
    makeSortable("#dailyHead th.sortable", dailySort, renderDaily);
    paintSortIndicators("#dailyHead th.sortable", dailySort);
}


/**
 * Roll-up for a group row.
 *
 * `sumRows` alone loses the two things the daily columns need: which date the
 * group is, and how many people worked in it. Members is a distinct count, not
 * a sum — the same tester on four files is one member, and summing would make
 * the plan four times too large.
 *
 * @param {Object[]} rows
 * @returns {Object}
 */
function dailyAggregate(rows) {
    // A field the whole group agrees on is a fact about the group; one it does
    // not is nothing, and must not be carried as though it were — the figures on
    // a roll-up row are a door into its cases, and a file name borrowed from the
    // first row would open the wrong ones.
    const shared = (key) => (rows.length && rows.every((r) => r[key] === rows[0][key])
        ? rows[0][key] : "");
    return {
        ...sumRows(rows),
        date: rows.length ? rows[0].date : "",
        file: shared("file"),
        device: shared("device"),
        pic: shared("pic"),
        members: new Set(rows.map((r) => r.pic).filter(Boolean)).size,
    };
}

/**
 * The cells after the status band.
 *
 * @param {Object} row A leaf row or a roll-up.
 * @param {number} depth 0 on a date row; deeper rows get the Executed figure
 *   only, because plan, attainment and cumulative are per-day quantities.
 * @returns {string} HTML.
 */
function dailyCells(row, depth) {
    const executed = executedIn(row);
    const blank = `<td class="num"></td>`.repeat(3) + `<td class="progress-col"></td>`;
    const executedCell = `<td class="num${executed ? "" : " zero"}">${executed || "0"}</td>`;

    if (depth !== 0) return executedCell + blank;

    // Both figures are the server's, for the filters on screen. `null` when no
    // plan matches that date and selection, which is not a plan of zero: the
    // day was not behind, it was never scheduled. Attain is worked over plan —
    // a plan of 100 that ended 90 OK and 10 Cancel is on plan.
    const day = planByDate.get(row.date);
    const plan = day ? day.planned : null;
    const attain = day && day.attain !== null ? Math.round(day.attain * 100) : null;
    // Three bands, as the design has them: on plan, close, behind. The tone is
    // the same vocabulary the statuses use, so nothing new is being said here.
    const tone = attain === null ? "muted" : attain >= 100 ? "success" : attain >= 80 ? "warn" : "danger";

    const cum = cumulative.get(row.date) || 0;
    const cumTotal = cumulative.size ? [...cumulative.values()][cumulative.size - 1] : 0;
    const pct = cumTotal ? (cum / cumTotal) * 100 : 0;

    return executedCell
        + `<td class="num${plan ? "" : " zero"}">${plan || "—"}</td>`
        + `<td class="num" data-tone="${tone}">${attain === null ? "—" : `${attain}%`}</td>`
        + `<td class="num${row.members ? "" : " zero"}">${row.members || "0"}</td>`
        + `<td class="progress-col"><span class="progress-cell">`
        + `<span class="progress progress--sm" role="img"`
        + ` aria-label="${Math.round(pct)}% of the period's executed cases">`
        + `<span class="progress-seg" style="width:${pct.toFixed(2)}%;`
        + `background:var(--tone-success)"></span></span>`
        + `<span class="num">${cum.toLocaleString()}</span></span></td>`;
}

/**
 * Adopt a fresh dataset: reset the sort to newest-first, open the most recent
 * date, refill the filters, redraw.
 *
 * Call {@link renderDailyHead} first — the header must reflect the current
 * taxonomy before the body is drawn against it.
 *
 * @param {Object[]} data `/api/daily` body.
 */
export function initDaily(data) {
    dailyData = data;
    dailySort.col = DEFAULT_SORT.col;
    dailySort.asc = DEFAULT_SORT.asc;
    paintSortIndicators("#dailyHead th.sortable", dailySort);

    // Everything closed except the latest date, whose files are opened too —
    // a log of thirty days should land you on the day you are working on with
    // its rows already visible, not behind two more clicks.
    expanded.clear();
    const latest = data.reduce((max, r) => (r.date > max ? r.date : max), "");
    if (latest) {
        expanded.add(groupPath(latest));
        new Set(data.filter((r) => r.date === latest).map((r) => r.file))
            .forEach((file) => expanded.add(groupPath(latest, file)));
    }

    populateSelect("#dailyFilterFile", uniqueOf(data, "file"));
    populateSelect("#dailyFilterDevice", uniqueOf(data, "device"));
    populateSelect("#dailyFilterPIC", uniqueOf(data, "pic"));
    renderDaily();
}

/**
 * What a daily row's status figure leads to.
 *
 * A leaf names a file, a device, a PIC and a day; a roll-up names the day and
 * whichever of the rest its rows agree on. "N/A" is dropped: it is what this
 * table prints for a case with no PIC recorded, and handing it on as a filter
 * would ask for a tester of that name.
 *
 * @param {Object} r A leaf row or a roll-up.
 * @returns {Object} Context for `onDrillIn`.
 */
function linkFor(r) {
    return {
        file: r.file, device: r.device, date: r.date,
        pic: r.pic === "N/A" ? "" : r.pic,
    };
}

/** Column count, for colspans. */
function totalCols() {
    // 4 label columns + Total + one per status + the five daily-log columns.
    return 10 + getStatuses().length;
}

/**
 * Recompute `dailyRows` from the current filters and sort, then redraw from the
 * first page.
 *
 * Any change of filter or sort reshuffles the rows, so the view goes back to
 * page 1 rather than leaving the reader on a page that now holds other data.
 *
 * Dates are compared as ISO strings, which orders correctly without parsing.
 */
function renderDaily() {
    const ff = $("#dailyFilterFile").value;
    const fd = $("#dailyFilterDevice").value;
    const fp = $("#dailyFilterPIC").value;
    const dfrom = $("#dailyFilterDateFrom").value;
    const dto = $("#dailyFilterDateTo").value;

    const rows = dailyData.filter((r) => {
        if (ff && r.file !== ff) return false;
        if (fd && r.device !== fd) return false;
        if (fp && r.pic !== fp) return false;
        if (dfrom && r.date < dfrom) return false;
        if (dto && r.date > dto) return false;
        return true;
    });

    const numeric = new Set(["total", ...getStatuses().map((s) => s.key)]);
    dailyRows = sortGrouped(rows, GROUP_BY, dailySort, numeric, sumRows);

    // Cumulative runs in date order regardless of how the table is sorted:
    // a running total that reversed with the sort would not be one.
    executedByDate = new Map();
    rows.forEach((r) => executedByDate.set(r.date, (executedByDate.get(r.date) || 0) + executedIn(r)));
    cumulative = new Map();
    let running = 0;
    [...executedByDate.keys()].sort().forEach((d) => {
        running += executedByDate.get(d);
        cumulative.set(d, running);
    });

    // The plan for these filters is a request away. Until it answers, no plan
    // figure is drawn rather than one for the previous filters.
    planByDate = new Map();
    renderChart();
    currentPage = 1;
    renderDailyBody();
    loadPlan({ file: ff, device: fd, pic: fp, from: dfrom, to: dto });
}

/**
 * Fetch the plan and attainment for the filters on screen, then redraw what
 * reads them: the chart and the Plan / Attain columns. The page is kept —
 * this is the same selection arriving complete, not a new one.
 *
 * @param {Object} filters Daily's filter values, as `getDailyPlan` takes them.
 */
async function loadPlan(filters) {
    const ticket = ++planRequest;
    const { ok, json } = await getDailyPlan(filters);
    if (!ok || ticket !== planRequest) return;
    planByDate = new Map(json.days.map((d) => [d.date, d]));
    renderChart();
    renderDailyBody();
}

/**
 * Executed per day against the plan — the design's chart, drawn in CSS.
 *
 * Not Chart.js: this is a bar per day with one horizontal marker, it has to
 * repaint on a theme change and on every filter change, and a canvas that
 * resolves its colours at construction is the thing `charts.js` exists to work
 * around. Divs take the tokens directly and cost nothing.
 *
 * It answers to the filters above it, unlike the design's, which always reports
 * the whole dataset — a chart contradicting the table beneath it is worse than
 * a chart with a narrower question.
 *
 * The bar is executed — throughput — while its tone says how the day went
 * against the plan, which is the server's attain for these filters: the same
 * pairing the Attain column makes.
 */
function renderChart() {
    const byDate = executedByDate;
    const dates = [...byDate.keys()].sort();
    chartMax = Math.max(1, ...byDate.values(),
        ...dates.map((d) => (planByDate.get(d) || {}).planned || 0)) * 1.12;

    if (!dates.length) {
        $("#dailyChart").innerHTML = `<p class="panel-empty">No dated cases match these filters.</p>`;
        $("#dailyChartNote").textContent = "";
        return;
    }

    $("#dailyChartNote").textContent = hasPlan()
        ? "The dashed line is what Planning says was meant to happen that day. "
          + "Days with no plan have no line."
        : "No day has been planned yet — set one up in Planning and the plan "
          + "line appears here.";

    $("#dailyChart").innerHTML = dates.map((d) => {
        const n = byDate.get(d) || 0;
        const day = planByDate.get(d);
        const plan = day ? day.planned : null;
        const done = day ? day.worked : n;
        const attain = day && day.attain !== null ? day.attain * 100 : null;
        // A day with no plan has nothing to be on or behind, so its bar keeps
        // the Executed colour the legend names; a planned day shows how it went.
        const tone = attain === null ? ""
            : attain >= 100 ? "success" : attain >= 80 ? "warn" : "danger";
        const toneAttr = tone ? ` data-tone="${tone}"` : "";
        return `<div class="bar-col" title="${esc(d)}: ${n} executed${
            done !== n ? `, ${done} done against the plan` : ""}${
            plan ? `, plan ${plan}` : ""}">
            <span class="bar-count num"${toneAttr}>${n || ""}</span>
            <span class="bar-track">
                <span class="bar-fill"${toneAttr}
                      style="height:${((n / chartMax) * 100).toFixed(2)}%"></span>
                ${plan ? `<span class="bar-plan"
                      style="bottom:${((plan / chartMax) * 100).toFixed(2)}%"></span>` : ""}
            </span>
            <span class="bar-label num">${esc(d.slice(5))}</span>
        </div>`;
    }).join("");
}

/** The distinct dates, in the order they appear after sorting. */
function pageDates() {
    const seen = [];
    dailyRows.forEach((r) => { if (!seen.includes(r.date)) seen.push(r.date); });
    return seen;
}

/**
 * Draw the current page of date groups.
 *
 * The footer totals **every** filtered row, not just the visible page — it
 * answers "how much matches the filters", which paging must not change.
 */
function renderDailyBody() {
    const dates = pageDates();
    const start = (currentPage - 1) * PAGE_SIZE;
    const visible = new Set(dates.slice(start, start + PAGE_SIZE));
    const rows = dailyRows.filter((r) => visible.has(r.date));

    renderGroupedTable({
        container: "#dailyBody",
        rows,
        groupBy: GROUP_BY,
        aggregate: dailyAggregate,
        renderValues: (r, i, depth) =>
            statusCells(r, { blankZeros: i !== -1, link: linkFor(r) }) + dailyCells(r, depth),
        renderLabelCells: (r) => `<td></td><td></td>`
            + `<td class="cell-label" style="--depth:2">${esc(r.device)}</td>`
            + `<td>${esc(r.pic)}</td>`,
        labelCols: 4,
        totalCols: totalCols(),
        expanded,
        defaultExpanded: DEFAULT_EXPANDED,
        onToggle: (path) => {
            toggleGroup(expanded, path, DEFAULT_EXPANDED);
            renderDailyBody();
        },
        emptyMessage: "No days match these filters.",
    });

    const totals = sumRows(dailyRows);
    // The footer totals everything the filters left, so its figures lead there —
    // to the filtered span of days, not to one of them.
    $("#dailyFoot").innerHTML = `<tr><td colspan="4">Total</td>${statusCells(totals, {
        link: {
            file: $("#dailyFilterFile").value,
            device: $("#dailyFilterDevice").value,
            pic: $("#dailyFilterPIC").value,
        },
    })}`
        + `<td class="num">${executedIn(totals).toLocaleString()}</td>`
        + `<td class="num"></td><td class="num"></td><td class="num"></td>`
        + `<td class="progress-col"></td></tr>`;
    $("#dailyCount").textContent = `${dates.length} day${dates.length === 1 ? "" : "s"}, `
        + `${dailyRows.length} row${dailyRows.length === 1 ? "" : "s"}`;

    renderPagination({
        container: "#dailyPagination",
        totalItems: dates.length,
        pageSize: PAGE_SIZE,
        currentPage,
        onPageChange: (page) => { currentPage = page; renderDailyBody(); },
    });
}
