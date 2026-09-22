/**
 * Planning view: what each person is meant to test, and how that went.
 *
 * Three cuts of one dataset, because the same plan answers three different
 * questions and no single table answers all of them:
 *
 * - **Day** — one date, everybody. This is the only cut that *edits*; the other
 *   two report. Beside it sits the suggestion table, which is the whole point
 *   of the screen: a plan that cannot be rearranged when the day turns out
 *   differently is a plan nobody keeps.
 * - **Person** — one name, every day. "This week An tested which files, and got
 *   through how much."
 * - **Calendar** — every day, one line each. Where the slack is and where the
 *   work piled up.
 *
 * Like every other view module, this one imports no other view and calls no
 * `fetch` of its own: data comes through `api.js`, and anything that is
 * navigation is reported back to `main.js` through a callback.
 *
 * **A day's rows are edited as a block.** The table holds the rows being
 * edited in a render-local array and writes the whole day in one `PUT`, which
 * is how `views/config.js` treats a config file and for the same reason: a
 * refused edit must leave the stored plan exactly as it was, and validating
 * half a day against rules that are about the whole of it cannot do that.
 *
 * **A row addresses itself by index into that array, never through a `data-`
 * attribute carrying its identity.** The rule the grouped tables follow, for
 * the reason spelled out there — an attribute is not a lossless channel, and a
 * file name or PIC that survived a round trip through one only by luck is a
 * bug waiting for the first unusual character.
 */
import { $, $$, esc } from "../dom.js";
import {
    getPlanCalendar, getPlanDay, getPlanPerson, getPlanSuggest,
    postPlanBaseline, putPlanDay,
} from "../api.js";
import { setPlanCalendar } from "../plan.js";
import { renderPageFooter } from "../pagination.js";
import { makeSortable, paintSortIndicators, sortableTh, sortRows } from "../sorting.js";

/** Which cut is showing: "day" | "person" | "calendar". */
let cut = "day";

/** The date the Day cut is on, as "YYYY-MM-DD". */
let openDate = todayISO();

/** The name the Person cut is on. */
let openPic = "";

/**
 * The rows of the open day, as they are being edited.
 *
 * Not the server's copy: this is the working set, and it only becomes the plan
 * when Save is pressed. A row is `{pic, file, device, planned, actual, diff,
 * baseline}` — the last three are the server's and are not editable, so they
 * are dropped before the PUT.
 */
let dayRows = [];

/** The day as the server last reported it, for the Discard button and the head. */
let dayMeta = { planned_total: 0, actual_total: 0, baseline_total: null, has_baseline: false };

/** Whether `dayRows` differs from what was last loaded or saved. */
let dirty = false;

/** @type {Object[]} the suggestion table's rows */
let suggestRows = [];

/** The device family the suggestion table is narrowed to; "" is every family. */
let suggestFamily = "";

/** @type {Object[]} rows of the Person cut */
let personRows = [];

/** @type {Object[]} rows of the Calendar cut */
let calendarRows = [];

const PAGE_SIZE = 12;
let dayPage = 1;
let personPage = 1;
let calendarPage = 1;
// Paging is off per table, not app-wide: a page number only means something
// inside one table, which is the rule Summary and Detail already follow.
let dayShowAll = false;
let personShowAll = false;
let calendarShowAll = false;

const daySort = { col: "pic", asc: true };
const personSort = { col: "date", asc: true };
const calendarSort = { col: "date", asc: true };

const DAY_NUMERIC = new Set(["planned", "actual", "diff", "baseline"]);
const PERSON_NUMERIC = new Set(["planned", "actual", "diff"]);
const CALENDAR_NUMERIC = new Set(["planned", "actual", "people", "attain"]);

/** Today, in the one date format the whole app uses. */
function todayISO() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * A difference, with its sign and a tone.
 *
 * Ahead is not automatically good and behind is not automatically bad — a day
 * that ran 200 cases against a plan of 30 usually means the plan was wrong —
 * so the tone marks distance from the plan rather than approval of it.
 *
 * @param {?number} diff
 * @returns {string} HTML for one cell.
 */
