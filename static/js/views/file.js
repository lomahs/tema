/**
 * File view: one workbook, sheet by sheet, and the work outstanding inside it.
 *
 * The drill-in behind a file name. Summary answers "how do the files compare";
 * this answers "what is in this one", which is why it is the only view not in
 * the rail — it is about a subject you have to pick first, so it is reached by
 * clicking a file name and left through the Back button it draws itself.
 *
 * Two things about what it counts are deliberate, and both differ from Review:
 *
 * - **Every scope group is here, including one the plan excludes.** The Scope
 *   filter is half the point of the page, and a filter with one option is not
 *   one. `/api/file` is the only read endpoint that does not run through
 *   `in_plan` for exactly this reason, so these figures can legitimately exceed
 *   Review's.
 * - **The leading card is "Cases", not "Total".** It includes work outside the
 *   plan, which Summary's Total excludes, and two different numbers both called
 *   Total would read as a bug — the same reasoning that labels Review's card
 *   "To review".
 *
 * Owns the open file and everything derived from it: the scope choice, the
 * status card pressed, the missing-reason condition, two sort states and two
 * pagers. Imports no other view — `main.js` owns navigation, and hands the back
 * button a callback the way it hands `summaryOverview` its jump handler.
 */
import { $, esc } from "../dom.js";
import { populateSelect, uniqueOf } from "../filters.js";
import { renderGroupedTable } from "../groupedTable.js";
import { renderPageFooter } from "../pagination.js";
import { makeSortable, paintSortIndicators, sortableTh, sortRows } from "../sorting.js";
import {
    getReviewStatuses, getStatuses, isReview, lacksReason, renderStatCards,
    statusCells, statusHeadCells, sumRows, toneFor,
} from "../taxonomy.js";

/** Sheet rows per page. A workbook has tabs, not thousands of them. */
const SHEET_PAGE_SIZE = 20;

/** Cases per page, as Review pages them. */
const CASE_PAGE_SIZE = 50;

/** Nothing nests here; the shared table widget still wants a Set. */
const noExpansion = new Set();

/** The case table's columns, in order. */
const CASE_COLUMNS = [
    { col: "case_no", label: "Case no", cls: "mono clip clip-sm" },
    { col: "sheet", label: "Sheet" },
    { col: "scope", label: "Scope" },
    { col: "device", label: "Device" },
    { col: "row_num", label: "Row", cls: "num" },
    { col: "result", label: "Result" },
    { col: "test_date", label: "Date" },
    { col: "pic", label: "PIC" },
    { col: "ticket_id", label: "Ticket ID" },
    { col: "note", label: "Note" },
];

/** @type {string} basename of the open workbook, "" when none */
let fileName = "";
/** @type {Object[]} `/api/file` sheet rows */
let rows = [];
/** @type {Object[]} that file's cases, each carrying `status` and `scope_group` */
let cases = [];

/** The status card pressed, or "" for none. A single pick, like Review's cards. */
let chosenStatus = "";
/** Whether the case table is narrowed to cases owing a reason and carrying none. */
let missingOnly = false;

let sheetSort = { col: null, asc: true };
let caseSort = { col: null, asc: true };
let sheetPage = 1;
let sheetShowAll = false;
let casePage = 1;
let caseShowAll = false;

/** Called when the Back button is pressed. */
let onBack = () => {};

/**
 * Called with a status figure's context when one is pressed.
 *
 * The same door Summary's band carries, reported back the same way: this module
 * no more knows which view lists the cases than it knows which view sent the
 * reader here. Its rows name a sheet as well, which no control on the
 * destination expresses — so it rides along as a condition.
 *
 * @type {(ctx: Object) => void}
 */
let onDrillIn = () => {};

/**
 * Wire the controls. Call once, at startup.
 *
 * The status cards are regenerated on every taxonomy load, so the strip is
 * bound here by delegation rather than each card being bound as it is built —
 * the arrangement Review uses, and for the same reason.
 *
 * @param {{onBack: () => void, onDrillIn?: (ctx: Object) => void}} opts
 */
