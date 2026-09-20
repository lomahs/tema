/**
 * Detail view: the case list for the whole taxonomy, fetched a status at a time.
 *
 * This is where a status figure leads. Every number in a status band on Summary,
 * on the file page and on Daily is a button, and pressing it opens this screen
 * showing exactly the cases behind it — an OK and a Not Yet Started as readily
 * as an NG. That is what it stopped being "Review", which held only the statuses
 * `parser/result_status.json` marks `"review": true`; that restriction survives
 * as the *selection* the rail and Summary's "To review" card arrive with, rather
 * than as a wall around the screen.
 *
 * **Cases arrive one status at a time, and are kept.** Nothing is fetched until
 * a status is chosen; `/api/cases?status=NG` is asked once and its answer cached
 * for as long as the load lasts, so pressing NG again costs nothing and pressing
 * OK costs only the OKs. Every other narrowing — scope, file, device, PIC, the
 * dates, the search box, sorting, grouping, paging — happens here, over what is
 * already in hand, so none of them is a round trip. The cache is dropped when
 * the source is reloaded or a config is saved, because either can change what a
 * case *is*.
 *
 * It follows that the status slices must partition the load, which is
 * `aggregate.status_cases`'s job and asserted there: a case in two slices would
 * be listed twice the moment two statuses are chosen, and one in no slice could
 * never be reached from any figure.
 *
 * **The scope cards are how work outside the plan is added.** One card per scope
 * group, multi-select, the counted ones pressed to begin with — so the figure
 * this screen opens on is the one Summary calls Total, and a group the plan
 * excludes is something the reader deliberately adds rather than something that
 * quietly inflates a count. Scope is a filter over the cache, not part of the
 * fetch key, so pressing a card never asks the server anything.
 *
 * **The status cards count from the summary rows, not from the cases.** They
 * report how many cases each status has *within the pressed scopes*, which is
 * exactly "how many there are to fetch" — a card that could only count what had
 * already been fetched would read 0 for everything nobody had clicked yet. The
 * other filters narrow the table beneath them without moving them; the strip
 * says so.
 *
 * Owns the case cache, the chosen statuses and scopes, the derived
 * filtered / grouped / paged state, and the two conditions a drill-in can set
 * that no control on the screen expresses.
 *
 * Grouping is optional here, unlike Summary and Daily. A flat list of cases is
 * the right default — you often want to scan or sort across every file at once
 * — so the group-by control starts at "No grouping" and paging counts rows.
 * Turn grouping on and paging counts groups instead, so a file never straddles
 * a page boundary.
 */
import { $, esc } from "../dom.js";
import { getCases } from "../api.js";
import { renderCharts, resizeCharts } from "../charts.js";
import { populateSelect, uniqueOf } from "../filters.js";
import { renderGroupedTable, toggleGroup } from "../groupedTable.js";
import { renderPageFooter } from "../pagination.js";
import { makeSortable, paintSortIndicators, sortableTh, sortGrouped, sortRows } from "../sorting.js";
import {
    getReasonStatuses, getReviewStatuses, getStatuses, isExcluded, lacksReason,
    renderStatCards, sumRows, toneFor,
} from "../taxonomy.js";

const PAGE_SIZE = 50;

/** Groups per page once grouping is on. */
const GROUP_PAGE_SIZE = 8;

/** Whether paging is off and every matching row is rendered into the pane. */
let showAll = false;

/** Whether the list is narrowed to cases that owe a reason and carry none. */
let missingOnly = false;

const DEFAULT_EXPANDED = true;

/**
 * Status key -> that status' cases, as `/api/cases` served them.
 *
 * The whole reason this screen is affordable. Cleared by {@link initDetail},
 * which runs on every load and every config save — the cases behind a status
 * can change without anything here being clicked.
 *
 * @type {Map<string, Object[]>}
 */
const cache = new Map();

/** @type {Set<string>} status keys chosen; also the fetch key. Empty shows nothing. */
const chosenStatuses = new Set();

/** @type {Set<string>} scope group keys pressed. A filter over the cache, never fetched. */
const chosenScopes = new Set();

/**
 * @type {Set<string>} raw Scope strings pressed in the filter well.
 *
 * Empty means every scope, which is what the select this replaced meant by "".
 * A narrowing, not a selection: unlike `chosenScopes` it never decides which
 * cases are here, only which of them are listed — which is why `clearNarrowing`
 * empties this one and deliberately leaves that one alone.
 */
const chosenRawScopes = new Set();

/** @type {{key: string, label: string, counted: boolean}[]} groups, from /api/summary */
let scopeGroups = [];

/** @type {Object[]} /api/summary rows — where the card figures come from */
let summaryRows = [];

/** @type {Object[]} the cached cases of the chosen statuses, within the chosen scopes */
let allData = [];

/** @type {Object[]} `allData` after the filters and the sort */
let filtered = [];

/**
 * Two narrowings a drill-in can arrive with that no control here expresses.
 *
 * Clicking a figure on a "By device type" row means *that handset*, which is
 * several device names; clicking one on the file page means *that sheet*. Both
 * ride on the case (`device_family` and `sheet` come down with it) rather than
 * being re-derived here, and both are clearable from the chip row — which is
 * why they are conditions and not hidden state.
 */
let conditions = { deviceFamily: "", sheet: "" };