function diffCell(diff) {
    if (diff == null) return `<td class="num zero">—</td>`;
    const tone = diff === 0 ? "success" : diff > 0 ? "warn" : "danger";
    const sign = diff > 0 ? "+" : "";
    return `<td class="num" data-tone="${tone}">${sign}${diff}</td>`;
}

/** Attainment as a bar, the shape Productivity uses. */
function attainCell(actual, planned) {
    if (!planned) return `<td class="progress-col"><span class="zero">—</span></td>`;
    const pct = Math.round((actual / planned) * 100);
    const tone = pct >= 100 ? "success" : pct >= 80 ? "warn" : "danger";
    return `<td class="progress-col"><span class="progress-cell">
        <span class="progress progress--sm" role="img" aria-label="${pct}% of plan">
            <span class="progress-seg" style="width:${Math.min(100, pct)}%;
                  background:var(--tone-${tone})"></span>
        </span>
        <span class="num" data-tone="${tone}">${pct}%</span>
    </span></td>`;
}

// --- the Day cut -----------------------------------------------------------

/**
 * Load one date and draw it.
 * @param {string} date "YYYY-MM-DD"
 */
async function loadDay(date) {
    const { ok, json } = await getPlanDay(date);
    if (!ok) { setDayError(json.error); return; }

    openDate = json.date;
    dayRows = json.rows.map((r) => ({ ...r }));
    dayMeta = json;
    dirty = false;
    dayPage = 1;
    $("#planDate").value = openDate;
    renderDay();
    await loadSuggestions();
}

function setDayError(message) {
    $("#planDayNote").textContent = message || "";
    $("#planDayNote").hidden = !message;
}

/** Whether a row is work that happened without being planned. */
const isUnplanned = (r) => r.planned == null;

function renderDayHead() {
    $("#planDayHead").innerHTML =
        sortableTh("pic", "PIC")
        + sortableTh("file", "File")
        + sortableTh("device", "Device")
        + sortableTh("planned", "Plan", { cls: "num" })
        + sortableTh("actual", "Actual", { cls: "num" })
        + sortableTh("diff", "Diff", { cls: "num" })
        + `<th class="progress-col">Attainment</th>`
        + `<th class="center">Row</th>`;
    makeSortable("#planDayHead th.sortable", daySort, renderDay);
    paintSortIndicators("#planDayHead th.sortable", daySort);
}

function renderDay() {
    const rows = sortRows(dayRows, daySort, DAY_NUMERIC);
    const page = dayShowAll ? rows
        : rows.slice((dayPage - 1) * PAGE_SIZE, dayPage * PAGE_SIZE);

    $("#planSaveBar").hidden = !dirty;
    $("#planBaselineNote").textContent = dayMeta.has_baseline
        ? `Judged against the ${dayMeta.baseline_total} case${
            dayMeta.baseline_total === 1 ? "" : "s"} planned coming into this day.`
        : "Not yet adjusted on the day itself, so the plan below is also the baseline.";

    if (!rows.length) {
        $("#planDayBody").innerHTML =
            `<tr class="empty-row"><td colspan="8">Nothing planned for this day yet. `
            + `Add a row, or take one from the list on the right.</td></tr>`;
        $("#planDayFoot").innerHTML = "";
        $("#planDayPager").innerHTML = "";
        return;
    }

    // `paths` in the grouped tables, and the same idea: the markup carries an
    // index into this render's array, never the row's own identity.
    $("#planDayBody").innerHTML = page.map((r) => {
        const i = dayRows.indexOf(r);
        return `<tr${isUnplanned(r) ? ' class="row--aside"' : ""}>
            <td>${editable(i, "pic", r.pic)}</td>
            <td class="mono">${editable(i, "file", r.file)}</td>
            <td>${editable(i, "device", r.device)}</td>
            <td class="num">${isUnplanned(r)
                ? `<span class="zero" title="Not planned">—</span>`
                : `<input class="input input--cell num" type="number" min="1"
                          step="1" value="${r.planned}" data-row="${i}" data-field="planned">`}</td>
            <td class="num">${r.actual || `<span class="zero">0</span>`}</td>
            ${diffCell(r.diff)}
            ${attainCell(r.actual, r.planned)}
            <td class="center"><button class="btn btn-sm btn-quiet" data-remove="${i}"
                    title="Remove this row">Remove</button></td>
        </tr>`;
    }).join("");

    const planned = dayRows.reduce((a, r) => a + (r.planned || 0), 0);
    const actual = dayRows.reduce((a, r) => a + (r.actual || 0), 0);
    $("#planDayFoot").innerHTML = `<tr>
        <td colspan="3">Total</td>
        <td class="num"><b>${planned}</b></td>
        <td class="num"><b>${actual}</b></td>
        ${diffCell(actual - planned)}
        ${attainCell(actual, planned)}
        <td></td>
    </tr>`;

    renderPageFooter({
        container: "#planDayPager",
        totalItems: rows.length,
        pageSize: PAGE_SIZE,
        currentPage: dayPage,
        showAll: dayShowAll,
        onPageChange: (p) => { dayPage = p; renderDay(); },
        onToggleAll: (all) => { dayShowAll = all; dayPage = 1; renderDay(); },
    });
}

