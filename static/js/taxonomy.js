/**
 * The result taxonomy (OK / NG / Pending / ...) and the table scaffolding built
 * from it.
 *
 * The taxonomy is served by `/api/statuses` rather than hard-coded, so the UI
 * and the backend always agree on which status columns exist. This module owns
 * that state: nothing else caches the status list, because an ES-module export
 * cannot be reassigned by an importer.
 *
 * Colour comes from each status' `tone` — a semantic name, not a hex value.
 * What a tone looks like belongs to `tokens.css`, which is why the same five
 * names drive badges, number columns and chart slices alike.
 */
import { $, esc } from "./dom.js";
import { shade } from "./theme.js";

/** @typedef {{key: string, label: string, tone: string}} Status */

/** @type {Status[]} */
let statuses = [];
/** @type {Set<string>} status keys that require a ticket id or a note */
let needsReason = new Set();
/** @type {Set<string>} status keys that count as work actually carried out */
let executed = new Set();
/** @type {Object<string, string>} status key -> tone */
let toneOf = {};
/** @type {Object<string, number>} status key -> its position among statuses sharing its tone */
let shadeOf = {};

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
    toneOf = Object.fromEntries(statuses.map((s) => [s.key, s.tone || "neutral"]));

    // Several statuses legitimately share a tone — OK and NG-OK are both good
    // outcomes, Cancel and NYS are both grey. Charts still need to tell them
    // apart, so each gets a shade step by its position within its tone.
    const seen = {};
    shadeOf = {};
    statuses.forEach((s) => {
        const tone = toneOf[s.key];
        seen[tone] = seen[tone] === undefined ? 0 : seen[tone] + 1;
        shadeOf[s.key] = seen[tone];
    });
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
 * Semantic colour name for a status key.
 * @param {string} key
 * @returns {string} One of success / danger / warn / neutral / muted.
 */
export function toneFor(key) {
    return toneOf[key] || "neutral";
}

/**
 * A concrete colour for a status, for anything that paints outside CSS.
 *
 * Charts cannot be handed `var(--tone-success)`, and two statuses sharing a
 * tone must not come out as the same slice, so the tone is resolved and then
 * stepped by the status' position within it.
 *
 * @param {string} key
 * @returns {string} A computed CSS colour.
 */
export function colourFor(key) {
    return shade(`--tone-${toneFor(key)}`, shadeOf[key] || 0);
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
 * The Total cell plus one `<td>` per status, in taxonomy order.
 *
 * These columns are the status band — the run of measurements that recurs
 * across Summary, Daily and Productivity — so the first of them carries
 * `band--first`, which is what draws the rule separating identity from
 * measurement.
 *
 * @param {Object} row A row (or a totals object) keyed by status.
 * @returns {string} HTML.
 */
export function statusCells(row) {
    const cells = statuses.map((s) => {
        const v = row[s.key] || 0;
        const zero = v ? "" : " zero";
        return `<td class="num band${zero}" data-tone="${esc(toneFor(s.key))}">${v}</td>`;
    });
    return `<td class="num band band--first">${row.total || 0}</td>` + cells.join("");
}

/**
 * Header cells matching {@link statusCells}, each sortable.
 *
 * @param {(col: string, label: string, opts: Object) => string} th A cell
 *   builder — `sortableTh` for a sortable table, a plain one otherwise.
 * @returns {string} HTML.
 */
export function statusHeadCells(th) {
    return th("total", "Total", { cls: "num band band--first" })
        + statuses.map((s) =>
            th(s.key, s.label, { cls: "num band", tone: toneFor(s.key) })).join("");
}

/**
 * Build the detail view's stat cards: Total, one per status, then Files.
 *
 * Generated rather than written into the template because the status list is
 * configurable. {@link setTaxonomy} must have run first.
 */
export function renderStatCards() {
    const cell = (label, id, tone) => `
        <div class="stat">
            <div class="stat-label">${esc(label)}</div>
            <div class="stat-value"${tone ? ` data-tone="${esc(tone)}"` : ""} id="${esc(id)}">0</div>
        </div>`;

    $("#statsRow").innerHTML = cell("Total", "statTotal")
        + statuses.map((s) => cell(s.label, `stat-${s.key}`, toneFor(s.key))).join("")
        + cell("Files", "statFiles");
}
