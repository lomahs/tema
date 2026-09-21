/**
 * Every DOM write Summary makes: the bucket cards, their scope tabs, the
 * tables and their footers, and the column alignment pass.
 *
 * Reads `state.js` and, for a bucket's rows and its scope groups, `buckets.js`.
 * Nothing here decides which rows belong to a bucket — that is `buckets.js`'s
 * job — and nothing here fetches.
 *
 * Unlike Detail's split, nothing here has to reach back into `index.js`: the
 * event handlers that call `render()` again (a filter chip's ×, a page change)
 * are themselves defined inside `render()` and `renderFooter()`, in this same
 * module, so they call the local `render` directly rather than through a
 * callback. `buckets.js` never calls anything in this file at all, so there is
 * no cycle for a hook to break — the callback seam Detail's split needed
 * between its `filters.js` and `render.js` has no counterpart here.
 */
import { $, $$, esc } from "../../dom.js";
import { renderGroupedTable } from "../../groupedTable.js";
import { renderPageFooter } from "../../pagination.js";
import { makeSortable, paintSortIndicators, sortableTh, sortRows } from "../../sorting.js";
import {
    getCountedStatuses, getStatuses, isExcluded, statusCells, statusHeadCells,
    sumRows,
} from "../../taxonomy.js";
import { executedPct, progressBar, scopeProgress } from "../summaryOverview.js";
import { bucketRows, filtered, groupsOf, pressedScopes } from "./buckets.js";
import {
    BUCKETS, GROUPINGS, PAGE_SIZE, chosenScopes, getGrouping, paging, sort,
    noExpansion,
} from "./state.js";

/**
 * What a card's dropped columns hold, when they hold anything.
 *
 * Summary draws only the counted statuses, so a case classified Out Of Scope or
 * Other has no column here. Silently is the one way it must not go: `Other` is
 * the fallback, which is where a misspelt Result string lands, and a typo that
 * vanishes from the main screen *and* from the total is the precise silence
 * the fallback exists to prevent.
 *
 * So the count comes back as a chip on the heading — `chip--aside`, the same
 * dashed treatment as the scope group that is reported but not counted, and
 * the same thing it means. It costs no column width and it is absent entirely
 * when the dropped columns are empty, which on a clean load is always. The
 * per-status breakdown rides in the title, and the file page still draws every
 * status a card.
 *
 * @param {Object[]} rows One scope group's rows.
 * @returns {string} HTML, or "" when nothing was dropped.
 */
function asideChip(rows, bucketKey) {
    const hidden = getStatuses().filter((s) => isExcluded(s.key));
    if (!hidden.length) return "";

    const totals = sumRows(rows);
    const held = hidden.filter((s) => totals[s.key]);
    const n = held.reduce((a, s) => a + totals[s.key], 0);
    if (!n) return "";

    // Each figure is a door, because this chip is the only place these statuses
    // appear on this screen at all: the band is drawn `counted`, so Out Of Scope
    // has no column here to click. Without this, the one status the reader
    // cannot reach from Summary would be the one deliberately set aside.
    const breakdown = held.map((s) =>
        `<button type="button" class="cell-link" data-status="${esc(s.key)}"`
        + ` data-bucket="${esc(bucketKey)}" title="List the ${esc(s.label)} cases">`
        + `${esc(s.label)}: ${totals[s.key]}</button>`).join(" · ");
    return `<span class="chip chip--aside" title="Outside the total, and not given a column here">`
        + `${breakdown} · ${n} not counted</span>`;
}