/**
 * A cell the reader can type into.
 *
 * Unplanned rows are read-only: they describe work that already happened, and
 * editing the name on one would not move the case, it would only make the row
 * stop matching the actual it was built from.
 */
function editable(i, field, value) {
    if (isUnplanned(dayRows[i])) return esc(value);
    return `<input class="input input--cell" value="${esc(value)}" `
         + `data-row="${i}" data-field="${field}">`;
}

/** Take a block from the suggestion table into the day's plan. */
function assign(row) {
    const pic = ($("#planNewPic").value || "").trim();
    if (!pic) {
        setDayError("Type the name of whoever takes it first — a plan row belongs "
                  + "to somebody.");
        $("#planNewPic").focus();
        return;
    }
    setDayError("");
    const existing = dayRows.find(
        (r) => r.pic === pic && r.file === row.file && r.device === row.device);
    if (existing) {
        // The same person, file and device twice is one row with the counts
        // added — which is what the server refuses, so add rather than append.
        existing.planned = (existing.planned || 0) + (row.free || row.remaining);
    } else {
        dayRows.push({
            pic, file: row.file, device: row.device,
            planned: row.free || row.remaining,
            actual: 0, diff: null, baseline: null,
        });
    }
    dirty = true;
    renderDay();
}

async function saveDay() {
    const entries = dayRows.filter((r) => !isUnplanned(r)).map((r) => ({
        pic: r.pic, file: r.file, device: r.device, planned: Number(r.planned),
    }));
    const { ok, json } = await putPlanDay(openDate, entries);
    if (!ok) { setDayError(json.error); return; }

    setDayError("");
    dayRows = json.rows.map((r) => ({ ...r }));
    dayMeta = json;
    dirty = false;
    renderDay();
    // `refreshCalendar` hands the new calendar to `plan.js`, which is what
    // tells Daily and Productivity their plan figures moved. This module knows
    // about neither view.
    await Promise.all([loadSuggestions(), refreshCalendar()]);
}

// --- the suggestion table --------------------------------------------------

async function loadSuggestions() {
    const { ok, json } = await getPlanSuggest(openDate, suggestFamily);
    suggestRows = ok ? json.rows : [];
    renderSuggestions();
}

