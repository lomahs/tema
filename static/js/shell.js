/**
 * The rail: navigation, what is loaded, and the page heading.
 *
 * This replaces the setup drawer. Setup used to be a thing you pulled over the
 * app and pushed away again; it is a view now, which means there is no longer a
 * surface that covers the data, and no open/closed state for anything to get
 * out of step with.
 *
 * Owns only chrome. `sourcePanel.js` still owns where the data comes from,
 * `reportPanel.js` where results go and `preparePanel.js` what gets written
 * back to the workbooks; none of the three knows this exists. It does not know
 * what a view contains either — `main.js` hands it a callback and it reports
 * clicks back through that.
 */
import { $, $$ } from "./dom.js";

/** Called with a view name when a nav item is pressed. */
let onNavigate = () => {};

/** Collapse the rail to its icon width, and back. */
function setRailOpen(open) {
    $("#rail").classList.toggle("is-closed", !open);
    // Chart.js measures its container, and the main column just changed width.
    window.dispatchEvent(new Event("resize"));
}

/**
 * Light up the nav item for the view now showing.
 * @param {string} view
 */
export function setActiveView(view) {
    $$("#viewNav .rail-nav-item").forEach((b) =>
        b.setAttribute("aria-current", String(b.dataset.view === view)));
}

/**
 * Views that can answer something with nothing loaded, and so are never
 * disabled: Tools is where you load, and Config edits files on disk.
 */
const ALWAYS_ENABLED = new Set(["tools", "config"]);

/**
 * Let the four data views be reached. They stay disabled until a load has
 * succeeded, because every one of them would otherwise open on nothing.
 *
 * @param {boolean} enabled
 */
export function setNavEnabled(enabled) {
    $$("#viewNav .rail-nav-item").forEach((b) => {
        if (!ALWAYS_ENABLED.has(b.dataset.view)) b.disabled = !enabled;
    });
}

/**
 * The two counts carried in the nav itself.
 *
 * They are the same two figures Summary and Review lead with, put where they
 * are visible from any view — the point of the rail carrying them at all.
 *
 * @param {{total: number, review: number}} counts
 */
export function setNavCounts({ total, review }) {
    $("#navCountTotal").textContent = total ? total.toLocaleString() : "";
    $("#navCountReview").textContent = review ? review.toLocaleString() : "";
}

/**
 * Report what is currently loaded, in the rail.
 *
 * Two lines rather than one sentence: the case count is the figure someone
 * checks at a glance, and the file count is the context for it.
 *
 * @param {?{loaded: number, file_count: number}} json An API load response, or
 *   `null` to clear the card.
 */
export function setSourceSummary(json) {
    const card = $("#sourceCard");
    if (!json) { card.hidden = true; return; }
    card.hidden = false;
    $("#sourceFigure").textContent = json.loaded.toLocaleString();
    $("#sourceSummary").textContent =
        `cases · ${json.file_count} file${json.file_count === 1 ? "" : "s"}`;
}

/**
 * Set the heading above whichever view is showing.
 *
 * @param {string} title
 * @param {string} sub One sentence on what this view counts. Views whose scope
 *   differs from the obvious one — Productivity ignores Daily's filters, Review
 *   holds only open work — are the reason this line exists.
 */
export function setPageHead(title, sub) {
    $("#pageTitle").textContent = title;
    $("#pageSub").textContent = sub;
}

/**
 * Wire the rail. Call once, at startup.
 * @param {{onNavigate: (view: string) => void}} opts
 */
export function initShell(opts) {
    onNavigate = opts.onNavigate;

    $("#btnRailClose").addEventListener("click", () => setRailOpen(false));
    $("#btnRailOpen").addEventListener("click", () => setRailOpen(true));

    // One listener on the nav rather than one per item: nothing here is
    // regenerated, but the count spans inside each button are, and a click on a
    // count is still a click on its item.
    $("#viewNav").addEventListener("click", (e) => {
        const item = e.target.closest(".rail-nav-item");
        if (item && !item.disabled) onNavigate(item.dataset.view);
    });
}