/**
 * A bucket's scope tabs: one per group in it, multi-select.
 *
 * Drawn only where there is a choice to make. With one group in the bucket the
 * strip would be a single tab that can only be pressed or else empty the table
 * it sits above, which is a control that asks a question with one answer.
 *
 * The figure on each tab counts that group under the shared Device/File
 * filters but *not* under the scope choice — a tab is how you pick a scope, so
 * its count has to say how much there is to pick, exactly as Review's status
 * cards count over `conditioned`.
 *
 * It is a tab bar rather than the pill strip Review draws, and deliberately so:
 * these sit on the head rule of the table they narrow, so the pressed ones read
 * as the heading of the rows beneath them rather than as a control floating
 * above. Review's pills are the same *question* asked of a screen with no such
 * rule to sit on, which is why the two no longer share a code shape.
 *
 * Selection is ink — an underline, ink text and a filled box. The design canvas
 * this came from marks it in its green, which is a few degrees from OK's own,
 * and colour on this screen means status.
 *
 * `All` presses every group in the bucket and reads pressed only when they all
 * are. It has no "off", the convention Review's leading pill uses: a control
 * whose only effect is to empty the table is not worth offering.
 *
 * @param {Object} bucket
 * @param {Object[]} rows Every row under the shared filters.
 * @returns {string} HTML, or "" when the bucket holds a single group.
 */
function scopeTabs(bucket, rows) {
    const groups = groupsOf(bucket);
    if (groups.length < 2) return "";

    const total = (key) => rows.filter((r) => r.scope === key)
        .reduce((n, r) => n + (r.total || 0), 0);

    // The box is `aria-hidden`: it is the pressed state drawn, and the button
    // already announces that through `aria-pressed`.
    const box = `<span class="scope-tab-box" aria-hidden="true">✓</span>`;

    return `<div class="scope-tabs" role="group" aria-label="Scope groups">
        <button type="button" class="scope-tab scope-tab--all"
                data-scope-all="${bucket.key}"
                aria-pressed="${groups.every((g) => chosenScopes.has(g.key))}">
            ${box}<span class="scope-tab-label">All</span>
        </button>
        ${groups.map((g) => `
            <button type="button" class="scope-tab"
                    data-scope-tab="${esc(g.key)}"
                    aria-pressed="${chosenScopes.has(g.key)}">
                ${box}
                <span class="scope-tab-label">${esc(g.label)}</span>
                <span class="scope-tab-count num">${total(g.key).toLocaleString()}</span>
            </button>`).join("")}
    </div>`;
}

/** The chips describing what is filtered out, and how to put it back. */
function chips() {
    const active = [
        { sel: "#summaryFilterDevice", label: "Device" },
        { sel: "#summaryFilterFile", label: "File" },
    ].filter(({ sel }) => $(sel).value);

    if (!active.length) return "";

    return `<div class="chips">
        <span class="eyebrow">Filtered</span>
        ${active.map(({ sel, label }) => `<span class="chip">
            ${esc(label)}: ${esc($(sel).value)}
            <button type="button" data-clear="${esc(sel)}" aria-label="Remove filter">×</button>
        </span>`).join("")}
        <button type="button" class="btn btn-quiet btn-sm" id="btnClearSummaryChips">Clear all</button>
    </div>`;
}

/**
 * Build every card: markup first, then bodies.
 *
 * The whole container is replaced on each render, which is what lets
 * `makeSortable` bind here without stacking a second listener on a header that
 * outlived the last draw — the old headers are gone with their listeners.
 */
