/**
 * Rows nested into expandable groups, with rolled-up parents.
 *
 * Deliberately knows nothing about any view: the caller passes its rows, its
 * grouping keys and its own expansion state in, and reacts through `onToggle`.
 * Keeping the dependency one-way is what stops a cycle between this module and
 * the views that use it — the same arrangement `pagination.js` uses.
 *
 * Two shapes of group row are supported, because the two kinds of table in this
 * app want different things:
 *
 * - `mode: "values"` — the group row carries the same numeric columns as its
 *   children, filled from `aggregate(descendants)`. Summary and Daily use this.
 * - `mode: "span"` — the group row is a single full-width band naming the group
 *   and a count. Detail uses this, because a group of cases has no meaningful
 *   "sum" to show in a Ticket ID column.
 */
import { $, esc } from "./dom.js";

/** Separator for composing a group path. A NUL cannot occur in a cell value. */
const SEP = "\u0000";

/**
 * @typedef {Object} GroupNode
 * @property {false} leaf
 * @property {string} label
 * @property {number} depth
 * @property {string} path
 * @property {Object[]} rows Every descendant leaf row.
 * @property {Array<GroupNode|LeafNode>} children
 *
 * @typedef {Object} LeafNode
 * @property {true} leaf
 * @property {Object} row
 */

/**
 * Bucket `rows` by each grouping key in turn, preserving the order they arrive
 * in — the caller has already sorted them, and re-sorting here would silently
 * override that.
 *
 * @param {Object[]} rows
 * @param {string[]} groupBy
 * @param {(row: Object, key: string) => string} labelOf
 * @param {number} depth
 * @param {string} prefix
 * @returns {Array<GroupNode|LeafNode>}
 */
function buildTree(rows, groupBy, labelOf, depth, prefix) {
    if (depth >= groupBy.length) return rows.map((row) => ({ leaf: true, row }));

    const key = groupBy[depth];
    const buckets = new Map();
    rows.forEach((row) => {
        const label = String(labelOf(row, key) ?? "");
        if (!buckets.has(label)) buckets.set(label, []);
        buckets.get(label).push(row);
    });

    return [...buckets.entries()].map(([label, group]) => {
        const path = prefix + SEP + label;
        return {
            leaf: false,
            label,
            depth,
            path,
            rows: group,
            children: buildTree(group, groupBy, labelOf, depth + 1, path),
        };
    });
}

/**
 * The path identifying a group, for seeding or checking expansion state.
 *
 * Views must build paths through here rather than concatenating labels
 * themselves — the separator is a NUL, which is easy to get wrong by hand.
 *
 * @param {...string} labels Group labels from the outermost inwards.
 * @returns {string}
 */
export function groupPath(...labels) {
    return labels.map((l) => SEP + String(l)).join("");
}

/**
 * Whether a group is open. An unvisited path takes the view's default, so a
 * fresh dataset does not arrive entirely collapsed.
 */
function isOpen(path, expanded, defaultExpanded) {
    if (expanded.has(path)) return true;
    if (expanded.has("!" + path)) return false;   // explicitly closed
    return defaultExpanded;
}

/**
 * Flip a path, recording the *explicit* state either way so the view default
 * stops applying to a group the reader has touched.
 *
 * @param {Set<string>} expanded Mutated in place.
 * @param {string} path
 * @param {boolean} defaultExpanded
 */
export function toggleGroup(expanded, path, defaultExpanded) {
    const open = isOpen(path, expanded, defaultExpanded);
    expanded.delete(path);
    expanded.delete("!" + path);
    expanded.add(open ? "!" + path : path);
}

/**
 * Open or close every group in one go.
 *
 * @param {Set<string>} expanded Mutated in place: cleared, then refilled.
 * @param {Object[]} rows
 * @param {string[]} groupBy
 * @param {(row: Object, key: string) => string} labelOf
 * @param {boolean} open
 */
export function setAllGroups(expanded, rows, groupBy, labelOf, open) {
    expanded.clear();
    const walk = (nodes) => nodes.forEach((n) => {
        if (n.leaf) return;
        expanded.add(open ? n.path : "!" + n.path);
        walk(n.children);
    });
    walk(buildTree(rows, groupBy, labelOf, 0, ""));
}

