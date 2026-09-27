/**
 * Thin DOM helpers shared by every module.
 */

/**
 * First element matching a CSS selector.
 * @param {string} sel
 * @returns {Element|null}
 */
export const $ = (sel) => document.querySelector(sel);

/**
 * All elements matching a CSS selector.
 * @param {string} sel
 * @returns {NodeListOf<Element>}
 */
export const $$ = (sel) => document.querySelectorAll(sel);

/**
 * Escape a value for interpolation into an HTML template string.
 *
 * Every module builds rows with template literals, so any field that comes from
 * a spreadsheet — file names, notes, PIC names — must pass through here.
 *
 * @param {*} v Any value; `null`/`undefined` become an empty string.
 * @returns {string} HTML-safe text.
 */
export function esc(v) {
    return v == null ? "" : String(v)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/**
 * An ISO timestamp as "27 Sep 2026 14:02", the way snapshots are named on screen.
 * @param {?string} iso
 * @returns {string}
 */
export function formatStamp(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const date = d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
    const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    return `${date} ${time}`;
}