function renderSuggestions() {
    const families = [...new Set(suggestRows.map((r) => r.device_family))].sort();
    // Rebuilt from the rows in hand, so a family the current load has none of
    // cannot stay pressed and narrow the table to nothing.
    if (suggestFamily && !families.includes(suggestFamily)) suggestFamily = "";

    $("#planFamilyTabs").innerHTML =
        [["", "All devices"], ...families.map((f) => [f, f])]
            .map(([key, label]) => `<button class="toggle${
                key === suggestFamily ? " is-on" : ""}" data-family="${esc(key)}"
                aria-pressed="${key === suggestFamily}">${esc(label)}</button>`)
            .join("");

    if (!suggestRows.length) {
        $("#planSuggestBody").innerHTML =
            `<tr class="empty-row"><td colspan="4">Nothing left to run on this `
            + `device — every case in the plan has a result.</td></tr>`;
        return;
    }

    $("#planSuggestBody").innerHTML = suggestRows.map((r, i) => {
        const takers = r.assigned_to.map((t) => `${esc(t.pic)} ${t.planned}`).join(" · ");
        return `<tr${r.free ? "" : ' class="row--aside"'}>
            <td class="mono">${esc(r.file)}</td>
            <td>${esc(r.device)}</td>
            <td class="num" title="${r.remaining} left of ${r.total} in the plan">
                <b>${r.free}</b>${r.assigned
                    ? ` <span class="zero">of ${r.remaining}</span>` : ""}
                ${takers ? `<br><span class="cell-sub">${takers}</span>` : ""}</td>
            <td class="center"><button class="btn btn-sm" data-assign="${i}">Assign</button></td>
        </tr>`;
    }).join("");
}

// --- the Person cut --------------------------------------------------------

function renderPersonHead() {
    $("#planPersonHead").innerHTML =
        sortableTh("date", "Date")
        + sortableTh("file", "File")
        + sortableTh("device", "Device")
        + sortableTh("planned", "Plan", { cls: "num" })
        + sortableTh("actual", "Actual", { cls: "num" })
        + sortableTh("diff", "Diff", { cls: "num" })
        + `<th class="progress-col">Attainment</th>`;
    makeSortable("#planPersonHead th.sortable", personSort, renderPerson);
    paintSortIndicators("#planPersonHead th.sortable", personSort);
}

async function loadPerson(pic) {
    openPic = pic;
    if (!pic) { personRows = []; renderPerson(); return; }
    const { ok, json } = await getPlanPerson(pic);
    personRows = ok ? json.rows : [];
    personPage = 1;
    renderPerson();
}

function renderPerson() {
    if (!openPic) {
        $("#planPersonBody").innerHTML =
            `<tr class="empty-row"><td colspan="7">Pick a name above.</td></tr>`;
        $("#planPersonFoot").innerHTML = "";
        $("#planPersonPager").innerHTML = "";
        return;
    }

    const rows = sortRows(personRows, personSort, PERSON_NUMERIC);
    const page = personShowAll ? rows
        : rows.slice((personPage - 1) * PAGE_SIZE, personPage * PAGE_SIZE);

    if (!rows.length) {
        $("#planPersonBody").innerHTML =
            `<tr class="empty-row"><td colspan="7">Nothing planned for ${esc(openPic)}, `
            + `and nothing run by them in what is loaded.</td></tr>`;
        $("#planPersonFoot").innerHTML = "";
        $("#planPersonPager").innerHTML = "";
        return;
    }

    $("#planPersonBody").innerHTML = page.map((r) => `<tr${
        r.planned == null ? ' class="row--aside"' : ""}>
        <td class="mono"><button type="button" class="cell-link" data-goday="${esc(r.date)}">${
            esc(r.date)}</button></td>
        <td class="mono">${esc(r.file)}</td>
        <td>${esc(r.device)}</td>
        <td class="num">${r.planned == null ? `<span class="zero">—</span>` : r.planned}</td>
        <td class="num">${r.actual || `<span class="zero">0</span>`}</td>
        ${diffCell(r.diff)}
        ${attainCell(r.actual, r.planned)}
    </tr>`).join("");

    const planned = rows.reduce((a, r) => a + (r.planned || 0), 0);
    const actual = rows.reduce((a, r) => a + (r.actual || 0), 0);
    $("#planPersonFoot").innerHTML = `<tr>
        <td colspan="3">Total</td>
        <td class="num"><b>${planned}</b></td>
        <td class="num"><b>${actual}</b></td>
        ${diffCell(actual - planned)}
        ${attainCell(actual, planned)}
    </tr>`;

    renderPageFooter({
        container: "#planPersonPager",
        totalItems: rows.length,
        pageSize: PAGE_SIZE,
        currentPage: personPage,
        showAll: personShowAll,
        onPageChange: (p) => { personPage = p; renderPerson(); },
        onToggleAll: (all) => { personShowAll = all; personPage = 1; renderPerson(); },
    });
}

