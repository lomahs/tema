/**
 * Detail's state, and the only module that declares it.
 *
 * An imported ES binding cannot be reassigned by the importer, so a scalar two
 * modules both write is reached through the accessors below; a Map, Set or
 * object is exported directly, because mutating one is not rebinding a name.
 */

export const PAGE_SIZE = 50;

/** Groups per page once grouping is on. */
export const GROUP_PAGE_SIZE = 8;

export const DEFAULT_EXPANDED = true;

/**
 * Status key -> that status' cases, as `/api/cases` served them.
 *
 * The whole reason this screen is affordable. Cleared by `initDetail`, which
 * runs on every load and every config save — the cases behind a status can
 * change without anything here being clicked.
 *
 * @type {Map<string, Object[]>}
 */
export const cache = new Map();

/** @type {Set<string>} status keys chosen; also the fetch key. Empty shows nothing. */
export const chosenStatuses = new Set();

/** @type {Set<string>} scope group keys pressed. A filter over the cache, never fetched. */
export const chosenScopes = new Set();

/**
 * @type {Set<string>} raw Scope strings pressed in the filter well.
 *
 * Empty means every scope, which is what the select this replaced meant by "".
 * A narrowing, not a selection: unlike `chosenScopes` it never decides which
 * cases are here, only which of them are listed — which is why `clearNarrowing`
 * empties this one and deliberately leaves that one alone.
 */
export const chosenRawScopes = new Set();

/** @type {Set<string>} which groups are open */
export const expanded = new Set();

/** @type {import("../../sorting.js").SortState} */
export const detailSort = { col: null, asc: true };

let showAll = false;
export const getShowAll = () => showAll;
export const setShowAll = (v) => { showAll = v; };

let missingOnly = false;
export const getMissingOnly = () => missingOnly;
export const setMissingOnly = (v) => { missingOnly = v; };

/** @type {{key: string, label: string, counted: boolean}[]} groups, from /api/summary */
let scopeGroups = [];
export const getScopeGroups = () => scopeGroups;
export const setScopeGroups = (v) => { scopeGroups = v; };

/** @type {Object[]} /api/summary rows — where the card figures come from */
let summaryRows = [];
export const getSummaryRows = () => summaryRows;
export const setSummaryRows = (v) => { summaryRows = v; };

/** @type {Object[]} the cached cases of the chosen statuses, within the chosen scopes */
let allData = [];
export const getAllData = () => allData;
export const setAllData = (v) => { allData = v; };

/** @type {Object[]} `allData` after the filters and the sort */
let filtered = [];
export const getFiltered = () => filtered;
export const setFiltered = (v) => { filtered = v; };

/**
 * Two narrowings a drill-in can arrive with that no control here expresses.
 *
 * Clicking a figure on a "By device type" row means *that handset*, which is
 * several device names; clicking one on the file page means *that sheet*. Both
 * ride on the case (`device_family` and `sheet` come down with it) rather than
 * being re-derived here, and both are clearable from the chip row — which is
 * why they are conditions and not hidden state.
 */
let conditions = { deviceFamily: "", sheet: "" };
export const getConditions = () => conditions;
export const setConditions = (v) => { conditions = v; };

/**
 * Filter values a drill-in asked for, applied once its cases have arrived.
 *
 * The File / Device / PIC selects are filled from the cases in hand, so setting
 * one before the fetch lands would be assigning a value that is not yet an
 * option. The row clicked is made of those very cases, so by the time they
 * arrive the option exists.
 *
 * @type {?Object}
 */
let pending = null;
export const getPending = () => pending;
export const setPending = (v) => { pending = v; };

let currentPage = 1;
export const getCurrentPage = () => currentPage;
export const setCurrentPage = (v) => { currentPage = v; };

/** Whether a fetch is in flight, and which one is the current answer. */
let loading = false;
export const getLoading = () => loading;
export const setLoading = (v) => { loading = v; };

let loadToken = 0;
export const nextLoadToken = () => ++loadToken;
export const getLoadToken = () => loadToken;

/** Whether the cache was dropped since this view was last drawn. */
let stale = true;
export const getStale = () => stale;
export const setStale = (v) => { stale = v; };

/** Columns, in order. `col` is the sort key; a blank one is not sortable. */
export const COLUMNS = [
    { col: "", label: "#", cls: "num" },
    { col: "file_name", label: "File" },
    { col: "sheet", label: "Sheet" },
    { col: "device", label: "Device" },
    { col: "row_num", label: "Row", cls: "num" },
    { col: "case_no", label: "Case no" },
    { col: "scope", label: "Scope" },
    { col: "result", label: "Result" },
    { col: "test_date", label: "Date" },
    { col: "pic", label: "PIC" },
    { col: "ticket_id", label: "Ticket ID" },
    { col: "note", label: "Note" },
];

/**
 * Single-choice selects that narrow the list, with the label used on their chip.
 *
 * Result is not among them: it narrows by *status* rather than by the raw text
 * of the cell, it takes several values at once, and it is what decides which
 * cases are fetched at all — so it is handled on its own throughout this module.
 *
 * Scope is not among them either, and for the same first reason: it takes
 * several values at once. It narrows by the raw string in the cell, which is a
 * finer vocabulary than the cards at the top of the screen — the cards pick
 * *groups*, this picks the spellings inside them — and asking for two spellings
 * of one commitment ("FPT" and "FPT (JM Support)") is the normal question, not
 * an exotic one. So it is a strip of toggles like Result, and `chosenRawScopes`
 * below is its state. It differs from Result in what an empty set means: Result
 * decides which cases are *fetched*, so all-pressed is its neutral position,
 * while this only narrows cases already in hand, so **empty means no narrowing**
 * — exactly what the select's "" meant before it.
 */
export const FILTERS = [
    { id: "filterFile", field: "file_name", label: "File" },
    { id: "filterDevice", field: "device", label: "Device" },
    { id: "filterPIC", field: "pic", label: "PIC" },
];
export const DATE_FILTERS = [
    { id: "filterDateFrom", label: "From" },
    { id: "filterDateTo", label: "To" },
];