/**
 * Filter values a drill-in asked for, applied once its cases have arrived.
 *
 * The File / Device / PIC selects are filled from the cases in hand, so setting
 * one before the fetch lands would be assigning a value that is not yet an
 * option. The row clicked is made of those very cases, so by the time they
 * arrive the option exists.
 *
 * @type {?Object}
 */
let pending = null;

let currentPage = 1;

/** Whether a fetch is in flight, and which one is the current answer. */
let loading = false;
let loadToken = 0;

/** Whether the cache was dropped since this view was last drawn. */
let stale = true;

/** @type {Set<string>} which groups are open */
const expanded = new Set();

/** @type {import("../sorting.js").SortState} */
const detailSort = { col: null, asc: true };

/** Columns, in order. `col` is the sort key; a blank one is not sortable. */
const COLUMNS = [
    { col: "", label: "#", cls: "num" },
    { col: "file_name", label: "File" },
    { col: "sheet", label: "Sheet" },
    { col: "device", label: "Device" },
    { col: "row_num", label: "Row", cls: "num" },
    { col: "case_no", label: "Case no" },
    { col: "scope", label: "Scope" },
    { col: "result", label: "Result" },
    { col: "test_date", label: "Date" },
    { col: "pic", label: "PIC" },
    { col: "ticket_id", label: "Ticket ID" },
    { col: "note", label: "Note" },
];

/**
 * Single-choice selects that narrow the list, with the label used on their chip.
 *
 * Result is not among them: it narrows by *status* rather than by the raw text
 * of the cell, it takes several values at once, and it is what decides which
 * cases are fetched at all — so it is handled on its own throughout this module.
 *
 * Scope is not among them either, and for the same first reason: it takes
 * several values at once. It narrows by the raw string in the cell, which is a
 * finer vocabulary than the cards at the top of the screen — the cards pick
 * *groups*, this picks the spellings inside them — and asking for two spellings
 * of one commitment ("FPT" and "FPT (JM Support)") is the normal question, not
 * an exotic one. So it is a strip of toggles like Result, and `chosenRawScopes`
 * below is its state. It differs from Result in what an empty set means: Result
 * decides which cases are *fetched*, so all-pressed is its neutral position,
 * while this only narrows cases already in hand, so **empty means no narrowing**
 * — exactly what the select's "" meant before it.
 */
const FILTERS = [
    { id: "filterFile", field: "file_name", label: "File" },
    { id: "filterDevice", field: "device", label: "Device" },
    { id: "filterPIC", field: "pic", label: "PIC" },
];
const DATE_FILTERS = [
    { id: "filterDateFrom", label: "From" },
    { id: "filterDateTo", label: "To" },
];

/**
 * Attach the filter, search, grouping, clear and chart-toggle listeners. Call
 * once, at startup.
 *
 * The sortable headers are regenerated per taxonomy load, so they are bound in
 * {@link renderDetailHead} instead — binding them here as well would stack a
 * second listener and make one click sort twice. The status and scope cards are
 * regenerated too, which is why both are bound through their strip.
 */
export function initDetailView() {
    const rerender = () => { currentPage = 1; applyFilters(); };

    [...FILTERS, ...DATE_FILTERS].forEach(({ id }) =>
        $("#" + id).addEventListener("change", rerender));
    $("#filterSearch").addEventListener("input", rerender);

    // One listener on the strip, so it can be rebuilt on every load without
    // rebinding. Unlike the Result toggles beside it, this never fetches: it
    // narrows cases already in hand.
    $("#filterScope").addEventListener("click", (e) => {
        const b = e.target.closest("button[data-scope-toggle]");
        if (!b) return;
        const v = b.dataset.scopeToggle;
        if (chosenRawScopes.has(v)) chosenRawScopes.delete(v);
        else chosenRawScopes.add(v);
        paintScopeToggles();
        rerender();
    });

    // One listener on the group rather than one per button, so the toggles can
    // be redrawn on every taxonomy load without rebinding anything. Unlike every
    // other control here, this one may have to fetch: a status nobody has picked
    // yet has no cases in hand.
    $("#filterResult").addEventListener("click", (e) => {
        const key = e.target.closest("button[data-status]")?.dataset.status;
        if (!key) return;
        if (chosenStatuses.has(key)) chosenStatuses.delete(key);
        else chosenStatuses.add(key);
        paintResultToggles();
        loadChosen();
    });
    $("#detailGroupBy").addEventListener("change", rerender);

    // The status cards are the design's tab row: a single pick over the same
    // state the Result toggles edit one at a time. One listener on the strip,
    // because the cards are regenerated on every taxonomy load.
    $("#statsRow").addEventListener("click", (e) => {
        const card = e.target.closest("button[data-status-card]");
        if (!card) return;
        const key = card.dataset.statusCard;
        if (!key) {
            // "All" is the one deliberately expensive pick on the screen: it
            // means every status, so it fetches the ones nobody has opened yet.
            getStatuses().forEach((s) => chosenStatuses.add(s.key));
        } else {
            chosenStatuses.clear();
            // Clicking the card already selected clears it, so the row is also
            // the way back out.
            if (card.getAttribute("aria-pressed") !== "true") chosenStatuses.add(key);
        }
        paintResultToggles();
        loadChosen();
    });

    // The scope cards never fetch: every case of a chosen status is already
    // here, whichever group it belongs to, so a card is a filter over the cache.
    $("#detailScopes").addEventListener("click", (e) => {
        const card = e.target.closest("button[data-scope-card]");
        if (!card) return;
        const key = card.dataset.scopeCard;
        if (!key) {
            // All: press every group, including any the plan excludes. Asking
            // for everything is the one moment adding those is not a quiet
            // default but the thing that was clicked.
            scopeGroups.forEach((g) => chosenScopes.add(g.key));
        } else if (chosenScopes.has(key)) {
            chosenScopes.delete(key);
        } else {
            chosenScopes.add(key);
        }
        paintScopeCards();
        currentPage = 1;
        rebuild();
    });

    // Filters are folded away by default: search plus the status cards answers
    // most of what this screen is opened for, and nine controls above the table
    // pushed the first row of data off a laptop screen.
    $("#btnToggleFilters").addEventListener("click", () => {
        const well = $("#detailFilters");
        well.hidden = !well.hidden;
        $("#btnToggleFilters").setAttribute("aria-expanded", String(!well.hidden));
    });

    // A condition, not a status: it narrows *within* whatever results are
    // chosen, so it sits beside the Result toggles rather than among them.
    $("#btnMissingReason").addEventListener("click", () => {
        missingOnly = !missingOnly;
        paintMissingReason();
        rerender();
    });

    $("#btnClearFilters").addEventListener("click", () => {
        clearNarrowing();
        rerender();
    });

    $("#btnToggleCharts").addEventListener("click", () => {
        const strip = $("#chartsRow");
        const show = strip.hidden;
        strip.hidden = !show;
        $("#btnToggleCharts").setAttribute("aria-expanded", String(show));
        $("#btnToggleCharts").textContent = show ? "Hide charts" : "Show charts";
        // Chart.js sizes to a 0x0 container while the strip is hidden.
        if (show) resizeCharts();
    });
}

