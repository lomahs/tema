/**
 * The plan, as the rest of the app reads it.
 *
 * This replaces `target.js`, and the replacement is a change of kind rather
 * than of storage. The target was one number — cases per person per day — that
 * every plan figure in the app was multiplied out of, kept in `localStorage`
 * because nothing on the server knew about it. A plan says what was actually
 * meant to happen on a given day, for named people on named files, so it lives
 * on the server and it differs per day.
 *
 * What is held here is the *calendar* — one line per day — and what it is for
 * is narrower than it was: whether anything is planned at all, and the
 * announcement that the plan changed. No figure is read off it any more. Every
 * plan-against-actual number is the server's, for the selection it is about:
 * Daily asks `/api/plan/daily` with its filters, the Member tab asks
 * `/api/member/*`, Planning asks for the phase and the board. A calendar total
 * divided in the browser is how a filtered Daily was measured against the
 * whole team's plan.
 *
 * It lives in its own module for the reason `theme.js` and the old `target.js`
 * do: an imported ES binding cannot be reassigned by the importer, so the value
 * is reached through functions and changes are announced.
 *
 * The calendar also lists days that were worked but never planned, with a
 * plan of 0 — so "is anything planned" is asked of the figures, not of how
 * many days there are.
 */

/** @typedef {{date: string, planned: number, actual: number, people: number}} PlanDay */

/** @type {Map<string, PlanDay>} keyed by "YYYY-MM-DD" */
let byDate = new Map();

/** @type {Array<() => void>} */
const listeners = [];

/**
 * Adopt a fresh calendar and tell everyone drawing from it.
 * @param {{days: PlanDay[]}} calendar A `/api/plan` response body.
 */
export function setPlanCalendar(calendar) {
    const { days = [] } = calendar || {};
    byDate = new Map(days.map((d) => [d.date, d]));
    listeners.forEach((fn) => fn());
}

/** @returns {boolean} Whether any day at all has been planned. */
export function hasPlan() {
    return [...byDate.values()].some((d) => d.planned > 0);
}

/**
 * Run `fn` whenever the plan changes.
 *
 * Saving a day's plan changes what Daily's Plan column and the Member tab's
 * figures mean, and both are usually off screen when it happens.
 *
 * @param {() => void} fn
 */
export function onPlanChange(fn) {
    listeners.push(fn);
}
