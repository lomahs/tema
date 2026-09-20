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
/** @type {Set<string>} status keys that are shown but left out of the total */
let excluded = new Set();
/** @type {Set<string>} status keys whose cases the detail view lists */
let review = new Set();
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
 * @param {{statuses?: Status[], needs_reason?: string[], executed?: string[],
 *          excluded?: string[], review?: string[]}} taxonomy
 */
export function setTaxonomy(taxonomy) {
    statuses = taxonomy.statuses || [];
    needsReason = new Set(taxonomy.needs_reason || []);
    executed = new Set(taxonomy.executed || []);
    excluded = new Set(taxonomy.excluded || []);
    review = new Set(taxonomy.review || []);
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
 * Which ones these are is configured in `config/result_status.json` and served
 * by `/api/statuses`, so the productivity table stays in step with the backend
 * instead of naming OK / NG / NG-OK itself.
 *
 * @returns {Status[]}
 */
export function getExecutedStatuses() {
    return statuses.filter((s) => executed.has(s.key));
}

/**
 * The statuses whose cases the detail view lists, in taxonomy order.
 *
 * Everything that is not a clean pass, not unstarted and not outside the plan —
 * which is what Detail is for. Configured in `config/result_status.json` by
 * `"review": true`, so this module names no status itself.
 *
 * @returns {Status[]}
 */
export function getReviewStatuses() {
    return statuses.filter((s) => review.has(s.key));
}

/**
 * Whether a case with this status belongs in the detail view at all.
 * @param {string} key
 * @returns {boolean}
 */
export function isReview(key) {
    return review.has(key);
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
 * The statuses that count toward `total`, in taxonomy order.
 *
 * The browser-side twin of `STATUS.counted`, and the one definition of it here:
 * the progress bar expands over these, the report's columns are these, and
 * Summary draws a column per one of these. Three private copies of
 * `filter(s => !isExcluded(s.key))` is how those three would come to disagree.
 *
 * @returns {Status[]}
 */
export function getCountedStatuses() {
    return statuses.filter((s) => !excluded.has(s.key));
}

/**
 * The statuses that oblige a ticket id or a note, in taxonomy order.
 *
 * What Detail selects when the Missing reason card sends someone there: the
 * condition narrows *within* the chosen statuses, so arriving with only the
 * review ones chosen would silently hide the cases of any other status that
 * owes an explanation — the very rows the card counted.
 *
 * @returns {Status[]}
 */
export function getReasonStatuses() {
    return statuses.filter((s) => needsReason.has(s.key));
}

/**
 * Whether a status is shown but deliberately left out of `total`.
 *
 * Out Of Scope is the shipped example: it owns a column so the count stays
 * visible, but a case that was never in the plan must not inflate the figure
 * progress is read against. The column is drawn set apart for that reason —
 * a reader adding the band up by eye needs to see where the sum stops.
 *
 * @param {string} key
 * @returns {boolean}
 */
export function isExcluded(key) {
    return excluded.has(key);
}


/**
 * Sum `total` plus one column per status across a set of rows.
 *
 * `total` is summed from the rows' own totals rather than recomputed, so the
 * footer inherits whatever the API decided a total means — including the
 * statuses it leaves out. Excluded columns still sum, in their own column.
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
 * @param {Object} [opts]
 * @param {boolean} [opts.blankZeros] Render an empty cell rather than `0`. Set
 *   on data rows, where a grid of zeros drowns out the figures that matter, and
 *   left off for roll-up and total rows, where a zero is a real answer.
 * @param {?Object} [opts.link] The row's context — `{file, device, scope, ...}`
 *   — which turns every non-zero figure into a button carrying it, and is what
 *   makes the status band a way *into* the cases it counts rather than only a
 *   report of them. A zero stays inert: there is nothing behind it to show.
 * @param {boolean} [opts.counted] Draw only the statuses inside `total`,
 *   omitting the excluded ones entirely. Summary asks for this: its band is
 *   wide enough already, and a column of blanks outside the sum costs room the
 *   file names need more. Everywhere else keeps the full band, because a count
 *   that appears on no screen at all is a count nobody can check.
 * @returns {string} HTML.
 */
export function statusCells(row, { blankZeros = false, counted = false, link = null } = {}) {
    const show = (v) => (v ? v : (blankZeros ? "" : 0));
    const cells = (counted ? getCountedStatuses() : statuses).map((s) => {
        const v = row[s.key] || 0;
        const zero = v ? "" : " zero";
        const aside = isExcluded(s.key) ? " band--aside" : "";
        const figure = link && v
            ? `<button type="button" class="cell-link" data-status="${esc(s.key)}"`
              + `${contextAttrs(link)}>${show(v)}</button>`
            : show(v);
        return `<td class="num band${aside}${zero}" data-tone="${esc(toneFor(s.key))}">${figure}</td>`;
    });
    return `<td class="num band band--first">${show(row.total || 0)}</td>` + cells.join("");
}

/**
 * The row's own context, as `data-` attributes on a status figure.
 *
 * Which fields a row has is the calling view's business — Summary knows a file
 * and a device, Daily also knows a date and a PIC — so this takes whatever it
 * is given and drops the blanks. Underscores become dashes so the values come
 * back off `dataset` in the usual camelCase.
 *
 * These are plain scalars, which an attribute carries losslessly. The rule
 * against round-tripping identity through the DOM is about *group paths*, whose
 * separator is a NUL the tokenizer rewrites; a file name is not that.
 *
 * @param {Object<string, string>} context
 * @returns {string} HTML attributes, each with a leading space.
 */
function contextAttrs(context) {
    return Object.entries(context)
        .filter(([, v]) => v !== undefined && v !== null && v !== "")
        .map(([k, v]) => ` data-${k.replace(/_/g, "-")}="${esc(v)}"`)
        .join("");
}

/**
 * Header cells matching {@link statusCells}, each sortable.
 *
 * @param {(col: string, label: string, opts: Object) => string} th A cell
 *   builder — `sortableTh` for a sortable table, a plain one otherwise.
 * @param {Object} [opts]
 * @param {boolean} [opts.counted] Head only the counted statuses, matching
 *   `statusCells` with the same flag set. The two are one band and must be
 *   passed the same option, or the headings slide off their figures.
 * @returns {string} HTML.
 */
export function statusHeadCells(th, { counted = false } = {}) {
    return th("total", "Total", { cls: "num band band--first" })
        + (counted ? getCountedStatuses() : statuses).map((s) => th(s.key, s.label, {
            cls: `num band${isExcluded(s.key) ? " band--aside" : ""}`,
            tone: toneFor(s.key),
        })).join("");
}

/**
 * Build a strip of stat cards: a total, one per status, then any inert cards.
 *
 * Defaults to Review's strip — the review statuses only, because those are the
 * only cases Review holds, and a card reading "OK 0" would be a permanent,
 * meaningless zero. Its first card is labelled "To review" rather than "Total"
 * for the same reason: it counts the cases on that screen, which is deliberately
 * not the Total that Summary reports, and two figures both called Total would
 * read as a bug.
 *
 * The file page passes the whole taxonomy and its own labels instead: it reports
 * on one workbook, where every status is a real bucket someone may want to see.
 * A status the taxonomy excludes from the total is marked `stat--aside`, the
 * card-strip form of the dashed rule the status band draws.
 *
 * @param {Object} [opts]
 * @param {string} [opts.container] Selector for the strip.
 * @param {Status[]} [opts.statuses] Which statuses get a card.
 * @param {string} [opts.totalLabel] Label for the leading card, which clears the
 *   status choice rather than setting one.
 * @param {string} [opts.totalId] Element id for the leading card's figure.
 * @param {string} [opts.idPrefix] Prefixed to each status key to make its id.
 * @param {Array<{label: string, id: string}>} [opts.inert] Cards that report
 *   something no status filter can express, and so are not buttons.
 *
 * **They are controls, not readouts.** Each card filters the table to its own
 * status, and the first clears that filter — the design's tab row, which is the
 * quick single pick over the same state the Result toggles inside the filter
 * panel edit one at a time. `views/detail.js` binds them; this only builds them,
 * because the status list is configurable and nothing may hard-code it.
 *
 * {@link setTaxonomy} must have run first.
 */
export function renderStatCards({
    container = "#statsRow",
    statuses: list = getReviewStatuses(),
    totalLabel = "To review",
    totalId = "statTotal",
    idPrefix = "stat-",
    inert = [{ label: "Files", id: "statFiles" }],
} = {}) {
    const cell = (label, id, tone, status, aside) => `
        <button type="button" class="stat${aside ? " stat--aside" : ""}"
                data-status-card="${esc(status)}" aria-pressed="false">
            <span class="stat-label">${esc(label)}</span>
            <span class="stat-value"${tone ? ` data-tone="${esc(tone)}"` : ""} id="${esc(id)}">0</span>
        </button>`;

    $(container).innerHTML = cell(totalLabel, totalId, "", "", false)
        + list.map((s) => cell(s.label, `${idPrefix}${s.key}`, toneFor(s.key), s.key,
                               isExcluded(s.key))).join("")
        // Files is a fact about the selection, not a status anyone can filter
        // to, so it is the one card that stays inert.
        + inert.map((c) => `<div class="stat stat--inert">
               <span class="stat-label">${esc(c.label)}</span>
               <span class="stat-value" id="${esc(c.id)}">0</span>
           </div>`).join("");
}


/**
 * A case whose status obliges the tester to record a ticket id or a note, and
 * which carries neither.
 *
 * The same predicate marks the Ticket ID and Note cells red and drives every
 * Missing reason filter, and it is the browser-side twin of what `/api/summary`
 * reports under `missing_reason`. It lives here, with the taxonomy it reads,
 * because two views ask it now — Review and the file page — and two copies of
 * this rule is exactly how they would come to disagree. Which statuses oblige
 * an explanation stays `needs_reason` in `config/result_status.json`, never
 * named in the JS.
 *
 * @param {Object} d A case row carrying `status`, `ticket_id` and `note`.
 * @returns {boolean}
 */
export function lacksReason(d) {
    return requiresReason(d.status) && !d.ticket_id && !d.note;
}