export function initFileView(opts) {
    onBack = opts.onBack;
    onDrillIn = opts.onDrillIn || (() => {});

    $("#btnFileBack").addEventListener("click", () => onBack());

    // One listener for the sheet table: its rows are redrawn on every filter,
    // and every figure in them is the same kind of link.
    $("#fileSheetBody").addEventListener("click", (e) => {
        const figure = e.target.closest("button[data-status]");
        if (figure) onDrillIn({ ...figure.dataset, file: fileName });
    });
    $("#fileSheetFoot").addEventListener("click", (e) => {
        const figure = e.target.closest("button[data-status]");
        if (figure) onDrillIn({ ...figure.dataset, file: fileName });
    });

    $("#fileFilterScope").addEventListener("change", () => {
        sheetPage = 1;
        casePage = 1;
        render();
    });

    $("#btnClearFileFilters").addEventListener("click", () => {
        $("#fileFilterScope").value = "";
        chosenStatus = "";
        missingOnly = false;
        sheetPage = 1;
        casePage = 1;
        render();
    });

    // A single pick over every status, the way Review's cards are a single pick
    // over the review ones. Pressing the card already chosen clears it, so the
    // strip is also the way back out.
    $("#fileStatsRow").addEventListener("click", (e) => {
        const card = e.target.closest("button[data-status-card]");
        if (!card) return;
        const key = card.dataset.statusCard;
        chosenStatus = (key && card.getAttribute("aria-pressed") !== "true") ? key : "";
        sheetPage = 1;
        casePage = 1;
        render();
    });

    // A condition, not a status choice: it narrows within whichever cases are
    // listed rather than picking which ones those are.
    $("#btnFileMissingReason").addEventListener("click", () => {
        missingOnly = !missingOnly;
        casePage = 1;
        render();
    });
}

/**
 * Rebuild everything the taxonomy decides the shape of: the card strip and both
 * table heads.
 *
 * Called on every load, after `setTaxonomy` — a status added or renamed in the
 * Config view changes the columns and the cards while the app runs. The heads
 * carry their own `makeSortable`, so nothing here may also be bound at init:
 * binding a header twice sorts twice per click and looks like nothing happened.
 */
export function renderFileHeads() {
    renderStatCards({
        container: "#fileStatsRow",
        statuses: getStatuses(),
        totalLabel: "Cases",
        totalId: "fileStatTotal",
        idPrefix: "fileStat-",
        inert: [
            { label: "Sheets", id: "fileStatSheets" },
            { label: "Devices", id: "fileStatDevices" },
        ],
    });

    $("#fileSheetHead").innerHTML =
        sortableTh("sheet", "Sheet") + sortableTh("scope", "Scope")
        + sortableTh("device", "Device") + statusHeadCells(sortableTh);
    makeSortable("#fileSheetHead th.sortable", sheetSort, () => { sheetPage = 1; render(); });
    paintSortIndicators("#fileSheetHead th.sortable", sheetSort);

    $("#fileCaseHead").innerHTML =
        CASE_COLUMNS.map((c) => sortableTh(c.col, c.label, { cls: c.cls || "" })).join("");
    makeSortable("#fileCaseHead th.sortable", caseSort, () => { casePage = 1; render(); });
    paintSortIndicators("#fileCaseHead th.sortable", caseSort);
}

/**
 * Adopt one workbook and draw it.
 *
 * Every filter is reset: arriving into a page still narrowed by the scope or
 * status someone picked on a different file would show a figure the card that
 * sent them never reported.
 *
 * @param {{file: string, rows: Object[], cases: Object[]}} data `/api/file` body.
 * @param {{backTo?: string}} [opts] What the Back button should name — the view
 *   the reader came from, which `main.js` knows and this does not.
 */
export function showFile(data, { backTo = "Summary" } = {}) {
    fileName = data.file || "";
    rows = data.rows || [];
    cases = data.cases || [];
    chosenStatus = "";
    missingOnly = false;
    sheetPage = 1;
    sheetShowAll = false;
    casePage = 1;
    caseShowAll = false;

    $("#btnFileBack").textContent = `‹ Back to ${backTo}`;
    $("#fileFilterScope").value = "";
    populateSelect("#fileFilterScope", uniqueOf(rows, "scope"));

    render();
}

