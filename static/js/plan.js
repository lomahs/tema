/**
 * The plan, as the rest of the app reads it.
 *
 * This replaces `target.js`, and the replacement is a change of kind rather
 * than of storage. The target was one number — cases per person per day — that
 * every plan figure in the app was multiplied out of, kept in `localStorage`
 * because nothing on the server knew about it. A plan says what was actually
 * meant to happen on a given day, for named people on named files, so it lives
 * on the server, it differs per day, and it is the thing Daily's plan line and
 * Productivity's attainment bar are now drawn from.
 *
 * What is held here is the *calendar*: one line per day, planned against done.
 * That is what Daily and Productivity need, and it is small — a few hundred
 * numbers for a sprint. The rows of a single day, and the suggestion table, are
 * fetched by `views/planning.js` when somebody is actually looking at them.
 *
 * It lives in its own module for the reason `theme.js` and the old `target.js`
 * do: an imported ES binding cannot be reassigned by the importer, so the value
 * is reached through functions and changes are announced.
 *
 * One consequence is deliberate and worth knowing. A day nobody planned has no
 * plan figure at all — `plannedFor` answers `null`, not `0`. Zero is a plan
 * somebody set; "no plan" is the absence of one, and a chart drawing a plan
 * line at zero across every day before this feature existed would be inventing
 * a target nobody agreed to.
 */

/** @typedef {{date: string, planned: number, actual: number, people: number}} PlanDay */

/** @type {Map<string, PlanDay>} keyed by "YYYY-MM-DD" */
let byDate = new Map();

/**
 * Cases planned per person, across every day.
 *
 * Productivity reports over the whole load at once, so it cannot read a per-day
 * figure, and a request per member would be one request per row of its table.
 * The server sends this alongside the calendar instead.
 *
 * @type {Map<string, number>}
 */
let byPic = new Map();

/** @type {Array<() => void>} */
const listeners = [];

/**
 * Adopt a fresh calendar and tell everyone drawing from it.
 * @param {{days: PlanDay[], by_pic: Object<string, number>}} calendar
 *   A `/api/plan` response body.
 */
export function setPlanCalendar(calendar) {
    const { days = [], by_pic: perPic = {} } = calendar || {};
    byDate = new Map(days.map((d) => [d.date, d]));
    byPic = new Map(Object.entries(perPic));
    listeners.forEach((fn) => fn());
}

/**
 * How many cases were planned for one day.
 *
 * @param {string} date "YYYY-MM-DD".
 * @returns {?number} `null` when that day was never planned — which is not the
 *   same as a plan of zero, and callers must not treat it as one.
 */
export function plannedFor(date) {
    const day = byDate.get(date);
    return day ? day.planned : null;
}

/**
 * How many cases one person was planned for, across every day.
 *
 * @param {string} pic
 * @returns {?number} `null` when nobody ever planned work for them — not zero,
 *   for the reason `plannedFor` gives.
 */
export function plannedForPic(pic) {
    return byPic.has(pic) ? byPic.get(pic) : null;
}

/** @returns {number} Cases planned for everyone, across every day. */
export function plannedTotal() {
    let sum = 0;
    byPic.forEach((n) => { sum += n; });
    return sum;
}

/** @returns {boolean} Whether any day at all has been planned. */
export function hasPlan() {
    return byDate.size > 0;
}

/**
 * Every planned day, in date order.
 * @returns {PlanDay[]}
 */
export function planDays() {
    return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * Run `fn` whenever the plan changes.
 *
 * Saving a day's plan changes what Daily's Plan column and Productivity's
 * attainment bar mean, and both are usually off screen when it happens.
 *
 * @param {() => void} fn
 */
export function onPlanChange(fn) {
    listeners.push(fn);
}