// --- the Calendar cut ------------------------------------------------------

function renderCalendarHead() {
    $("#planCalendarHead").innerHTML =
        sortableTh("date", "Date")
        + sortableTh("people", "People", { cls: "num center" })
        + sortableTh("planned", "Plan", { cls: "num" })
        + sortableTh("actual", "Actual", { cls: "num" })
        + `<th class="progress-col">Attainment</th>`;
    makeSortable("#planCalendarHead th.sortable", calendarSort, renderCalendar);
    paintSortIndicators("#planCalendarHead th.sortable", calendarSort);
}

/** Re-pull the calendar, which both the Calendar cut and Daily read. */
async function refreshCalendar() {
    const { ok, json } = await getPlanCalendar();
    calendarRows = ok ? json.days : [];
    // `plan.js` is where Daily and Productivity read it from; this view happens
    // to be what fetches it, the way `main.js` fetches it on load.
    setPlanCalendar(ok ? json : null);
    renderCalendar();
}

function renderCalendar() {
    const rows = sortRows(calendarRows, calendarSort, CALENDAR_NUMERIC);
    const page = calendarShowAll ? rows
        : rows.slice((calendarPage - 1) * PAGE_SIZE, calendarPage * PAGE_SIZE);

    if (!rows.length) {
        $("#planCalendarBody").innerHTML =
            `<tr class="empty-row"><td colspan="5">No day has been planned yet, and `
            + `nothing loaded carries a test date.</td></tr>`;
        $("#planCalendarFoot").innerHTML = "";
        $("#planCalendarPager").innerHTML = "";
        return;
    }

    $("#planCalendarBody").innerHTML = page.map((r) => `<tr${
        r.planned ? "" : ' class="row--aside"'}>
        <td class="mono"><button type="button" class="cell-link" data-goday="${esc(r.date)}">${
            esc(r.date)}</button></td>
        <td class="num center">${r.people || `<span class="zero">0</span>`}</td>
        <td class="num">${r.planned || `<span class="zero">—</span>`}</td>
        <td class="num">${r.actual || `<span class="zero">0</span>`}</td>
        ${attainCell(r.actual, r.planned)}
    </tr>`).join("");

    const planned = rows.reduce((a, r) => a + r.planned, 0);
    const actual = rows.reduce((a, r) => a + r.actual, 0);
    $("#planCalendarFoot").innerHTML = `<tr>
        <td colspan="2">Total</td>
        <td class="num"><b>${planned}</b></td>
        <td class="num"><b>${actual}</b></td>
        ${attainCell(actual, planned)}
    </tr>`;

    renderPageFooter({
        container: "#planCalendarPager",
        totalItems: rows.length,
        pageSize: PAGE_SIZE,
        currentPage: calendarPage,
        showAll: calendarShowAll,
        unit: "day",
        onPageChange: (p) => { calendarPage = p; renderCalendar(); },
        onToggleAll: (all) => { calendarShowAll = all; calendarPage = 1; renderCalendar(); },
    });
}

// --- the cuts --------------------------------------------------------------

function showCut(next) {
    cut = next;
    $$("#planCuts .toggle").forEach((b) => {
        const on = b.dataset.cut === cut;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", String(on));
    });
    ["day", "person", "calendar"].forEach((c) => {
        $(`#planCut-${c}`).hidden = c !== cut;
    });
}

/**
 * Jump to one date's plan from a date cell in either reporting cut.
 *
 * A date in those tables is the question "what was meant to happen that day",
 * and the Day cut is the answer — so the cell is a door into it, the same idea
 * as every status figure being a door into its cases.
 */
function openDay(date) {
    showCut("day");
    loadDay(date);
}

// --- wiring ----------------------------------------------------------------