export function render() {
    const container = $("#summaryTables");
    const rows = filtered();

    $("#btnSummaryGrouping").textContent =
        GROUPINGS.find((g) => g.key === getGrouping()).label;

    // An empty bucket is not drawn: a team with no work outside the plan should
    // not have to scroll past an empty Out Scope table to reach its figures. A
    // bucket whose groups are all unpressed is empty for a different reason, so
    // it keeps its card — hiding the table you just emptied would take its
    // scope cards away with it and leave no way to press them again.
    const present = BUCKETS
        .map((bucket) => ({
            bucket,
            groups: groupsOf(bucket),
            rows: bucketRows(bucket, rows),
        }))
        .filter((p) => p.groups.length
            && (p.rows.length || p.groups.some((g) => !chosenScopes.has(g.key))));

    if (!present.length) {
        container.innerHTML = `<p class="empty-note">No test cases match these filters.</p>`;
        return;
    }

    // Addressed by position, not by bucket key, for the reason it was not
    // addressed by scope key: an id and a selector round trip want something
    // that never needs escaping.
    container.innerHTML = chips() + present.map(({ bucket, groups, rows: r }, i) => {
        // The tabs sit *on* the head's rule, so the head gives that rule up —
        // a strip drawn under a head that kept its own border would stack two
        // lines a couple of pixels apart.
        const tabs = scopeTabs(bucket, rows);
        return `
        <section class="card card--table">
            <div class="card-head card-head--row${tabs ? " card-head--tabbed" : ""}">
                <h2>${esc(bucket.title ?? groups[0].label)}</h2>
                <!-- A bucket outside the plan says so on its own heading. Its
                     table and its bar are drawn in full — the count has to stay
                     visible — but nothing in it reaches the figures above, and
                     a reader comparing the two would otherwise find them short
                     by this table with nothing on screen explaining why. The
                     dashed rule is the one the band draws where a status
                     column stops counting. -->
                ${groups.every((g) => g.counted === false)
                    ? `<span class="chip chip--aside" title="Reported, but not counted toward the totals above">Not in total</span>`
                    : ""}
                <!-- And what this card's dropped columns hold, if anything. -->
                ${asideChip(r, bucket.key)}
                <!-- Each bucket carries its own bar: a commitment running behind
                     is a fact the combined figure above would hide. -->
                ${scopeProgress(r)}
                <!-- The design's right-hand summary. How many scopes are
                     pressed belongs beside the row count rather than in a
                     second element: both answer "what am I looking at", and
                     only the strip below can change either of them. -->
                <span class="count">${r.length} row${r.length === 1 ? "" : "s"}${
                    tabs ? ` · ${pressedScopes(bucket.key).length} of ${groups.length} scopes` : ""}</span>
            </div>
            ${tabs}
            <div class="scroll-x scroll-x--flush scroll-x--rows">
                <table class="ledger">
                    <thead><tr id="summaryHead-${i}"></tr></thead>
                    <tbody id="summaryBody-${i}"></tbody>
                    <tfoot id="summaryFoot-${i}"></tfoot>
                </table>
            </div>
            <div class="card-foot" id="summaryFooter-${i}"></div>
        </section>`;
    }).join("");

    container.querySelectorAll("[data-clear]").forEach((b) =>
        b.addEventListener("click", () => {
            $(b.dataset.clear).value = "";
            paging.clear();
            render();
        }));
    const clearAll = $("#btnClearSummaryChips");
    if (clearAll) clearAll.addEventListener("click", () => $("#btnClearSummaryFilters").click());

    present.forEach(({ bucket, rows: r }, i) => renderTable(i, bucket, r));
    alignColumns();
}

/**
 * Give every scope group's table the same column widths.
 *
 * Each card is its own `<table>`, so a browser sizes each one to its own
 * content: FPT's File column is as wide as FPT's longest file name and JP's is
 * as wide as JP's. The status bands then start at different offsets and stop
 * lining up down the page — and the whole reason these are separate tables is
 * that a reader compares them, which means reading down a column.
 *
 * So: let the browser size them naturally, measure what each column came out
 * as, take the widest across the cards and pin every table to it. Measuring
 * rather than choosing widths is what keeps this honest when the taxonomy
 * changes — a status added in the Config view widens its column here the same
 * way it widens a single table, and nothing has to be told how wide a column
 * called "Pending (保留)" is.
 *
 * Pinning needs `table-layout: fixed`, under which the first row's widths
 * govern the whole table, so the header cells are the only ones set. The
 * container is rebuilt on every `render`, so the measurement is always of
 * freshly auto-sized tables and never of the last pass's pinned ones.
 *
 * It runs for a single card too. Aligning is only half of what it does — the
 * other half is `fitToPane`, which is what keeps the table inside the page, and
 * one table can overflow its pane exactly as two can.
 *
 * A hidden view measures as zero — `render` runs before `showView` on the load
 * path — so this bails rather than pinning every column to nothing, and
 * `main.js` calls `alignSummaryColumns` when the view is shown. That is the
 * same arrangement `resizeCharts` needs and for the same reason.
 */
