/**
 * Entry point: wires the modules together and owns the tab switching.
 *
 * Loaded as `<script type="module">`, so it runs deferred — the DOM is fully
 * parsed and the Chart.js global is available before anything here executes.
 */
import { $, $$ } from "./dom.js";
import { fetchAll } from "./api.js";
import { refreshChartTheme, resizeCharts } from "./charts.js";
import { initTheme, onThemeChange } from "./theme.js";
import { closeDrawer, initSetupDrawer, setSourceSummary } from "./setupDrawer.js";
import { initSourcePanel } from "./sourcePanel.js";
import { initReportPanel, setReportEnabled } from "./reportPanel.js";
import { renderStatCards, setTaxonomy } from "./taxonomy.js";
import { initSummaryView, renderSummary, renderSummaryHead } from "./views/summary.js";
import { initDaily, initDailyView, renderDailyHead } from "./views/daily.js";
import { initProductivity, renderProductivityHead } from "./views/productivity.js";
import { initDetail, initDetailView, renderDetailHead, showCase } from "./views/detail.js";

const VIEWS = ["summary", "daily", "detail"];

/**
 * Show one of the three views and hide the others.
 * @param {"summary"|"daily"|"detail"} view
 */
function showView(view) {
    VIEWS.forEach((v) => { $(`#${v}View`).hidden = v !== view; });
    $$("#viewTabs .tab").forEach((t) =>
        t.setAttribute("aria-selected", String(t.dataset.view === view)));
    // Chart.js sizes to the container, which is 0x0 while the tab is hidden.
    if (view === "detail") resizeCharts();
}

/** Wire the Summary / Daily / Detail tabs. */
function initViewTabs() {
    $$("#viewTabs .tab").forEach((tab) =>
        tab.addEventListener("click", () => showView(tab.dataset.view)));
}

/**
 * Pull every endpoint and redraw all three views.
 *
 * Order matters: the taxonomy defines the status columns, so it is applied
 * before the stat cards and the four generated table headers, and the headers
 * are built before the bodies that fill them.
 *
 * @param {Object} loadResult The `/api/load` or `/api/reload` response.
 */
async function refreshViews(loadResult) {
    const { taxonomy, cases, summary, daily, productivity } = await fetchAll();

    setTaxonomy(taxonomy);
    renderStatCards();
    renderSummaryHead();
    renderDailyHead();
    renderProductivityHead();
    renderDetailHead();

    initDetail(cases);
    renderSummary(summary);
    initDaily(daily);
    initProductivity(productivity);

    // There is something to publish now.
    setReportEnabled(true);

    setSourceSummary(loadResult);
    $("#emptyState").hidden = true;
    $("#viewTabs").hidden = false;
    showView("summary");
    closeDrawer();
}

/**
 * Open one case in the detail view.
 *
 * Passed to the summary view as a callback rather than imported by it, so
 * `views/summary.js` keeps knowing nothing about `views/detail.js`.
 *
 * @param {Object} c A missing-reason case.
 */
function jumpToCase(c) {
    showView("detail");
    showCase(c);
}

initTheme();
onThemeChange(refreshChartTheme);
initSetupDrawer();
initSourcePanel({ onLoaded: refreshViews });
initReportPanel();
initSummaryView({ onJumpToCase: jumpToCase });
initDetailView();
initDailyView();
initViewTabs();