/**
 * Clear everything that narrows the list, leaving the selection alone.
 *
 * The statuses and the scopes are deliberately untouched: they are what decides
 * which cases exist on this screen at all, and a "Clear all" that emptied the
 * table would be offering to show you nothing. The grouping choice is left too.
 */
function clearNarrowing() {
    [...FILTERS, ...DATE_FILTERS].forEach(({ id }) => { $("#" + id).value = ""; });
    chosenRawScopes.clear();
    paintScopeToggles();
    $("#filterSearch").value = "";
    conditions = { deviceFamily: "", sheet: "" };
    missingOnly = false;
    paintMissingReason();
}

/** Reflect `missingOnly` onto its button. */
function paintMissingReason() {
    $("#btnMissingReason").setAttribute("aria-pressed", String(missingOnly));
}

/** The scope groups that count toward the total — the selection this view opens on. */
function defaultScopes() {
    chosenScopes.clear();
    scopeGroups.filter((g) => g.counted !== false)
        .forEach((g) => chosenScopes.add(g.key));
}

/**
 * Open this view on the statuses that count as open work.
 *
 * What the rail arrives with, and where Summary's "To review" card leads. The
 * restriction that used to define this screen is this one selection now.
 */
export function showReview() {
    clearNarrowing();
    chosenStatuses.clear();
    getReviewStatuses().forEach((s) => chosenStatuses.add(s.key));
    defaultScopes();
    paintScopeCards();
    paintResultToggles();
    showAll = false;
    return loadChosen();
}

/**
 * Open this view showing only the cases that owe a reason and carry none.
 *
 * Called from `main.js` when Summary's Missing reason card is pressed. Every
 * other narrowing is cleared first: the card reports over the whole load, so
 * arriving into a list still narrowed by somebody's earlier File choice would
 * show a smaller number than the card that sent you.
 *
 * The statuses chosen are the ones that *oblige* a reason, which is what the
 * card counted — not the review ones. A status can need a reason without being
 * open work, and arriving with only the review statuses chosen would silently
 * drop exactly those rows.
 */
export function showMissingReason() {
    clearNarrowing();
    chosenStatuses.clear();
    getReasonStatuses().forEach((s) => chosenStatuses.add(s.key));
    defaultScopes();
    paintScopeCards();
    missingOnly = true;
    paintMissingReason();
    paintResultToggles();
    showAll = false;
    return loadChosen();
}

/**
 * Open this view on the cases behind one status figure.
 *
 * The other half of making the status band a door: the figure says which status
 * and which row it was counted on, and this narrows to exactly that. `main.js`
 * routes every band on every screen here, so a figure means the same thing
 * wherever it is clicked.
 *
 * A row that names its scope group selects that card alone — the figure counted
 * that group and nothing else. One that does not (Daily reports over the plan
 * rather than per group) falls back to the counted groups.
 *
 * @param {Object} ctx
 * @param {string} [ctx.status] The status key the figure counts.
 * @param {string[]} [ctx.statuses] Several, where the figure was a roll-up over
 *   them — Summary's Executed and Pass rate cards each count a set the taxonomy
 *   defines, and opening one on a single status would list less than it said.
 * @param {string} [ctx.file] Workbook basename.
 * @param {string} [ctx.device] One device name.
 * @param {string} [ctx.deviceFamily] A handset, where the row merged its sizes.
 * @param {string} [ctx.scope] A scope *group* key, not a raw Scope string.
 * @param {string} [ctx.sheet] One sheet of one workbook.
 * @param {string} [ctx.pic] One tester.
 * @param {string} [ctx.date] One test date, applied to both date bounds.
 */