export function alignColumns() {
    const tables = [...$$("#summaryTables table.ledger")];
    if (!tables.length) return;
    if (!tables[0].offsetParent) return;   // hidden: nothing has a width yet

    const widths = [];
    tables.forEach((table) => {
        [...table.tHead.rows[0].cells].forEach((cell, i) => {
            widths[i] = Math.max(widths[i] || 0, Math.ceil(cell.getBoundingClientRect().width));
        });
    });

    fitToPane(widths, tables[0].parentElement.clientWidth);

    const total = widths.reduce((a, w) => a + w, 0);
    tables.forEach((table) => {
        table.style.tableLayout = "fixed";
        // Stated explicitly: a fixed-layout table left to size itself is not
        // obliged to add its columns up, and the pane's `overflow` still wants
        // something definite to decide whether it has to scroll.
        table.style.width = `${total}px`;
        [...table.tHead.rows[0].cells].forEach((cell, i) => {
            cell.style.width = `${widths[i]}px`;
        });
    });
}

/**
 * Which columns may give, in the order they are asked, and how far each may be
 * squeezed before it stops giving.
 *
 * A table wider than its pane scrolls sideways, and a horizontal scrollbar
 * under a band of figures is the one thing that stops you reading down a
 * column — which is the whole reason these columns were aligned to begin with.
 * So the table is fitted to the page, and something has to give. The order is
 * what decides *what*, and the band is asked first on purpose:
 *
 * 1. The status band. These columns are as wide as their *headings*, not their
 *    figures — "Pending (保留)" against a one-digit count — so most of that
 *    width is whitespace, and `.ledger th.band` already sets `white-space:
 *    normal` so a heading wraps rather than clips. Squeezing here costs a line
 *    of header height. The floor is the room a six-figure count needs, which
 *    is the point where squeezing would start costing a figure instead.
 * 2. The two columns of freehand text and the progress bar. A file name that
 *    runs out of room ellipsizes — recoverable from the cell's title, but only
 *    by hovering it, so this is asked second rather than first.
 * 3. The band again, down to what a four-figure count needs. This is the last
 *    resort on a genuinely narrow window, where the choice is between a
 *    heading wrapping onto a third line and a sideways scrollbar. Kept apart
 *    from the first tier so that a wide screen never reaches it: the band
 *    settles at a comfortable width long before anything is this tight.
 *
 * Surplus goes the other way round, and to the File column alone. A wide
 * screen spent on whitespace around two-digit numbers is a wide screen wasted,
 * and of the three columns that hold text, File is the only one that can spend
 * the room: Device names are short, and Executed holds a bar whose width is
 * declared. See `fitToPane`.
 *
 * @param {number} n The column count: File, Device, the band, then Executed.
 * @returns {{i: number, floor: number}[][]}
 */
function giveTiers(n) {
    const band = (floor) => {
        const cols = [];
        for (let i = 2; i < n - 1; i += 1) cols.push({ i, floor });
        return cols;
    };
    return [
        band(64),
        [{ i: 0, floor: 240 }, { i: 1, floor: 80 }, { i: n - 1, floor: 110 }],
        band(52),
    ];
}

/** The Executed column's declared width, read from the token that sets it. */
function progressWidth() {
    const declared = getComputedStyle(document.documentElement)
        .getPropertyValue("--progress-w");
    return parseInt(declared, 10) || 0;
}

/**
 * Stretch or squeeze `widths` in place so the row fits `available`.
 *
 * The measured widths are what the columns *want*; this is what there is room
 * for. Within a tier the change is shared in proportion to what each column
 * already has, so the widest gives — or takes — the most.
 *
 * If every tier is at its floor and it still does not fit, the pane scrolls:
 * at that point there genuinely is no room, and the alternative is clipping
 * the figures themselves.
 *
 * @param {number[]} widths Measured column widths, mutated in place.
 * @param {number} available The pane's content width.
 */
