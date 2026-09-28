/**
 * The Member tab: the only module `main.js` imports from `views/member/`.
 *
 * Owns the refresh cycle and the week on screen. The tab is four requests
 * rather than one, because they are wanted at different times: productivity,
 * the totals and the week list whenever the load or the plan changes, and one
 * week's cells each time the reader pages — so paging costs one small request
 * and the phase totals are never refetched for it.
 *
 * It refreshes on its own `onPlanChange` subscription as well as when `main.js`
 * asks after a load. Those two arrive together on every load (`refreshViews`
 * sets the plan calendar too), so a refresh already running absorbs the second
 * request and runs once more afterwards rather than twice at once.
 */
import { $ } from "../../dom.js";
import {
    getMemberProductivity, getMemberTotals, getMemberWeek, getMemberWeeks,
} from "../../api.js";
import { onPlanChange } from "../../plan.js";
import { initMatrix, renderMatrix } from "./matrix.js";
import { renderProductivityHead, setProductivity } from "./productivity.js";

export { renderProductivityHead as renderMemberHead };

/** @type {Object|null} `/api/member/totals` body */
let totals = null;
/** @type {Object[]} `/api/member/weeks` → `weeks` */
let weeks = [];
/** Index of the week holding today. */
let current = 0;
/** The Monday on screen, kept across refreshes so a plan save does not page away. */
let viewing = null;

/** @type {?Promise<void>} */
let running = null;
let again = false;

/**
 * Wire the view. Call once, at startup.
 */
export function initMemberView() {
    initMatrix({ onPage: showWeek });
    onPlanChange(refreshMember);
}

/**
 * Refetch everything the tab draws.
 *
 * @returns {Promise<void>}
 */
export function refreshMember() {
    if (running) {
        again = true;
        return running;
    }
    running = (async () => {
        do {
            again = false;
            await load();
        } while (again);
    })().finally(() => { running = null; });
    return running;
}

function fail(message) {
    const el = $("#memberMatrixError");
    el.textContent = message || "";
    el.hidden = !message;
}

async function load() {
    const [prod, tot, wk] = await Promise.all([
        getMemberProductivity(), getMemberTotals(), getMemberWeeks(),
    ]);
    if (prod.ok) setProductivity(prod.json);
    if (!tot.ok || !wk.ok) {
        fail((tot.json && tot.json.error) || (wk.json && wk.json.error)
             || "The member figures could not be read.");
        return;
    }
    fail("");
    totals = tot.json;
    weeks = wk.json.weeks;
    current = wk.json.current;
    const kept = viewing ? weeks.findIndex((w) => w.start === viewing) : -1;
    await showWeek(kept >= 0 ? kept : current);
}

/**
 * Fetch one week's cells and draw the matrix around them.
 * @param {number} index Into `weeks`.
 */
async function showWeek(index) {
    if (!totals) return;
    if (!weeks.length) {
        renderMatrix({ totals, weeks, index: 0, current, week: null });
        return;
    }
    const i = Math.max(0, Math.min(index, weeks.length - 1));
    const res = await getMemberWeek(weeks[i].start);
    if (!res.ok) {
        fail(res.json.error || "That week could not be read.");
        return;
    }
    fail("");
    viewing = weeks[i].start;
    renderMatrix({ totals, weeks, index: i, current, week: res.json });
}