export function showStatusCases(ctx) {
    clearNarrowing();
    chosenStatuses.clear();
    (ctx.statuses || (ctx.status ? [ctx.status] : [])).forEach((k) => chosenStatuses.add(k));

    // `scopes` for a figure counted over several groups at once — Summary draws
    // one table per *role* now, so a card may hold more than one — and `scope`
    // for a single one. Both are filtered against the configured groups: a key
    // this build does not know is dropped rather than narrowing the view to
    // nothing, and if that leaves none, the default selection stands.
    const asked = (ctx.scopes || (ctx.scope ? [ctx.scope] : []))
        .filter((k) => scopeGroups.some((g) => g.key === k));
    if (asked.length) {
        chosenScopes.clear();
        asked.forEach((k) => chosenScopes.add(k));
    } else {
        defaultScopes();
    }
    paintScopeCards();
    paintResultToggles();

    conditions = { deviceFamily: ctx.deviceFamily || "", sheet: ctx.sheet || "" };
    // The selects are filled from the cases, so these wait for them to arrive.
    pending = { file: ctx.file, device: ctx.device, pic: ctx.pic, date: ctx.date };

    showAll = false;
    currentPage = 1;
    return loadChosen();
}

/**
 * Fetch whichever chosen statuses are not cached, then redraw.
 *
 * A slow first answer must not overwrite a fast second one, so each run takes a
 * token and a stale run drops its result rather than rendering it — otherwise
 * clicking NG and then OK could leave the NGs on screen with OK pressed.
 *
 * A refused status (400) is dropped from the selection rather than retried: the
 * only way to ask for one the taxonomy does not name is to have had this screen
 * open while somebody removed it in Config.
 */
async function loadChosen() {
    stale = false;
    currentPage = 1;
    const missing = [...chosenStatuses].filter((key) => !cache.has(key));
    if (!missing.length) { rebuild(); return; }

    const token = ++loadToken;
    loading = true;
    renderTable();

    const answers = await Promise.all(
        missing.map(async (key) => [key, await getCases(key)]));
    if (token !== loadToken) return;   // a later click is the current answer

    answers.forEach(([key, { ok, json }]) => {
        if (ok) cache.set(key, json);
        else chosenStatuses.delete(key);
    });
    loading = false;
    paintResultToggles();
    rebuild();
}

/**
 * Rebuild `allData` from the cache and redraw.
 *
 * Taxonomy order rather than the order the statuses were clicked, so the
 * unsorted table reads the way every other status list in the app does.
 */
function rebuild() {
    allData = [];
    getStatuses().forEach((s) => {
        if (!chosenStatuses.has(s.key)) return;
        (cache.get(s.key) || []).forEach((d) => {
            if (chosenScopes.has(d.scope_group)) allData.push(d);
        });
    });

    expanded.clear();
    FILTERS.forEach(({ id, field }) => populateSelect("#" + id, uniqueOf(allData, field)));
    renderScopeToggles();

    if (pending) {
        // The row clicked is made of these cases, so its file, device and PIC
        // are options by now.
        if (pending.file) $("#filterFile").value = pending.file;
        if (pending.device) $("#filterDevice").value = pending.device;
        if (pending.pic) $("#filterPIC").value = pending.pic;
        if (pending.date) {
            $("#filterDateFrom").value = pending.date;
            $("#filterDateTo").value = pending.date;
        }
        pending = null;
    }

    applyFilters();
}

/**
 * How many cases count as open work — the figure the rail carries beside Detail.
 *
 * Read off the summary rows rather than off the cases, because the cases of a
 * review status may never be fetched: the rail states this whether or not
 * anybody opens the screen. Counted over the scope groups in the plan, which is
 * what the selection this view opens on shows.
 *
 * @returns {number}
 */
export function reviewCount() {
    const counted = new Set(scopeGroups.filter((g) => g.counted !== false).map((g) => g.key));
    const totals = sumRows(summaryRows.filter((r) => counted.has(r.scope)));
    return getReviewStatuses().reduce((n, s) => n + (totals[s.key] || 0), 0);
}

/**
 * Adopt a fresh load and drop the cache.
 *
 * Nothing is fetched here. The cases behind a figure are worth a request when
 * somebody asks for them, and a load whose Detail screen is never opened should
 * cost nothing at all — which is the whole point of serving them per status.
 * The exception is a reader already standing on this screen when the source is
 * reloaded or a config saved: their rows are now wrong, so those are re-fetched
 * at once. Everyone else gets them from {@link enterDetail}.
 *
 * @param {{groups: Object[], scopes: Object[]}} summary The `/api/summary` body.
 *   Its rows are what the status cards count, and its `scopes` are the cards.
 */
export function initDetail(summary) {
    summaryRows = summary.groups || [];
    scopeGroups = summary.scopes || [];
    cache.clear();
    allData = [];
    filtered = [];
    stale = true;

    // A status or a group can disappear in Config while this screen is open.
    const keys = new Set(getStatuses().map((s) => s.key));
    [...chosenStatuses].forEach((k) => { if (!keys.has(k)) chosenStatuses.delete(k); });
    if (!chosenStatuses.size) getReviewStatuses().forEach((s) => chosenStatuses.add(s.key));
    const groups = new Set(scopeGroups.map((g) => g.key));
    [...chosenScopes].forEach((k) => { if (!groups.has(k)) chosenScopes.delete(k); });
    if (!chosenScopes.size) defaultScopes();

    renderScopeCards();
    paintResultToggles();
    renderStats();
    renderTable();

    if (!$("#detailView").hidden) return loadChosen();
    return Promise.resolve();
}

/**
 * Fetch what the current selection needs, if the cache has been dropped since
 * this view was last drawn. Called by `main.js` when the view is shown.
 */