function fitToPane(widths, available) {
    if (!available || widths.length < 3) return;

    // Auto layout inflates the last column to soak up whatever slack the table
    // had, which is how Executed ends up half as wide again as the width it
    // declares. Held to that width first, so the squeeze below is spent on
    // columns that actually need the room.
    const declared = progressWidth();
    const last = widths.length - 1;
    if (declared) widths[last] = Math.min(widths[last], declared);

    const tiers = giveTiers(widths.length)
        .map((tier) => tier.filter((c) => c.i >= 0 && c.i < widths.length))
        .filter((tier) => tier.length);

    let slack = available - widths.reduce((a, w) => a + w, 0);
    // A surplus goes to the File column and nowhere else.
    //
    // Sharing it across the text tier in proportion to current width sounds
    // fair and is not: Executed is the widest of the three, so it took the
    // largest share of every wide screen — and it holds a bar and a percentage
    // whose size is declared, so the extra room did nothing at all. Device
    // names are short. File names run past fifty characters and ellipsize.
    // Only one of the three can spend the room, so only it is offered it.
    const asked = slack > 0
        ? [tiers[1].filter((c) => c.i === 0)].filter((t) => t.length)
        : tiers;

    asked.forEach((tier) => {
        // More than one pass: a column that reaches its floor stops absorbing,
        // and what it could not take is offered to the rest of its tier rather
        // than quietly dropped.
        for (let pass = 0; pass < 4 && Math.round(slack) !== 0; pass += 1) {
            const open = tier.filter((c) => slack > 0 || widths[c.i] > c.floor);
            const pool = open.reduce((a, c) => a + widths[c.i], 0);
            if (!open.length || !pool) break;

            const before = slack;
            open.forEach((c) => {
                const want = widths[c.i] + (widths[c.i] / pool) * before;
                const got = Math.max(c.floor, Math.round(want));
                slack -= got - widths[c.i];
                widths[c.i] = got;
            });
            if (slack === before) break;   // nothing moved; no point going again
        }
    });

    // Rounding each share to a whole pixel leaves a pixel or two of drift, and
    // a table one pixel wider than its pane is still a table with a scrollbar.
    // Take the remainder off whichever column has the most room above its
    // floor, which is the one least likely to notice losing it.
    const spare = (c) => widths[c.i] - c.floor;
    const columns = tiers.flat();
    let over = widths.reduce((a, w) => a + w, 0) - available;
    while (over > 0) {
        const roomiest = columns.reduce((a, c) => (spare(c) > spare(a) ? c : a), columns[0]);
        if (!roomiest || spare(roomiest) <= 0) break;   // nothing left to give
        const take = Math.min(over, spare(roomiest));
        widths[roomiest.i] -= take;
        over -= take;
    }
}

/**
 * Fill one scope group's header, body, totals row and footer.
 *
 * @param {number} i The card's position among the drawn tables.
 * @param {Object} bucket
 * @param {Object[]} rows That bucket's rows, merged but unsorted.
 */
function renderTable(i, bucket, rows) {
    const head = `#summaryHead-${i}`;
    $(head).innerHTML =
        sortableTh("file", "File")
        + sortableTh("device", "Device")
        // Counted statuses only. Everywhere else draws the full band; this is
        // the one screen that cannot afford it. The columns it drops hold
        // nothing that enters the sum, and the room they free buys the File
        // column the width a fifty-character workbook name actually needs.
        // What those columns do hold is reported by `asideChip` on the card
        // heading, so the count never leaves the screen altogether.
        + statusHeadCells(sortableTh, { counted: true })
        // Not sortable, deliberately: it is a redrawing of the band beside it,
        // so a reader who wants that order has Total and the status columns.
        + `<th class="progress-col">Executed</th>`;
    // Every table re-renders, not just the one clicked: the sort state is shared,
    // so leaving the others alone would show two different orders at once.
    makeSortable(`${head} th.sortable`, sort, render);
    paintSortIndicators(`${head} th.sortable`, sort);

    const numeric = new Set(["total", ...getStatuses().map((s) => s.key)]);
    const sorted = sortRows(rows, sort, numeric);

    const state = paging.get(bucket.key) || { page: 1, showAll: false };
    const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
    const page = Math.min(Math.max(1, state.page), pageCount);
    const visible = state.showAll
        ? sorted
        : sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    renderGroupedTable({
        container: `#summaryBody-${i}`,
        rows: visible,
        totalCols: 4 + getCountedStatuses().length,
        expanded: noExpansion,
        // Every row stands on its own: both identity columns are filled in, so
        // a copied selection is complete without the header above it.
        // The file name is the way into that workbook's own page. A name is
        // plain text with no separator to lose, so unlike a group path it can
        // ride in the attribute; `esc` covers the quoting.
        renderLabelCells: (r) =>
            `<td><button type="button" class="cell-link" data-file="${esc(r.file)}"`
            + ` title="Open ${esc(r.file)}">${esc(r.file)}</button></td>`
            // Titled because the column is fitted to the page and a long device
            // name ellipsizes; the File cell's own title covers the same thing.
            + `<td title="${esc(r.device)}">${esc(r.device)}</td>`,
        labelCols: 2,
        renderValues: (r) => statusCells(r, {
            blankZeros: true, counted: true, link: linkFor(r, bucket.key),
        }) + progressCell(r),
        onToggle: () => {},
        emptyMessage: "No test cases loaded.",
    });

    // The footer totals **every** row in the bucket, not the visible page — it
    // answers "where does this bucket stand", which paging must not change.
    const totals = sumRows(sorted);
    // The footer totals this group under whatever the shared filters are set to,
    // so its figures lead to the same narrowing rather than to the whole group.
    $(`#summaryFoot-${i}`).innerHTML =
        `<tr><td colspan="2">Total</td>${statusCells(totals, {
            counted: true,
            link: {
                bucket: bucket.key,
                file: $("#summaryFilterFile").value,
                device: $("#summaryFilterDevice").value,
            },
        })}`
        + `${progressCell(totals)}</tr>`;

    renderFooter(i, bucket, sorted.length, page, pageCount, state.showAll);
}

