/**
 * The result taxonomy (OK / NG / Pending / ...) and the table scaffolding built
 * from it.
 *
 * The taxonomy is served by `/api/statuses` rather than hard-coded, so the UI
 * and the backend always agree on which status columns exist. This module owns
 * that state: nothing else caches the status list, because an ES-module export
 * cannot be reassigned by an importer.
 */
import { $, esc } from "./dom.js";

/** @typedef {{key: string, label: string, badge: string, text: string}} Status */

/** @type {Status[]} */
let statuses = [];
/** @type {Set<string>} status keys that require a ticket id or a note */
let needsReason = new Set();
/** @type {Set<string>} status keys that count as work actually carried out */
let executed = new Set();
/** @type {Object<string, string>} status key -> bootstrap badge class */
let badgeOf = {};
/** @type {Object<string, string>} status key -> bootstrap text colour class */
let textOf = {};

/**
 * Adopt the taxonomy from `/api/statuses`.
 *
 * Must run before {@link renderStatCards} or any view header render — those
 * read the status list to decide which columns to emit.
 *
 * @param {{statuses?: Status[], needs_reason?: string[], executed?: string[]}} taxonomy
 */
export function setTaxonomy(taxonomy) {
    statuses = taxonomy.statuses || [];
    needsReason = new Set(taxonomy.needs_reason || []);
    executed = new Set(taxonomy.executed || []);
    badgeOf = Object.fromEntries(statuses.map((s) => [s.key, s.badge]));
    textOf = Object.fromEntries(statuses.map((s) => [s.key, s.text || ""]));
}

/**
 * The ordered status list. Treat as read-only.
 * @returns {Status[]}
 */
export function getStatuses() {
    return statuses;
}

/**
 * The statuses that count as work carried out, in taxonomy order.
 *
 * Which ones these are is configured in `parser/result_status.json` and served
 * by `/api/statuses`, so the productivity table stays in step with the backend
 * instead of naming OK / NG / NG-OK itself.
 *
 * @returns {Status[]}
 */
export function getExecutedStatuses() {
    return statuses.filter((s) => executed.has(s.key));
}

/**
 * Bootstrap badge class for a status key.
 * @param {string} key
 * @returns {string} Empty string when the key is unknown.
 */
export function badgeFor(key) {
    return badgeOf[key] || "";
}

/**
 * Whether a status obliges the tester to record a ticket id or a note.
 * @param {string} key
 * @returns {boolean}
 */
export function requiresReason(key) {
    return needsReason.has(key);
}

/**
 * Sum `total` plus one column per status across a set of rows.
 *
 * Because the API always emits every status key (unknown results land in the
 * configured fallback bucket), the status columns add up to `total`.
 *
 * @param {Object[]} rows Summary or daily rows.
 * @returns {Object<string, number>} `{total, <statusKey>: n, ...}`
 */
export function sumRows(rows) {
    const totals = { total: 0 };
    statuses.forEach((s) => { totals[s.key] = 0; });
    rows.forEach((r) => {
        totals.total += r.total || 0;
        statuses.forEach((s) => { totals[s.key] += r[s.key] || 0; });
    });
    return totals;
}

/**
 * One `<td>` per status, in taxonomy order.
 * @param {Object} row A row (or a totals object) keyed by status.
 * @param {boolean} [emphasise] Colour the counts by status.
 * @returns {string} HTML.
 */
export function statusCells(row, emphasise) {
    return statuses.map((s) => {
        const cls = emphasise ? statusTextClass(s.key) : "";
        const v = row[s.key];
        return `<td${cls ? ` class="${cls}"` : ""}>${v || ""}</td>`;
    }).join("");
}

/**
 * Text colour for a status. Taken from the status' configured `text` class so
 * the palette stays in one place (`parser/result_status.json`) — a badge class
 * cannot serve here, since several statuses share a badge but want different
 * text colours (NG-OK vs Pending, Cancel vs NYS).
 *
 * A status with no `text` keeps the default body colour, which is what NYS
 * wants: a muted grey there is indistinguishable from the table header.
 *
 * @param {string} key
 * @returns {string} Bootstrap utility classes, possibly empty.
 */
export function statusTextClass(key) {
    const text = textOf[key];
    return text ? `${text} fw-bold` : "";
}

/**
 * Build the detail view's stat cards: Total, one per status, then Files.
 *
 * The cards are generated rather than written into the template because the
 * status list is configurable. {@link setTaxonomy} must have run first.
 */
export function renderStatCards() {
    const subtle = (key) => {
        const badge = badgeFor(key);
        if (badge.includes("bg-success")) return " bg-success-subtle";
        if (badge.includes("bg-danger")) return " bg-danger-subtle";
        if (badge.includes("bg-warning")) return " bg-warning-subtle";
        return "";
    };
    const card = (label, id, extra) => `
        <div class="col-auto"><div class="card stat-card${extra || ""}"><div class="card-body py-2 px-3">
            <div class="small text-muted">${esc(label)}</div>
            <div class="fs-5 fw-bold" id="${esc(id)}">0</div>
        </div></div></div>`;

    $("#statsRow").innerHTML = card("Total", "statTotal")
        + statuses.map((s) => card(s.label, `stat-${s.key}`, subtle(s.key))).join("")
        + card("Files", "statFiles", " bg-info-subtle");
}