/** Wire the view. Call once, at startup. */
export function initPlanningView() {
    renderDayHead();
    renderPersonHead();
    renderCalendarHead();

    $("#planCuts").addEventListener("click", (e) => {
        const b = e.target.closest("[data-cut]");
        if (b) showCut(b.dataset.cut);
    });

    $("#planDate").addEventListener("change", (e) => loadDay(e.target.value));
    $("#planPrevDay").addEventListener("click", () => loadDay(shiftDay(openDate, -1)));
    $("#planNextDay").addEventListener("click", () => loadDay(shiftDay(openDate, 1)));
    $("#planToday").addEventListener("click", () => loadDay(todayISO()));

    $("#planAddRow").addEventListener("click", () => {
        const pic = ($("#planNewPic").value || "").trim();
        if (!pic) { setDayError("A plan row belongs to somebody — type a name first.");
                    $("#planNewPic").focus(); return; }
        setDayError("");
        dayRows.push({ pic, file: "", device: "", planned: 1,
                       actual: 0, diff: null, baseline: null });
        dirty = true;
        renderDay();
    });

    $("#planSave").addEventListener("click", saveDay);
    $("#planDiscard").addEventListener("click", () => loadDay(openDate));
    $("#planRebaseline").addEventListener("click", async () => {
        const { ok, json } = await postPlanBaseline(openDate);
        if (!ok) { setDayError(json.error); return; }
        dayMeta = json;
        renderDay();
    });

    // One listener on the body rather than one per input: the rows are redrawn
    // on every keystroke's worth of state change, and per-row listeners would
    // be rebound each time.
    $("#planDayBody").addEventListener("input", (e) => {
        const el = e.target.closest("[data-row]");
        if (!el) return;
        const row = dayRows[Number(el.dataset.row)];
        if (!row) return;
        row[el.dataset.field] = el.dataset.field === "planned"
            ? Number(el.value) : el.value;
        dirty = true;
        $("#planSaveBar").hidden = false;
    });
    $("#planDayBody").addEventListener("click", (e) => {
        const b = e.target.closest("[data-remove]");
        if (!b) return;
        dayRows.splice(Number(b.dataset.remove), 1);
        dirty = true;
        renderDay();
    });

    $("#planFamilyTabs").addEventListener("click", (e) => {
        const b = e.target.closest("[data-family]");
        if (!b) return;
        suggestFamily = b.dataset.family;
        loadSuggestions();
    });
    $("#planSuggestBody").addEventListener("click", (e) => {
        const b = e.target.closest("[data-assign]");
        if (b) assign(suggestRows[Number(b.dataset.assign)]);
    });

    $("#planPerson").addEventListener("change", (e) => loadPerson(e.target.value));

    // Both reporting cuts make their date cells doors into the Day cut.
    ["#planPersonBody", "#planCalendarBody"].forEach((sel) => {
        $(sel).addEventListener("click", (e) => {
            const b = e.target.closest("[data-goday]");
            if (b) openDay(b.dataset.goday);
        });
    });

    showCut("day");
}

/** One day either side of `date`, in the app's date format. */
function shiftDay(date, by) {
    const d = new Date(`${date}T00:00:00`);
    d.setDate(d.getDate() + by);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Adopt a fresh load: refill the PIC list and redraw every cut.
 *
 * The names offered are the ones the loaded cases carry, because those are the
 * people whose work the plan can be checked against. A name can still be typed
 * freely into the Day cut — somebody planned for tomorrow has not tested
 * anything yet, so insisting on a known name would make it impossible to plan
 * for a new joiner.
 *
 * @param {Object[]} productivity `/api/productivity` rows, which name every PIC.
 */
export async function initPlanning(productivity) {
    const names = [...new Set((productivity || []).map((r) => r.pic))]
        .filter((n) => n && n !== "N/A").sort();
    $("#planPerson").innerHTML = `<option value="">Pick a person…</option>`
        + names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
    $("#planPicList").innerHTML = names.map((n) => `<option value="${esc(n)}">`).join("");

    if (openPic && !names.includes(openPic)) openPic = "";
    $("#planPerson").value = openPic;

    await Promise.all([loadDay(openDate), refreshCalendar()]);
    await loadPerson(openPic);
}
