/**
 * The daily target: how many cases one person is expected to execute in a day.
 *
 * This is the one number in the app that is not read out of a workbook. It has
 * no backend, no endpoint and no aggregate — it is a yardstick the team sets for
 * itself, and the plan line on the Daily chart, the Plan and Attain columns of
 * the daily log, and the attainment bar on Productivity are all derived from it
 * in the browser. Nothing is written anywhere as a result of changing it.
 *
 * It lives in its own module because two views read it and one of them writes
 * it: an imported ES binding cannot be reassigned by the importer, so the value
 * is reached through functions and changes are announced, the same arrangement
 * `theme.js` uses.
 *
 * The design canvas keeps this in component state, which forgets it on reload.
 * It is kept in `localStorage` here: a target is a team's standing figure, and
 * retyping it every morning is how it ends up wrong.
 */

const STORAGE_KEY = "test-management.target";

/** Cases per person per day. The design's default, and a plausible one. */
const DEFAULT_TARGET = 30;

let target = DEFAULT_TARGET;

/** @type {Array<() => void>} */
const listeners = [];

/** @returns {number} The current target, always at least 1. */
export function getTarget() {
    return target;
}

/**
 * Adopt a new target and tell everyone drawing from it.
 *
 * Zero and negative values are refused rather than clamped silently: the target
 * is a divisor, and a zero one turns every attainment figure into Infinity.
 *
 * @param {number|string} value
 * @returns {number} What was actually adopted, so a caller can correct its input.
 */
export function setTarget(value) {
    const n = Math.round(Number(value));
    target = Number.isFinite(n) && n > 0 ? n : DEFAULT_TARGET;
    try {
        localStorage.setItem(STORAGE_KEY, String(target));
    } catch (_) { /* private window, blocked storage — the choice just will not survive */ }
    listeners.forEach((fn) => fn());
    return target;
}

/**
 * Run `fn` whenever the target changes.
 * @param {() => void} fn
 */
export function onTargetChange(fn) {
    listeners.push(fn);
}

/**
 * The plan for a day: the target multiplied by the people who actually worked.
 *
 * Members rather than headcount, and measured per day — a day two people tested
 * is not judged against a five-person plan. That is also why a day with no
 * named PIC has no plan: there is nobody to hold the figure against.
 *
 * @param {number} members Distinct PICs active that day.
 * @returns {number} 0 when nobody worked.
 */
export function planFor(members) {
    return members > 0 ? target * members : 0;
}

/** Read the stored target. Call once, at startup. */
export function initTarget() {
    let stored = null;
    try {
        stored = localStorage.getItem(STORAGE_KEY);
    } catch (_) { /* as above */ }
    const n = Math.round(Number(stored));
    target = Number.isFinite(n) && n > 0 ? n : DEFAULT_TARGET;
}