/**
 * Render rows into `container`, nested by `groupBy`.
 *
 * @param {Object} opts
 * @param {string} opts.container Selector for the `<tbody>` to fill.
 * @param {Object[]} opts.rows Leaf rows, already filtered and sorted.
 * @param {string[]} [opts.groupBy] Ordered grouping keys; empty renders flat.
 * @param {(row: Object, key: string) => string} [opts.labelOf] Group label for a
 *   row; defaults to reading the key straight off the row.
 * @param {(rows: Object[]) => Object} [opts.aggregate] Roll-up for a group row
 *   in `"values"` mode.
 * @param {(row: Object, index: number) => string} opts.renderValues Cells after
 *   the label columns, for a leaf.
 * @param {(row: Object) => string} [opts.renderLabelCells] The leading label
 *   cells for a leaf; must emit exactly `labelCols` of them.
 * @param {(row: Object, index: number) => string} [opts.leafAttrs] Extra
 *   attributes for a leaf `<tr>` — how a caller keeps its rows clickable when
 *   they sit under group rows.
 * @param {number} [opts.labelCols] How many leading columns the label occupies.
 * @param {number} opts.totalCols Column count, for colspans.
 * @param {Set<string>} opts.expanded Expansion state, owned by the caller.
 * @param {boolean} [opts.defaultExpanded] What an untouched group does.
 * @param {"values"|"span"} [opts.mode]
 * @param {(rows: Object[]) => string} [opts.summarise] Right-hand text on a
 *   `"span"` group row.
 * @param {(path: string) => void} opts.onToggle
 * @param {string} [opts.emptyMessage] Shown when there is nothing to draw.
 */
export function renderGroupedTable({
    container, rows, groupBy = [], labelOf, aggregate, renderValues,
    renderLabelCells, leafAttrs, labelCols = 1, totalCols, expanded,
    defaultExpanded = true, mode = "values", summarise, onToggle,
    emptyMessage = "Nothing to show.",
}) {
    const body = $(container);
    const label = labelOf || ((row, key) => row[key]);

    if (!rows.length) {
        body.innerHTML = `<tr class="empty-row"><td colspan="${totalCols}">${esc(emptyMessage)}</td></tr>`;
        return;
    }

    const html = [];
    let index = 0;

    // Group identities never touch the DOM. An attribute value is not a
    // lossless channel — the HTML tokenizer rewrites U+0000 to U+FFFD, and
    // a path that comes back changed silently fails to match the expansion
    // state, which looks exactly like a chevron that does nothing. So the
    // markup carries an index into this array and nothing else.
    const paths = [];

    const twisty = (open) =>
        `<button class="twisty" aria-expanded="${open}">${open ? "▾" : "▸"}</button>`;

    const walk = (nodes) => nodes.forEach((node) => {
        if (node.leaf) {
            const labels = renderLabelCells
                ? renderLabelCells(node.row)
                : `<td class="cell-label"><span class="twisty twisty--leaf"></span>${esc(node.row[groupBy[0]])}</td>`;
            const attrs = leafAttrs ? " " + leafAttrs(node.row, index) : "";
            html.push(`<tr${attrs}>${labels}${renderValues(node.row, index++)}</tr>`);
            return;
        }

        const open = isOpen(node.path, expanded, defaultExpanded);
        const style = ` style="--depth:${node.depth}"`;

        const gid = paths.push(node.path) - 1;

        if (mode === "span") {
            html.push(
                `<tr data-depth="${node.depth}" data-group="${gid}"${style}>`
                + `<td class="cell-label" colspan="${totalCols}">${twisty(open)}${esc(node.label)}`
                + `<span class="muted mono"> ${esc(summarise ? summarise(node.rows) : "")}</span>`
                + `</td></tr>`);
        } else {
            html.push(
                `<tr data-depth="${node.depth}" data-group="${gid}"${style}>`
                + `<td class="cell-label" colspan="${labelCols}">${twisty(open)}${esc(node.label)}</td>`
                + renderValues(aggregate(node.rows), -1)
                + `</tr>`);
        }

        if (open) walk(node.children);
    });

    walk(buildTree(rows, groupBy, label, 0, ""));
    body.innerHTML = html.join("");

    body.querySelectorAll("tr[data-group]").forEach((tr) => {
        const path = paths[Number(tr.dataset.group)];
        const fire = () => onToggle(path);
        tr.querySelector(".twisty").addEventListener("click", fire);
        // The whole group row is the target: a 12px chevron is a poor click area.
        tr.addEventListener("click", (e) => {
            if (e.target.closest(".twisty")) return;
            fire();
        });
    });
}
