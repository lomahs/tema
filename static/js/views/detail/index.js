/**
 * Detail view: the case list for the whole taxonomy, fetched a status at a time.
 *
 * This is where a status figure leads. Every number in a status band on Summary,
 * on the file page and on Daily is a button, and pressing it opens this screen
 * showing exactly the cases behind it — an OK and a Not Yet Started as readily
 * as an NG. That is what it stopped being "Review", which held only the statuses
 * `config/result_status.json` marks `"review": true`; that restriction survives
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
import { $ } from "../../dom.js";
import { getCases } from "../../api.js";
import { renderCharts, resizeCharts } from "../../charts.js";
import { populateSelect, uniqueOf } from "../../filters.js";
import {
    getReasonStatuses, getReviewStatuses, getStatuses, sumRows,
} from "../../taxonomy.js";
import { applyFilters, clearNarrowing, defaultScopes, setOnCleared } from "./filters.js";
import {
    paintMissingReason, paintResultToggles, paintScopeCards, paintScopeToggles,
    renderChips, renderScopeCards, renderScopeToggles, renderStats, renderTable,
    setOnChanged, setOnReload,
} from "./render.js";
import {
    FILTERS, DATE_FILTERS, cache, chosenRawScopes, chosenScopes, chosenStatuses,
    expanded, getAllData, getFiltered, getLoadToken, getPending, getScopeGroups,
    getStale, getSummaryRows, nextLoadToken, setAllData, setConditions,
    setCurrentPage, setFiltered, setLoading, setMissingOnly, getMissingOnly,
    setPending, setScopeGroups, setShowAll, setStale, setSummaryRows,
} from "./state.js";

/**
 * One narrowing pass and the four redraws that follow it.
 *
 * This is the tail `applyFilters` used to carry. It lives here because it is
 * the only place that legitimately knows about both halves.
 */
function refresh() {
    applyFilters();
    renderStats();
    renderChips();
    renderTable();
    renderCharts(getFiltered());
}

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
    setOnChanged(refresh);
    setOnReload(rebuild);
    setOnCleared(() => { paintScopeToggles(); paintMissingReason(); });

    const rerender = () => { setCurrentPage(1); refresh(); };

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
            getScopeGroups().forEach((g) => chosenScopes.add(g.key));
        } else if (chosenScopes.has(key)) {
            chosenScopes.delete(key);
        } else {
            chosenScopes.add(key);
        }
        paintScopeCards();
        setCurrentPage(1);
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
        setMissingOnly(!getMissingOnly());
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
    setShowAll(false);
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
    setMissingOnly(true);
    paintMissingReason();
    paintResultToggles();
    setShowAll(false);
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
        .filter((k) => getScopeGroups().some((g) => g.key === k));
    if (asked.length) {
        chosenScopes.clear();
        asked.forEach((k) => chosenScopes.add(k));
    } else {
        defaultScopes();
    }
    paintScopeCards();
    paintResultToggles();

    setConditions({ deviceFamily: ctx.deviceFamily || "", sheet: ctx.sheet || "" });
    // The selects are filled from the cases, so these wait for them to arrive.
    setPending({ file: ctx.file, device: ctx.device, pic: ctx.pic, date: ctx.date });

    setShowAll(false);
    setCurrentPage(1);
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
    setStale(false);
    setCurrentPage(1);
    const missing = [...chosenStatuses].filter((key) => !cache.has(key));
    if (!missing.length) { rebuild(); return; }

    const token = nextLoadToken();
    setLoading(true);
    renderTable();

    const answers = await Promise.all(
        missing.map(async (key) => [key, await getCases(key)]));
    if (token !== getLoadToken()) return;   // a later click is the current answer

    answers.forEach(([key, { ok, json }]) => {
        if (ok) cache.set(key, json);
        else chosenStatuses.delete(key);
    });
    setLoading(false);
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
    setAllData([]);
    getStatuses().forEach((s) => {
        if (!chosenStatuses.has(s.key)) return;
        (cache.get(s.key) || []).forEach((d) => {
            if (chosenScopes.has(d.scope_group)) getAllData().push(d);
        });
    });

    expanded.clear();
    FILTERS.forEach(({ id, field }) => populateSelect("#" + id, uniqueOf(getAllData(), field)));
    renderScopeToggles();

    if (getPending()) {
        // The row clicked is made of these cases, so its file, device and PIC
        // are options by now.
        if (getPending().file) $("#filterFile").value = getPending().file;
        if (getPending().device) $("#filterDevice").value = getPending().device;
        if (getPending().pic) $("#filterPIC").value = getPending().pic;
        if (getPending().date) {
            $("#filterDateFrom").value = getPending().date;
            $("#filterDateTo").value = getPending().date;
        }
        setPending(null);
    }

    refresh();
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
    const counted = new Set(getScopeGroups().filter((g) => g.counted !== false).map((g) => g.key));
    const totals = sumRows(getSummaryRows().filter((r) => counted.has(r.scope)));
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
    setSummaryRows(summary.groups || []);
    setScopeGroups(summary.scopes || []);
    cache.clear();
    setAllData([]);
    setFiltered([]);
    setStale(true);

    // A status or a group can disappear in Config while this screen is open.
    const keys = new Set(getStatuses().map((s) => s.key));
    [...chosenStatuses].forEach((k) => { if (!keys.has(k)) chosenStatuses.delete(k); });
    if (!chosenStatuses.size) getReviewStatuses().forEach((s) => chosenStatuses.add(s.key));
    const groups = new Set(getScopeGroups().map((g) => g.key));
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
    if (getStale()) loadChosen();
}

export {
    renderDetailCards, renderDetailHead, renderResultToggles, renderScopeCards,
} from "./render.js";