/**
 * What a row's status figure leads to, which is what the Rows setting made it.
 *
 * Split rows name one device, so the drill-in names it too. "By device type"
 * rows name a family — several device names merged — so they hand over the
 * family, which rides on each case for exactly this reason rather than being
 * re-derived from the substring rules in JavaScript. A Combined row is every
 * device of that file, so it names none and the file plus the scope group is
 * already the whole of it.
 *
 * @param {Object} r A row at the current granularity.
 * @param {string} scopeKey The scope group whose card it is drawn in.
 * @returns {Object} Context for `onDrillIn`.
 */
function linkFor(r, bucketKey) {
    // `bucket`, not `scope`: a row here is merged across whichever of the
    // bucket's groups are pressed, so no single scope key describes it — and a
    // bucket key is one of this module's own literals, which a `data-`
    // attribute can carry safely. The click handler turns it back into the
    // pressed scope keys.
    if (getGrouping() === "combined") return { file: r.file, bucket: bucketKey };
    if (getGrouping() === "family") {
        return { file: r.file, device_family: r.device_family, bucket: bucketKey };
    }
    return { file: r.file, device: r.device, bucket: bucketKey };
}

/**
 * The Executed cell: the row's own progress bar, and the percentage beside it.
 *
 * The same `progressBar` the overview and the scope headings use, so a row, its
 * group and the whole load are all painted by one function.
 *
 * @param {Object} row A summary row, or a totals object.
 * @returns {string} HTML.
 */
function progressCell(row) {
    if (!row.total) return `<td class="progress-col"></td>`;
    return `<td class="progress-col"><span class="progress-cell">`
        + progressBar(row, "progress--sm")
        + `<span class="num">${executedPct(row)}%</span>`
        + `</span></td>`;
}

/**
 * One card's footer, from the shared widget.
 *
 * Review draws the same thing, so the markup and the paging arithmetic live in
 * `pagination.js` rather than here — two footers that drifted would be two
 * different answers to "is this all of it".
 */
function renderFooter(i, bucket, count, page, pageCount, showAll) {
    const state = () => paging.get(bucket.key) || { page: 1, showAll: false };
    renderPageFooter({
        container: `#summaryFooter-${i}`,
        totalItems: count,
        pageSize: PAGE_SIZE,
        currentPage: page,
        showAll,
        unit: "file",
        onPageChange: (p) => { paging.set(bucket.key, { ...state(), page: p }); render(); },
        onToggleAll: (all) => { paging.set(bucket.key, { page: 1, showAll: all }); render(); },
    });
}