/**
 * The workbook currently open, or "" when none.
 *
 * `main.js` re-fetches it after a reload or a config save — the numbers on this
 * page are as stale as any other view's, and it is the one view that cannot be
 * redrawn from what `fetchAll` returns.
 *
 * @returns {string}
 */
export function currentFile() {
    return fileName;
}

/** The scope group chosen, or "" for all of them. */
function chosenScope() {
    return $("#fileFilterScope").value;
}

/** Sheet rows under the scope choice alone — what the cards count over. */
function conditionedRows() {
    const scope = chosenScope();
    return scope ? rows.filter((r) => r.scope === scope) : rows;
}

/** Redraw the cards and both cards' tables. */
function render() {
    const conditioned = conditionedRows();
    renderCards(conditioned);
    renderSheetTable(conditioned);
    renderCaseTable();
}

/**
 * Fill the card strip.
 *
 * The figures come from the sheet rows rather than from the cases, so a card
 * and the table beneath it cannot disagree — `total` here means what it means
 * everywhere else, the sum of the counted statuses, so an excluded status shows
 * its own count without being inside the leading figure.
 *
 * Cards count over the scope choice but **not** over the status choice: a card
 * is the way to pick a status, so its figure has to say how many there are to
 * pick. Review's rule, for Review's reason.
 *
 * @param {Object[]} conditioned Sheet rows under the scope choice.
 */
function renderCards(conditioned) {
    const totals = sumRows(conditioned);
    const set = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value.toLocaleString();
    };

    set("fileStatTotal", totals.total);
    getStatuses().forEach((s) => set(`fileStat-${s.key}`, totals[s.key] || 0));
    set("fileStatSheets", new Set(conditioned.map((r) => r.sheet)).size);
    set("fileStatDevices", new Set(conditioned.map((r) => r.device)).size);

    $("#fileStatsRow").querySelectorAll("button[data-status-card]").forEach((b) =>
        b.setAttribute("aria-pressed", String(b.dataset.statusCard === chosenStatus)));
}

/**
 * Draw the per-sheet table.
 *
 * The status choice hides rows rather than changing what they say: picking NG
 * keeps the sheets that have at least one, and every figure on the row stays
 * exactly what it was. A row whose counts moved with the filter would stop
 * being the sheet's own total.
 *
 * @param {Object[]} conditioned Sheet rows under the scope choice.
 */
function renderSheetTable(conditioned) {
    const visible = chosenStatus
        ? conditioned.filter((r) => (r[chosenStatus] || 0) > 0)
        : conditioned;

    const numeric = new Set(["total", ...getStatuses().map((s) => s.key)]);
    const sorted = sortRows(visible, sheetSort, numeric);

    const pageCount = Math.max(1, Math.ceil(sorted.length / SHEET_PAGE_SIZE));
    const page = Math.min(Math.max(1, sheetPage), pageCount);
    const shown = sheetShowAll
        ? sorted
        : sorted.slice((page - 1) * SHEET_PAGE_SIZE, page * SHEET_PAGE_SIZE);

    renderGroupedTable({
        container: "#fileSheetBody",
        rows: shown,
        totalCols: 4 + getStatuses().length,
        expanded: noExpansion,
        renderLabelCells: (r) =>
            `<td>${esc(r.sheet)}</td><td>${esc(r.scope)}</td><td>${esc(r.device)}</td>`,
        labelCols: 3,
        // A row here is one (sheet, scope, device) of this workbook, and all
        // three travel: the file is added by the listener, which is the one
        // thing every row on this page shares.
        renderValues: (r) => statusCells(r, {
            blankZeros: true,
            link: { sheet: r.sheet, scope: r.scope, device: r.device },
        }),
        onToggle: () => {},
        emptyMessage: "No sheets match these filters.",
    });

    // The totals row adds up every row the filters left, not the visible page:
    // it answers "where does this file stand", which paging must not change.
    const totals = sumRows(sorted);
    // The footer covers the whole file under the Scope filter as it stands, so
    // its figures lead to that and not to the sheet above them.
    $("#fileSheetFoot").innerHTML =
        `<tr><td colspan="3">Total</td>${statusCells(totals, {
            link: { scope: $("#fileFilterScope").value },
        })}</tr>`;

    renderPageFooter({
        container: "#fileSheetFooter",
        totalItems: sorted.length,
        pageSize: SHEET_PAGE_SIZE,
        currentPage: page,
        showAll: sheetShowAll,
        unit: "row",
        onPageChange: (p) => { sheetPage = p; render(); },
        onToggleAll: (all) => { sheetShowAll = all; sheetPage = 1; render(); },
    });
}