export function enterDetail() {
    if (stale) loadChosen();
}

/**
 * Draw one toggle per status.
 *
 * Rebuilt from the taxonomy rather than written into the template, and called
 * again whenever the selection changes so `aria-pressed` stays truthful — a
 * toggle group that lies to a screen reader is worse than a plain select.
 */
export function renderResultToggles() {
    $("#filterResult").innerHTML = getStatuses().map((st) =>
        `<button type="button" class="toggle" data-status="${esc(st.key)}"`
        + ` data-tone="${esc(toneFor(st.key))}" aria-pressed="false">${esc(st.label)}</button>`
    ).join("");
    paintResultToggles();
}

/**
 * Draw the Scope toggles: every raw spelling present in the cases in hand.
 *
 * Rebuilt on every `rebuild`, exactly as `populateSelect` refilled the select it
 * replaces — the vocabulary is the data's, not the config's, so a scope nobody
 * has written down this load has no toggle. A pressed scope that disappears
 * that way is dropped from the set at the same time, because a narrowing on a
 * value no case carries would empty the table with no visible control to undo
 * it.
 */
function renderScopeToggles() {
    const values = uniqueOf(allData, "scope");
    // Drop any pressed value the new data no longer has.
    [...chosenRawScopes].forEach((v) => { if (!values.includes(v)) chosenRawScopes.delete(v); });

    $("#filterScope").innerHTML = values.map((v) =>
        `<button type="button" class="toggle" data-scope-toggle="${esc(v)}"`
        + ` aria-pressed="false">${esc(v)}</button>`).join("");
    paintScopeToggles();
}

/** Reflect `chosenRawScopes` onto the toggles. */
function paintScopeToggles() {
    $("#filterScope").querySelectorAll("button[data-scope-toggle]").forEach((b) => {
        b.setAttribute("aria-pressed", String(chosenRawScopes.has(b.dataset.scopeToggle)));
    });
}

/**
 * Draw the status card strip: every status, not only the reviewable ones.
 *
 * The leading card is "All" rather than "To review": this screen holds the whole
 * taxonomy now, and pressing it is the deliberate choice to fetch every status.
 * Built here rather than by `main.js`, which has no business knowing what this
 * strip contains.
 */
export function renderDetailCards() {
    renderStatCards({
        container: "#statsRow",
        statuses: getStatuses(),
        totalLabel: "All",
        totalId: "statTotal",
        idPrefix: "stat-",
        inert: [{ label: "Files", id: "statFiles" }],
    });
    paintResultToggles();
}

/** Reflect `chosenStatuses` onto the toggles and the cards. */
function paintResultToggles() {
    $("#filterResult").querySelectorAll("button[data-status]").forEach((b) => {
        b.setAttribute("aria-pressed", String(chosenStatuses.has(b.dataset.status)));
    });
    // The cards show the same state. "All" is pressed when every status is
    // chosen; a status card is pressed only when it is the *sole* choice,
    // because the toggles can express a combination the single-pick row cannot.
    const all = getStatuses().length > 0 && chosenStatuses.size === getStatuses().length;
    $("#statsRow").querySelectorAll("button[data-status-card]").forEach((b) => {
        const key = b.dataset.statusCard;
        const on = key
            ? chosenStatuses.size === 1 && chosenStatuses.has(key)
            : all;
        b.setAttribute("aria-pressed", String(on));
    });
}

/**
 * Draw the scope pills: All, then one per group with the cases it holds.
 *
 * Counted from the summary rows, so a group is offered — and its size is known
 * — before any of its cases have been fetched. A group the plan excludes is
 * drawn `chip-card--aside`, the pill form of the dashed rule its Summary table
 * carries, and starts unpressed: adding work nobody committed to is a choice
 * somebody makes, not a default.
 *
 * **All is a shortcut, not a mode.** The groups stay multi-select — several
 * pressed at once is the normal question here — and All simply presses every
 * one of them, reading as pressed only when they all are. That is the
 * convention the status cards above already use, and it is why All has no
 * "off": unpressing everything would empty the table, and a control whose only
 * effect is to show nothing is not one worth offering. Its figure is the sum of
 * the rest, so the row adds up to what pressing it would list.
 */
export function renderScopeCards() {
    const counts = countsByScope();
    const total = scopeGroups.reduce((n, g) => n + (counts[g.key] || 0), 0);
    const pill = (key, label, value, cls = "") =>
        `<button type="button" class="chip-card${cls}"`
        + ` data-scope-card="${esc(key)}" aria-pressed="false">`
        + `<span class="chip-card-label">${esc(label)}</span>`
        + `<span class="chip-card-value num">${value.toLocaleString()}</span></button>`;

    // All carries the empty key, the way the status strip's leading card does.
    $("#detailScopes").innerHTML = pill("", "All", total)
        + scopeGroups.map((g) => pill(g.key, g.label, counts[g.key] || 0,
                                      g.counted === false ? " chip-card--aside" : "")).join("");
    paintScopeCards();
}

/** Every case of every status, per scope group, from the summary rows. */
function countsByScope() {
    const counts = {};
    scopeGroups.forEach((g) => {
        const totals = sumRows(summaryRows.filter((r) => r.scope === g.key));
        // Every status, not `total`: an excluded status is a case this screen
        // can list, and a card that would not count it is a card that lies
        // about how many rows pressing it adds.
        counts[g.key] = getStatuses().reduce((n, s) => n + (totals[s.key] || 0), 0);
    });
    return counts;
}

