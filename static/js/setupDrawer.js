/**
 * The setup drawer and the source summary in the top bar.
 *
 * Choosing where data comes from and where the report goes is something you do
 * once a session, so it lives behind a button rather than above every view. The
 * drawer opens itself when there is nothing loaded — an empty app should show
 * you the way in — and puts itself away once a load succeeds.
 *
 * Owns only chrome. `sourcePanel.js` still owns where the data comes from and
 * `reportPanel.js` still owns where results go; neither knows this exists.
 */
import { $ } from "./dom.js";

let drawer, scrim, openers, closer;

/** What had focus before the drawer opened, so it can be handed back. */
let lastFocus = null;

/** Whether the drawer is showing. */
function isOpen() {
    return !drawer.hidden;
}

/** Show the drawer and move focus into it. */
function openDrawer() {
    lastFocus = document.activeElement;
    drawer.hidden = false;
    scrim.hidden = false;
    const first = drawer.querySelector("input, select, textarea, button");
    if (first) first.focus();
}

/** Hide the drawer and return focus to whatever opened it. */
export function closeDrawer() {
    drawer.hidden = true;
    scrim.hidden = true;
    if (lastFocus && lastFocus.isConnected) lastFocus.focus();
}

/**
 * Report what is currently loaded, in the top bar.
 *
 * Written as a sentence rather than a row of dot-joined fragments — it is read
 * at a glance by someone who wants to know whether they are looking at today's
 * data.
 *
 * @param {?{loaded: number, file_count: number}} json An API load response, or
 *   `null` to clear the summary.
 */
export function setSourceSummary(json) {
    const el = $("#sourceSummary");
    if (!json) { el.textContent = ""; return; }
    const files = `${json.file_count} file${json.file_count === 1 ? "" : "s"}`;
    el.textContent = `${files} loaded, ${json.loaded.toLocaleString()} cases`;
}

/** Wire the drawer. Call once, at startup. */
export function initSetupDrawer() {
    drawer = $("#setupDrawer");
    scrim = $("#drawerScrim");
    closer = $("#btnCloseDrawer");
    openers = [$("#btnSetup"), $("#btnEmptySetup")];

    openers.forEach((b) => b.addEventListener("click", openDrawer));
    closer.addEventListener("click", closeDrawer);
    scrim.addEventListener("click", closeDrawer);

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && isOpen()) closeDrawer();
    });

    // Nothing is loaded yet, so the only useful thing to do is choose a source.
    openDrawer();
}