/**
 * The cases the lower table is drawn from, before the missing-reason condition.
 *
 * With no card pressed this is the work outstanding — whatever the taxonomy
 * marks `review` — which is what the section is for. Press a card and it
 * becomes that status' cases instead, whichever status it is: singling one out
 * would mean writing a status key into the JS, and the taxonomy is the only
 * place a status may be named.
 */
function conditionedCases() {
    const scope = chosenScope();
    return cases.filter((d) => {
        if (scope && d.scope_group !== scope) return false;
        return chosenStatus ? d.status === chosenStatus : isReview(d.status);
    });
}

/** Draw the case table, its heading and its missing-reason button. */
function renderCaseTable() {
    const conditioned = conditionedCases();
    const owing = conditioned.filter(lacksReason).length;
    const listed = missingOnly ? conditioned.filter(lacksReason) : conditioned;

    const chosen = getStatuses().find((s) => s.key === chosenStatus);
    $("#fileCasesTitle").textContent = chosen
        ? chosen.label
        : `Open work — ${getReviewStatuses().map((s) => s.label).join(", ")}`;

    const btn = $("#btnFileMissingReason");
    btn.textContent = owing ? `Missing reason · ${owing}` : "Missing reason";
    btn.setAttribute("aria-pressed", String(missingOnly));
    btn.disabled = !owing && !missingOnly;

    const sorted = sortRows(listed, caseSort, new Set(["row_num"]));
    const pageCount = Math.max(1, Math.ceil(sorted.length / CASE_PAGE_SIZE));
    const page = Math.min(Math.max(1, casePage), pageCount);
    const shown = caseShowAll
        ? sorted
        : sorted.slice((page - 1) * CASE_PAGE_SIZE, page * CASE_PAGE_SIZE);

    renderGroupedTable({
        container: "#fileCaseBody",
        rows: shown,
        totalCols: CASE_COLUMNS.length,
        expanded: noExpansion,
        renderLabelCells: () => "",
        labelCols: 0,
        renderValues: (d) => caseCells(d),
        onToggle: () => {},
        emptyMessage: chosenStatus
            ? "No cases with this result."
            : "Nothing outstanding in this file.",
    });

    renderPageFooter({
        container: "#fileCaseFooter",
        totalItems: sorted.length,
        pageSize: CASE_PAGE_SIZE,
        currentPage: page,
        showAll: caseShowAll,
        unit: "case",
        onPageChange: (p) => { casePage = p; renderCaseTable(); },
        onToggleAll: (all) => { caseShowAll = all; casePage = 1; renderCaseTable(); },
    });
}

/**
 * Every cell of one case row.
 *
 * The Ticket ID and Note cells are painted red by `lacksReason` — the same
 * predicate that drives the Missing reason button above them and the figure
 * `/api/summary` reports, so the cells and the count can never disagree about
 * which case owes an explanation.
 */
function caseCells(d) {
    const cell = (field, extra = "") => {
        const flag = (field === "ticket_id" || field === "note") && lacksReason(d) ? "flag" : "";
        const cls = [flag, extra].filter(Boolean).join(" ");
        const value = esc(d[field]);
        const title = extra.includes("clip") && value ? ` title="${value}"` : "";
        return `<td${cls ? ` class="${cls}"` : ""}${title}>${value}</td>`;
    };

    return cell("case_no", "mono clip clip-sm")
        + cell("sheet")
        + cell("scope")
        + cell("device")
        + `<td class="num">${d.row_num}</td>`
        + `<td><span class="badge" data-tone="${esc(toneFor(d.status))}">${esc(d.result)}</span></td>`
        + cell("test_date", "mono")
        + cell("pic")
        + cell("ticket_id", "mono")
        + cell("note", "clip");
}
