/**
 * The one table of the loaded source's workbooks.
 *
 * Two panels have something to say about the same list of files: `sourcePanel`
 * knows what each one contributed to the load, `preparePanel` knows what state
 * its TOOL_DATA sheet is in and what may be done to it. They used to say it in
 * two tables, one under the other, listing the same files twice.
 *
 * So this is a self-contained widget in the mould of `pagination.js` and
 * `groupedTable.js`: it **imports no panel module**, both panels feed it, and
 * it reports a pressed action back through `onAction`. That is what lets the
 * two sections merge without either panel learning the other exists.
 *
 * The two halves arrive separately and out of order — the load results land the
 * moment `/api/load` answers, the workbook states one round trip later — so
 * each is stored as it comes and the table redraws from whatever it has. A file
 * present in only one of them still gets a row; being listed by the loader but
 * not by the prepare scan (or the reverse) is exactly the kind of thing worth
 * seeing rather than hiding.
 */
import { $, esc } from "./dom.js";

let wrapper, body;

/** Called with `(path, action)` when a row button is pressed. */
let onAction = () => {};

/** `/api/load`'s per-file results, keyed by path. */
let loadResults = new Map();

/** `/api/prepare/files`' entries, keyed by path. */
let prepareFiles = new Map();

/**
 * Whether the action buttons are live.
 *
 * They act on the *source* files, so they mean nothing until a load has
 * succeeded — the same condition that used to hide the prepare section.
 */
let actionsEnabled = false;

/**
 * Wire up the table. Call once, at startup.
 * @param {Object} opts
 * @param {(path: string, action: "tool-data"|"clear") => void} opts.onAction
 */
export function initFilesTable({ onAction: action }) {
    wrapper = $("#sourceFilesWrapper");
    body = $("#sourceFilesBody");
    onAction = action;

    // One listener for the whole table: the rows are redrawn on every refresh.
    body.addEventListener("click", (event) => {
        const btn = event.target.closest("button[data-act]");
        if (!btn || btn.disabled) return;
        // The path is read out of a render-local array rather than a `data-`
        // attribute, the same rule the grouped tables follow: an attribute is
        // not a lossless channel, and a path is the one thing here that has to
        // survive a click intact.
        const entry = rows()[Number(btn.dataset.row)];
        if (entry) onAction(entry.path, btn.dataset.act);
    });
}

/**
 * Report what each workbook contributed to the load.
 * @param {Array<{file: string, path: string, status: string, cases?: number,
 *   error?: string}>} results
 */
export function setLoadResults(results) {
    loadResults = new Map((results || []).map((r) => [r.path, r]));
    render();
}

/**
 * Report each workbook's TOOL_DATA state.
 * @param {Array<{file: string, path: string, has_tool_data: boolean,
 *   blocks: ?number, error?: string}>} files
 */
export function setPrepareFiles(files) {
    prepareFiles = new Map((files || []).map((f) => [f.path, f]));
    render();
}

/**
 * Turn the row actions on or off.
 * @param {boolean} enabled
 */
export function setActionsEnabled(enabled) {
    actionsEnabled = enabled;
    render();
}

/** Empty the table — a load that failed has nothing to show for itself. */
export function clearFilesTable() {
    loadResults = new Map();
    prepareFiles = new Map();
    render();
}

/**
 * The merged list, in load order first so the table keeps the order the loader
 * reported; anything only the prepare scan knows about follows.
 * @returns {Array<{path: string, file: string, load: ?Object, prepare: ?Object}>}
 */
function rows() {
    const paths = [...loadResults.keys()];
    prepareFiles.forEach((_, path) => { if (!loadResults.has(path)) paths.push(path); });

    return paths.map((path) => {
        const load = loadResults.get(path) || null;
        const prepare = prepareFiles.get(path) || null;
        return { path, file: (load || prepare).file, load, prepare };
    });
}

/** The Status / Cases pair, for a file the loader may not have reached. */
function loadCells(load) {
    if (!load) {
        return `<td class="muted">—</td><td class="num muted">—</td>`;
    }
    const cls = load.status === "OK" ? "is-ok" : "is-error";
    return `<td class="${cls}">${esc(load.status)}</td>`
         + `<td class="num">${load.cases != null ? load.cases : "—"}</td>`;
}

/** What the workbook's TOOL_DATA sheet looks like, in one cell. */
function toolDataCell(prepare) {
    if (!prepare) return `<td class="muted">—</td>`;
    if (prepare.error) return `<td class="is-error">${esc(prepare.error)}</td>`;
    if (!prepare.has_tool_data) return `<td class="muted">none</td>`;
    return `<td><span class="mono">${prepare.blocks}`
         + ` block${prepare.blocks === 1 ? "" : "s"}</span></td>`;
}

/**
 * The two buttons, for one row.
 *
 * A workbook with no TOOL_DATA cannot be cleared — nothing says which cells
 * hold results — and neither button means anything before a load, because the
 * list they act on is the loaded source's.
 */
function actionCell(prepare, index) {
    if (!prepare) return `<td class="actions muted">—</td>`;

    const described = prepare.has_tool_data;
    const off = actionsEnabled ? "" : " disabled";
    const noSheet = described ? "" : ' disabled title="Needs a TOOL_DATA sheet first"';

    return `<td class="actions">
        <button type="button" class="btn btn-sm" data-act="tool-data" data-row="${index}"${off}>
            ${described ? "Check TOOL_DATA" : "Create TOOL_DATA"}
        </button>
        <button type="button" class="btn btn-sm" data-act="clear" data-row="${index}"${off || noSheet}>
            Clear results
        </button>
    </td>`;
}

/** Draw the table, or hide it when there is nothing in it. */
function render() {
    const entries = rows();
    wrapper.hidden = entries.length === 0;

    body.innerHTML = entries.map((entry, index) => `<tr>
        <td class="num muted">${index + 1}</td>
        <td class="clip" title="${esc(entry.path)}">${esc(entry.file)}</td>
        ${loadCells(entry.load)}
        ${toolDataCell(entry.prepare)}
        ${actionCell(entry.prepare, index)}
        <td>${entry.load && entry.load.error ? esc(entry.load.error) : ""}</td>
    </tr>`).join("");
}
