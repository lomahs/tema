/**
 * Entry point: wires the modules together and owns which view is showing.
 *
 * Loaded as `<script type="module">`, so it runs deferred — the DOM is fully
 * parsed and the Chart.js global is available before anything here executes.
 */
import { $ } from "./dom.js";
import { fetchAll, postReload } from "./api.js";
import { refreshChartTheme, resizeCharts } from "./charts.js";
import { initTheme, onThemeChange } from "./theme.js";
import {
    initShell, setActiveView, setNavCounts, setNavEnabled, setPageHead, setSourceSummary,
} from "./shell.js";
import { initSourcePanel } from "./sourcePanel.js";
import { initReportPanel, setReportEnabled } from "./reportPanel.js";
import { initPreparePanel, refreshPrepare, runFileAction } from "./preparePanel.js";
import { initFilesTable } from "./filesTable.js";
import { initConfigView } from "./views/config.js";
import { getReviewStatuses, renderStatCards, setTaxonomy } from "./taxonomy.js";
import { initSummaryView, renderSummary } from "./views/summary.js";
import { setJumpHandler } from "./views/summaryOverview.js";
import { initDaily, initDailyView, renderDailyHead } from "./views/daily.js";
import {
    initProductivity, initProductivityView, renderProductivityHead,
} from "./views/productivity.js";
import { initTarget } from "./target.js";
import {
    initDetail, initDetailView, renderDetailHead, renderResultToggles, reviewCount,
    showMissingReason,
} from "./views/detail.js";

/**
 * Every view, and the heading each carries.
 *
 * The subtitle is a function rather than a string because two of them are only
 * answerable once the taxonomy has loaded, and because both exist to correct a
 * reasonable wrong assumption: that Productivity answers to Daily's filters,
 * and that Review shows everything.
 */
const VIEWS = {
    summary: {
        title: "Summary",
        sub: () => "Every case loaded, one table per scope group.",
    },
    daily: {
        title: "Daily",
        sub: () => "Cases executed per day. Cases with no test date are not counted here.",
    },
    productivity: {
        title: "Productivity",
        sub: () => "Executed cases divided by the days that member actually tested. "
                 + "Covers everything loaded — Daily's filters do not apply.",
    },
    detail: {
        title: "Review",
        sub: () => {
            const names = getReviewStatuses().map((s) => s.label);
            return names.length
                ? `Open work only: ${names.join(", ")}. Everything else is left out of this view.`
                : "Open work only.";
        },
    },
    tools: {
        title: "Tools",
        sub: () => "Where the cases come from, what gets written back to the workbooks, "
                 + "and where the report goes.",
    },
    config: {
        title: "Config",
        sub: () => "The data files the rest of the app is driven by. Saving one applies it "
                 + "to the running app — no restart.",
    },
};

/**
 * The last `/api/load` response, or `null` while nothing is loaded.
 *
 * Held because a config save changes what every figure on screen *means* —
 * which statuses are columns, which scopes are tables — without anything having
 * been loaded again. Redrawing then needs the figures the rail is showing, and
 * they arrive only with a load.
 */
let lastLoad = null;

/**
 * Show one view and hide the others.
 * @param {keyof VIEWS} view
 */
function showView(view) {
    Object.keys(VIEWS).forEach((v) => { $(`#${v}View`).hidden = v !== view; });
    setActiveView(view);
    setPageHead(VIEWS[view].title, VIEWS[view].sub());
    // Back to the top. The rail is the only fixed thing on screen now, so a
    // view change that kept the scroll position landed the reader halfway down
    // a table they had not seen the head of.
    window.scrollTo({ top: 0 });
    // Chart.js sizes to the container, which is 0x0 while the view is hidden.
    if (view === "detail") resizeCharts();
}

/**
 * Pull every endpoint and redraw every view.
 *
 * Order matters: the taxonomy defines the status columns, so it is applied
 * before the stat cards and the generated table headers, and the headers are
 * built before the bodies that fill them. Summary is the exception — it draws
 * one table per scope group, so it cannot know its headers until it has the
 * data, and `renderSummary` builds both together.
 *
 * @param {Object} loadResult The `/api/load` or `/api/reload` response.
 * @param {{show?: boolean}} [opts] `show: false` leaves the current view in
 *   place — the prepare panel reloads from inside Tools, and throwing the user
 *   onto Summary mid-workflow would lose their place.
 */
async function refreshViews(loadResult, { show = true } = {}) {
    lastLoad = loadResult;
    const { taxonomy, cases, summary, daily, productivity } = await fetchAll();

    setTaxonomy(taxonomy);
    renderStatCards();
    renderDailyHead();
    renderProductivityHead();
    renderDetailHead();
    renderResultToggles();

    initDetail(cases);
    // Summary's overview reports the last day anyone tested, which lives in the
    // daily rows rather than the summary ones.
    renderSummary(summary, daily);
    initDaily(daily);
    initProductivity(productivity);

    // There is something to publish now.
    setReportEnabled(true);

    setSourceSummary(loadResult);
    setNavCounts({ total: loadResult.loaded, review: reviewCount() });
    setNavEnabled(true);

    if (show) showView("summary");

    // The prepare panel works from the loaded source's file list, so it only
    // has something to show once a load has succeeded.
    await refreshPrepare();
}

/**
 * Re-read the source after the prepare panel has written to the workbooks.
 *
 * Clearing a round's results is meant to empty the views, so this is not
 * optional bookkeeping — without it the screen would keep showing results that
 * are no longer in the files.
 */
async function reloadAfterPrepare() {
    const { ok, json } = await postReload();
    if (ok) await refreshViews(json, { show: false });
}

/**
 * Redraw after a config file was saved.
 *
 * The taxonomy decides what every status column counts and the scope groups
 * decide how many Summary tables there are, so both change the screen without
 * anything having been re-read from disk — the endpoints classify per request.
 * `show: false` keeps the user on Config, where they are still working.
 *
 * Nothing is redrawn when nothing is loaded: there would be nothing to redraw,
 * and `refreshViews` would turn the nav on over an empty app.
 */
async function refreshAfterConfigSave() {
    if (lastLoad) await refreshViews(lastLoad, { show: false });
}

initTheme();
initTarget();
onThemeChange(refreshChartTheme);
initShell({ onNavigate: showView });
// Summary's KPI cards navigate, but `views/summary.js` must not import
// `views/detail.js` to do it — this module owns the views, so the jump comes
// back through here instead, and it is also what translates a card's filter
// name into the call on whichever module owns that view's state.
setJumpHandler((view, filter) => {
    if (filter === "missing") showMissingReason();
    showView(view);
});
initSourcePanel({ onLoaded: refreshViews });
initReportPanel();
initPreparePanel({ onApplied: reloadAfterPrepare });
// The two Tools panels share one table of workbooks; it reports a pressed row
// button to whichever of them owns that action.
initFilesTable({ onAction: runFileAction });
initConfigView({ onSaved: refreshAfterConfigSave });
initDetailView();
initDailyView();
initSummaryView();
initProductivityView();

// Nothing is loaded yet, so the only view that can answer anything is Tools.
// It is the empty state now: a separate "nothing loaded" panel in front of the
// folder field said the same thing twice.
showView("tools");
