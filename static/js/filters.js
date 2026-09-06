/**
 * Helpers for the dropdown filters used by both the detail and daily views.
 */
import { $, esc } from "./dom.js";

/**
 * Distinct, sorted, non-blank values of one field across rows.
 * @param {Object[]} rows
 * @param {string} key
 * @returns {string[]}
 */
export function uniqueOf(rows, key) {
    return [...new Set(rows.map((r) => r[key]).filter(Boolean))].sort();
}

/**
 * Refill a `<select>` with `values`, keeping its "All ..." placeholder and the
 * current selection.
 *
 * The placeholder text is read back off the existing first option rather than
 * passed in, so each select keeps the wording set in the template ("All Files",
 * "All PICs", ...). Restoring `el.value` afterwards is what stops a reload from
 * silently clearing an active filter — if the old value is no longer among the
 * options the assignment is ignored and the select falls back to "All".
 *
 * @param {string} sel CSS selector for the `<select>`.
 * @param {string[]} values
 */
export function populateSelect(sel, values) {
    const el = $(sel);
    const current = el.value;
    const label = el.options.length ? el.options[0].text : "All";
    el.innerHTML = `<option value="">${esc(label)}</option>`
        + values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("");
    el.value = current;
}
