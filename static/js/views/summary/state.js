/**
 * Summary's state, and the only module that declares it.
 *
 * Same rule as `views/detail/state.js`: a scalar two modules both write is
 * reached through an accessor, because an imported binding cannot be
 * reassigned; a Map, Set or object is exported directly.
 */

/** @typedef {{key: string, label: string}} ScopeGroup */

/** Files per page, per card. The design's page size. */
export const PAGE_SIZE = 10;

/** @type {Object[]} rows from /api/summary, each carrying its scope group key */
let groups = [];
export const getGroups = () => groups;
export const setGroups = (v) => { groups = v; };

/** @type {ScopeGroup[]} every configured group, in config order */
let scopes = [];
export const getScopes = () => scopes;
export const setScopes = (v) => { scopes = v; };

/**
 * The three tables, in the order they are drawn.
 *
 * Summary used to draw one table per scope group. It now draws one per *role*,
 * because the roles are what a reader is actually comparing: what we committed
 * to, what we are reporting but did not commit to, and what nobody has
 * classified yet. A team with six scope groups had six tables and no way to see
 * the first of those three figures at all.
 *
 * The roles come from the config, not from this file — `counted` and `fallback`
 * ride along on every group in `/api/summary`'s `scopes` list, so no scope is
 * ever named here. The third bucket takes its heading from the fallback group's
 * own label for the same reason; the first two are role names, not scopes, so
 * they are written down.
 *
 * `counted` is the KPI strip's denominator too — `summaryOverview` filters by
 * the same flag — so "the total is the In Scope table" holds by construction
 * rather than by two places agreeing to compute it the same way.
 *
 * @type {{key: string, title: string|null, pick: (g: ScopeGroup) => boolean}[]}
 */
export const BUCKETS = [
    { key: "in", title: "In Scope", pick: (g) => g.counted !== false && !g.fallback },
    { key: "out", title: "Out Scope", pick: (g) => g.counted === false && !g.fallback },
    // Titled from the group itself: it is one configured group, and naming it
    // here would be this module naming a scope.
    { key: "other", title: null, pick: (g) => !!g.fallback },
];

/**
 * @type {Set<string>} scope group keys pressed, across every bucket.
 *
 * A filter over rows already fetched, never a fetch — the same arrangement as
 * Review's scope cards, whose behaviour these copy. Every group starts pressed:
 * unlike Review, where adding work outside the plan is a deliberate choice, a
 * bucket exists precisely to show what is in it.
 */
export const chosenScopes = new Set();

/** @type {import("../../sorting.js").SortState} shared by every table */
export const sort = { col: null, asc: true };

/**
 * How many rows a file gets.
 *
 * - `split` — one per (file, device): the granularity the backend serves and
 *   the report writes.
 * - `family` — one per (file, device family): "iPhone Min size" and "iPhone Max
 *   size" are two device blocks in the workbook but one handset to anyone
 *   reading the totals. Which names make a family is configured in
 *   `config/device_groups.json` and arrives on the row as `device_family`, so
 *   this module names no device of its own.
 * - `combined` — one per file, every device summed.
 *
 * The design defaults to combined. This defaults to split, because per-device
 * is what this table has always shown and what the published report is keyed
 * on; collapsing it silently would be a change of meaning, not of layout.
 *
 * None of the three changes a total — only how many rows carry it.
 *
 * @type {"split"|"family"|"combined"}
 */
let grouping = "split";
export const getGrouping = () => grouping;
export const setGrouping = (v) => { grouping = v; };

/** The cycle the Rows button walks, and what it reads in each state. */
export const GROUPINGS = [
    { key: "split", label: "Split" },
    { key: "family", label: "By device type" },
    { key: "combined", label: "Combined" },
];

/** @type {{key: string, label: string}[]} from /api/summary, for naming a family */
let families = [];
export const getFamilies = () => families;
export const setFamilies = (v) => { families = v; };

/** @type {Map<string, {page: number, showAll: boolean}>} keyed by scope key */
export const paging = new Map();

/** No expansion here — the tables are flat — but the widget wants the set. */
export const noExpansion = new Set();

export const FILTERS = ["#summaryFilterDevice", "#summaryFilterFile"];

/**
 * Called with a file name when one is clicked.
 *
 * A file cell is a way into the file view, but this module must not import it —
 * `main.js` owns the views, the same arrangement that keeps `views/detail/index.js`
 * out of here for the Missing reason jump.
 */
let onOpenFile = () => {};
export const getOnOpenFile = () => onOpenFile;
export const setOnOpenFile = (fn) => { onOpenFile = fn; };

/**
 * Called with a status figure's context when one is pressed.
 *
 * Every number in the status band is a way into the cases it counts, and this
 * module must no more import the view that lists them than it imports the file
 * view — `main.js` owns both. The context is the row: its file, its device or
 * device family, and the scope group whose card it was drawn in.
 *
 * @type {(ctx: Object) => void}
 */
let onDrillIn = () => {};
export const getOnDrillIn = () => onDrillIn;
export const setOnDrillIn = (fn) => { onDrillIn = fn; };