/** Reflect `chosenScopes` onto the cards, and say what they add up to. */
function paintScopeCards() {
    // All is pressed only when every group is, so it reports the selection
    // rather than claiming one: with three of four pressed it is a shortcut
    // still worth offering, not a description of what is on screen.
    const all = scopeGroups.length > 0 && chosenScopes.size === scopeGroups.length;
    $("#detailScopes").querySelectorAll("button[data-scope-card]").forEach((b) => {
        const key = b.dataset.scopeCard;
        b.setAttribute("aria-pressed", String(key ? chosenScopes.has(key) : all));
    });

    const chosen = scopeGroups.filter((g) => chosenScopes.has(g.key));
    const counts = countsByScope();
    const total = chosen.reduce((n, g) => n + (counts[g.key] || 0), 0);
    // Naming all four when all four are pressed restates the row above it, and
    // grows with the config; the pills are already the list.
    const named = all ? "All scopes" : chosen.map((g) => g.label).join(" + ");
    $("#detailScopeSummary").textContent = chosen.length
        ? `${total.toLocaleString()} cases · ${named}`
        : "No scope selected";
}

/**
 * Build the detail header and make it sortable.
 *
 * Generated rather than written into the template so the sort buttons and their
 * `aria-sort` targets are built the same way as every other table's.
 */
export function renderDetailHead() {
    $("#detailHead").innerHTML = COLUMNS.map((c) => c.col
        ? sortableTh(c.col, c.label, { cls: c.cls || "" })
        : `<th${c.cls ? ` class="${c.cls}"` : ""}>${esc(c.label)}</th>`).join("");
    makeSortable("#detailHead th.sortable", detailSort, () => { currentPage = 1; applyFilters(); });
    paintSortIndicators("#detailHead th.sortable", detailSort);
}

/** The active grouping keys, from the toolbar control. */
function groupBy() {
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
function applyFilters() {
    const values = Object.fromEntries(
        [...FILTERS, ...DATE_FILTERS].map(({ id }) => [id, $("#" + id).value]));
    const q = $("#filterSearch").value.trim().toLowerCase();

    filtered = allData.filter((d) => {
        for (const { id, field } of FILTERS) {
            if (values[id] && d[field] !== values[id]) return false;
        }
        // Empty means every scope, so an unpressed strip narrows nothing.
        if (chosenRawScopes.size && !chosenRawScopes.has(d.scope)) return false;
        if (conditions.deviceFamily && d.device_family !== conditions.deviceFamily) return false;
        if (conditions.sheet && d.sheet !== conditions.sheet) return false;
        const from = values.filterDateFrom;
        const to = values.filterDateTo;
        if (from && (!d.test_date || d.test_date < from)) return false;
        if (to && (!d.test_date || d.test_date > to)) return false;
        if (q && !matchesSearch(d, q)) return false;
        if (missingOnly && !lacksReason(d)) return false;
        return true;
    });

    const keys = groupBy();
    const numeric = new Set(["row_num"]);
    filtered = keys.length
        ? sortGrouped(filtered, keys, detailSort, numeric, null)
        : sortRows(filtered, detailSort, numeric);

    renderStats();
    renderChips();
    renderTable();
    renderCharts(filtered);
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

/**
 * Update the stat figures and the "n / m cases" count.
 *
 * The status figures are counted over the **summary rows** of the pressed scope
 * groups, not over the cases: a status nobody has clicked has no cases here, and
 * a card reading 0 for it would be reporting the absence of a fetch as an
 * absence of work. What a card says is therefore how many cases pressing it
 * would list — which is what a control has to say to be worth pressing — and it
 * does not move when a File or a search narrows the table beneath it.
 */
function renderStats() {
    const totals = sumRows(summaryRows.filter((r) => chosenScopes.has(r.scope)));

    const setStat = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = Number(value || 0).toLocaleString();
    };
    // Every status, including the excluded ones: this screen lists them, so
    // "All" has to count them. That makes this figure legitimately larger than
    // Summary's Total, which is the plan.
    setStat("statTotal", getStatuses().reduce((n, s) => n + (totals[s.key] || 0), 0));
    getStatuses().forEach((s) => setStat(`stat-${s.key}`, totals[s.key] || 0));
    // Files is a fact about what you are looking at, not about what you could
    // pick, so it alone counts the rows actually on screen.
    setStat("statFiles", new Set(filtered.map((d) => d.file_name)).size);

    $("#filteredCount").textContent = filtered.length === allData.length
        ? `${filtered.length.toLocaleString()} cases`
        : `${filtered.length.toLocaleString()} / ${allData.length.toLocaleString()} cases`;

    // How many conditions are folded away, on the button that folds them —
    // otherwise a closed panel hides the fact that the table is narrowed.
    const narrowing = FILTERS.filter(({ id }) => $("#" + id).value).length
        + DATE_FILTERS.filter(({ id }) => $("#" + id).value).length
        // However many scopes are pressed, they are one narrowing.
        + (chosenRawScopes.size ? 1 : 0)
        + (conditions.deviceFamily ? 1 : 0)
        + (conditions.sheet ? 1 : 0)
        + (missingOnly ? 1 : 0)
        + ($("#detailGroupBy").value ? 1 : 0);
    $("#filterCount").textContent = narrowing ? String(narrowing) : "";
}

/**
 * One dismissible chip per active narrowing.
 *
 * A select showing "iPhone 15" does not say *which* dimension it narrows once
 * you have looked away, and the date bounds are easy to forget entirely. The
 * two conditions a drill-in can set have no control of their own, so a chip is
 * the only way to see — or undo — them.
 *
 * Status chips appear only when the choice is a strict subset: with every status
 * pressed they would be a row of eight chips saying nothing is narrowed.
 */
function renderChips() {
    const chips = [];
    const push = (id, label, value) => {
        if (value) chips.push(`<span class="chip">${esc(label)}: ${esc(value)}`
            + `<button type="button" data-clear="${esc(id)}" aria-label="Clear ${esc(label)} filter">✕</button></span>`);
    };
    FILTERS.forEach(({ id, label }) => push(id, label, $("#" + id).value));
    // One chip per pressed scope rather than one listing them all, for the
    // reason the statuses get one each: any single one can then be dropped
    // without retyping the rest.
    [...chosenRawScopes].forEach((v) => chips.push(
        `<span class="chip">Scope: ${esc(v)}`
        + `<button type="button" data-scope-toggle="${esc(v)}"`
        + ` aria-label="Clear ${esc(v)} filter">✕</button></span>`));
    if (chosenStatuses.size < getStatuses().length) {
        // One chip per chosen status rather than one listing them all, so any
        // single one can be dropped without retyping the rest.
        getStatuses()
            .filter((st) => chosenStatuses.has(st.key))
            .forEach((st) => chips.push(
                `<span class="chip">Result: ${esc(st.label)}`
                + `<button type="button" data-status="${esc(st.key)}"`
                + ` aria-label="Clear ${esc(st.label)} filter">✕</button></span>`));
    }
    if (conditions.deviceFamily) {
        chips.push(`<span class="chip">Device type: ${esc(conditions.deviceFamily)}`
            + `<button type="button" data-condition="deviceFamily"`
            + ` aria-label="Clear Device type filter">✕</button></span>`);
    }
    if (conditions.sheet) {
        chips.push(`<span class="chip">Sheet: ${esc(conditions.sheet)}`
            + `<button type="button" data-condition="sheet"`
            + ` aria-label="Clear Sheet filter">✕</button></span>`);
    }
    DATE_FILTERS.forEach(({ id, label }) => push(id, label, $("#" + id).value));
    push("filterSearch", "Search", $("#filterSearch").value.trim());
    if (missingOnly) {
        chips.push(`<span class="chip">Missing reason`
            + `<button type="button" data-missing="1"`
            + ` aria-label="Clear Missing reason filter">✕</button></span>`);
    }

    $("#detailChips").innerHTML = chips.join("");
    $("#detailChips").querySelectorAll("button[data-missing]").forEach((b) =>
        b.addEventListener("click", () => {
            missingOnly = false;
            paintMissingReason();
            currentPage = 1;
            applyFilters();
        }));
    $("#detailChips").querySelectorAll("button[data-condition]").forEach((b) =>
        b.addEventListener("click", () => {
            conditions[b.dataset.condition] = "";
            currentPage = 1;
            applyFilters();
        }));
    $("#detailChips").querySelectorAll("button[data-clear]").forEach((b) =>
        b.addEventListener("click", () => {
            $("#" + b.dataset.clear).value = "";
            currentPage = 1;
            applyFilters();
        }));
    $("#detailChips").querySelectorAll("button[data-scope-toggle]").forEach((b) =>
        b.addEventListener("click", () => {
            chosenRawScopes.delete(b.dataset.scopeToggle);
            paintScopeToggles();
            // A narrowing, not a selection: nothing has to be fetched or rebuilt.
            currentPage = 1;
            applyFilters();
        }));
    $("#detailChips").querySelectorAll("button[data-status]").forEach((b) =>
        b.addEventListener("click", () => {
            chosenStatuses.delete(b.dataset.status);
            paintResultToggles();
            // Dropping a status needs no fetch — the others are already here.
            rebuild();
        }));
}

/**
 * Whether a row is a section heading inside the spreadsheet rather than a case.
 *
 * These carry a title in the Case no column — "[Login - normal case]" — and
 * nothing else. Scope being empty is what marks them, but that alone would also
 * excuse a real case whose Scope was genuinely forgotten, so it is paired with
 * "nothing has been recorded against this row". Flagging headings as errors
 * trains people to ignore the flag.
 *
 * @param {Object} d A case row.
 * @returns {boolean}
 */
function isSectionHeader(d) {
    return !d.scope && !d.result && !d.test_date && !d.pic;
}

/**
 * Bootstrap-free class flagging a cell that should have been filled in.
 *
 * Three different rules apply:
 * - identity fields are always mandatory;
 * - result/date/PIC are only expected once *any* of the three is filled, so an
 *   untested case is not flagged, but a half-recorded one is — unless the case
 *   is out of the plan, where the blank is the whole point rather than an
 *   omission (an Out Of Scope case is precisely one that names no PIC, so
 *   flagging that cell would mark every one of them as a mistake);
 * - ticket id and note are required together (either satisfies) for the
 *   statuses the config marks as needing a reason.
 *
 * @param {Object} d A case row.
 * @param {string} field
 * @returns {string} `"flag"` or an empty string.
 */
function cellCls(d, field) {
    if (isSectionHeader(d)) return "";
    const v = d[field];
    if (["case_no", "file_name", "sheet", "device", "scope"].includes(field)) {
        return v ? "" : "flag";
    }
    if (["result", "test_date", "pic"].includes(field)) {
        if (isExcluded(d.status)) return "";
        const has = [d.result, d.test_date, d.pic].filter(Boolean).length;
        return has > 0 && !v ? "flag" : "";
    }
    if (field === "ticket_id" || field === "note") {
        return lacksReason(d) ? "flag" : "";
    }
    return "";
}

/**
 * One `<td>` for a field, carrying its validation highlight.
 *
 * A clipped cell also gets the full value as its tooltip — truncation must not
 * be the same thing as losing the text.
 *
 * @param {Object} d
 * @param {string} field
 * @param {string} [extra] Extra classes.
 * @returns {string} HTML.
 */
function td(d, field, extra = "") {
    const cls = [cellCls(d, field), extra].filter(Boolean).join(" ");
    const value = esc(d[field]);
    const title = extra.includes("clip") && value ? ` title="${value}"` : "";
    return `<td${cls ? ` class="${cls}"` : ""}${title}>${value}</td>`;
}

/** Every cell of one case row. */
function caseCells(d, i) {
    return `<td class="num muted">${i + 1}</td>`
        + td(d, "file_name")
        + td(d, "sheet")
        + td(d, "device")
        + `<td class="num">${d.row_num}</td>`
        + td(d, "case_no", "mono clip clip-sm")
        + td(d, "scope")
        + `<td class="${cellCls(d, "result")}">`
        + `<span class="badge" data-tone="${esc(toneFor(d.status))}">${esc(d.result)}</span></td>`
        + td(d, "test_date", "mono")
        + td(d, "pic")
        + td(d, "ticket_id", "mono")
        + td(d, "note", "clip");
}

/**
 * What the table says when it has no rows to draw.
 *
 * Three different states look identical otherwise, and only one of them is
 * "there is nothing here": cases are still on their way, no status is chosen so
 * nothing was ever asked for, or the filters match nothing.
 *
 * @returns {string}
 */
function emptyMessage() {
    if (loading) return "Loading cases…";
    if (!chosenStatuses.size) return "Pick a status above to list its cases.";
    if (!chosenScopes.size) return "Pick a scope above to list its cases.";
    return "No cases match these filters.";
}

/** The distinct top-level group values, in their sorted order. */
function groupValues(keys) {
    const seen = [];
    filtered.forEach((r) => {
        const v = String(r[keys[0]] ?? "");
        if (!seen.includes(v)) seen.push(v);
    });
    return seen;
}

/** Draw the current page, grouped or flat, plus its pager. */
function renderTable() {
    const keys = groupBy();

    // Mid-fetch the rows on screen belong to the previous selection, so they are
    // cleared rather than left to look like the answer. `aria-busy` says so to a
    // screen reader, which a message in a table cell does not.
    $("#dataBody").closest("table").setAttribute("aria-busy", String(loading));
    if (loading) {
        renderGroupedTable({
            container: "#dataBody",
            rows: [],
            totalCols: COLUMNS.length,
            expanded,
            renderLabelCells: () => "",
            labelCols: 0,
            renderValues: () => "",
            onToggle: () => {},
            emptyMessage: emptyMessage(),
        });
        $("#detailFooter").innerHTML = "";
        return;
    }

    if (!keys.length) {
        const start = showAll ? 0 : (currentPage - 1) * PAGE_SIZE;
        renderGroupedTable({
            container: "#dataBody",
            rows: showAll ? filtered : filtered.slice(start, start + PAGE_SIZE),
            totalCols: COLUMNS.length,
            expanded,
            renderLabelCells: () => "",
            labelCols: 0,
            renderValues: (d, i) => caseCells(d, start + i),
            onToggle: () => {},
            emptyMessage: emptyMessage(),
        });
        renderPageFooter({
            container: "#detailFooter",
            totalItems: filtered.length,
            pageSize: PAGE_SIZE,
            currentPage,
            showAll,
            unit: "case",
            onPageChange: (page) => { currentPage = page; renderTable(); },
            onToggleAll: (all) => { showAll = all; currentPage = 1; renderTable(); },
        });
        return;
    }

    const values = groupValues(keys);
    const start = (currentPage - 1) * GROUP_PAGE_SIZE;
    const visible = new Set(showAll ? values : values.slice(start, start + GROUP_PAGE_SIZE));
    const rows = filtered.filter((r) => visible.has(String(r[keys[0]] ?? "")));

    renderGroupedTable({
        container: "#dataBody",
        rows,
        groupBy: keys,
        mode: "span",
        summarise: (g) => `${g.length} case${g.length === 1 ? "" : "s"}`,
        totalCols: COLUMNS.length,
        expanded,
        defaultExpanded: DEFAULT_EXPANDED,
        renderLabelCells: () => "",
        labelCols: 0,
        renderValues: (d, i) => caseCells(d, i),
        onToggle: (path) => {
            toggleGroup(expanded, path, DEFAULT_EXPANDED);
            renderTable();
        },
        emptyMessage: emptyMessage(),
    });

    renderPageFooter({
        container: "#detailFooter",
        totalItems: values.length,
        pageSize: GROUP_PAGE_SIZE,
        currentPage,
        showAll,
        // Paging counts **groups** wherever grouping is on: a page that split a
        // group would make its roll-up a lie, and so would a count of rows.
        unit: "group",
        onPageChange: (page) => { currentPage = page; renderTable(); },
        onToggleAll: (all) => { showAll = all; currentPage = 1; renderTable(); },
    });
}
