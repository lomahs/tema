/**
 * Every DOM write Detail makes: the stat cards, the toggle strips, the table
 * and its footer.
 *
 * Reads `state.js` and, for the scope-card figures, `filters.js`'s
 * `countsByScope`. Nothing here decides what is in `allData` or `filtered` —
 * that is `filters.js`'s job — and nothing here fetches.
 *
 * A control rendered here can change what the screen shows in one of two ways,
 * and each goes through its own callback that `index.js` installs, because a
 * renderer that imported `index.js` to call back into it would be the cycle
 * Step 8 checks for: `onChanged` when only *which* of the cases in hand are
 * shown changes (a sort, a filter, a page), and `onReload` when *which cases
 * are in hand* changes (dropping a chosen status).
 */
import { $, esc } from "../../dom.js";
import { renderGroupedTable, toggleGroup } from "../../groupedTable.js";
import { renderPageFooter } from "../../pagination.js";
import { makeSortable, paintSortIndicators, sortableTh } from "../../sorting.js";
import {
    getStatuses, isExcluded, lacksReason, renderStatCards, sumRows, toneFor,
} from "../../taxonomy.js";
import { uniqueOf } from "../../filters.js";
import { countsByScope, groupBy } from "./filters.js";
import {
    COLUMNS, DATE_FILTERS, DEFAULT_EXPANDED, FILTERS, GROUP_PAGE_SIZE, PAGE_SIZE,
    chosenRawScopes, chosenScopes, chosenStatuses, detailSort, expanded,
    getAllData, getConditions, getCurrentPage, getFiltered, getLoading,
    getMissingOnly, getScopeGroups, getShowAll, getSummaryRows, setCurrentPage,
    setMissingOnly, setShowAll,
} from "./state.js";

/**
 * What to run when a control inside a rendered fragment changes the view.
 *
 * A callback rather than an import, for the reason `summaryOverview.js` takes
 * one: the renderer is below `index.js` in the dependency order, and reaching
 * up for `refresh` would make the two modules import each other.
 */
let onChanged = () => {};

/** Installed once by `initDetailView`. */
export function setOnChanged(fn) { onChanged = fn; }

/**
 * What to run when a control drops a chosen status: the cases in hand change,
 * not merely which of them are shown, so this reaches `rebuild` rather than
 * the narrower `onChanged`.
 */
let onReload = () => {};

/** Installed once by `initDetailView`. */
export function setOnReload(fn) { onReload = fn; }

/**
 * Update the stat figures and the "n / m cases" count.
 *
 * The status figures are counted over the **summary rows** of the pressed scope
 * groups, not over the cases: a status nobody has clicked has no cases here, and
 * a card reading 0 for it would be reporting the absence of a fetch as an
 * absence of work. What a card says is therefore how many cases pressing it
 * would list — which is what a control has to say to be worth pressing — and it
 * does not move when a File or a search narrows the table beneath it.
 */
export function renderStats() {
    const totals = sumRows(getSummaryRows().filter((r) => chosenScopes.has(r.scope)));

    const setStat = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = Number(value || 0).toLocaleString();
    };
    // Every status, including the excluded ones: this screen lists them, so
    // "All" has to count them. That makes this figure legitimately larger than
    // Summary's Total, which is the plan.
    setStat("statTotal", getStatuses().reduce((n, s) => n + (totals[s.key] || 0), 0));
    getStatuses().forEach((s) => setStat(`stat-${s.key}`, totals[s.key] || 0));
    // Files is a fact about what you are looking at, not about what you could
    // pick, so it alone counts the rows actually on screen.
    setStat("statFiles", new Set(getFiltered().map((d) => d.file_name)).size);

    $("#filteredCount").textContent = getFiltered().length === getAllData().length
        ? `${getFiltered().length.toLocaleString()} cases`
        : `${getFiltered().length.toLocaleString()} / ${getAllData().length.toLocaleString()} cases`;

    // How many conditions are folded away, on the button that folds them —
    // otherwise a closed panel hides the fact that the table is narrowed.
    const narrowing = FILTERS.filter(({ id }) => $("#" + id).value).length
        + DATE_FILTERS.filter(({ id }) => $("#" + id).value).length
        // However many scopes are pressed, they are one narrowing.
        + (chosenRawScopes.size ? 1 : 0)
        + (getConditions().deviceFamily ? 1 : 0)
        + (getConditions().sheet ? 1 : 0)
        + (getMissingOnly() ? 1 : 0)
        + ($("#detailGroupBy").value ? 1 : 0);
    $("#filterCount").textContent = narrowing ? String(narrowing) : "";
}

/**
 * One dismissible chip per active narrowing.
 *
 * A select showing "iPhone 15" does not say *which* dimension it narrows once
 * you have looked away, and the date bounds are easy to forget entirely. The
 * two conditions a drill-in can set have no control of their own, so a chip is
 * the only way to see — or undo — them.
 *
 * Status chips appear only when the choice is a strict subset: with every status
 * pressed they would be a row of eight chips saying nothing is narrowed.
 */
export function renderChips() {
    const chips = [];
    const push = (id, label, value) => {
        if (value) chips.push(`<span class="chip">${esc(label)}: ${esc(value)}`
            + `<button type="button" data-clear="${esc(id)}" aria-label="Clear ${esc(label)} filter">✕</button></span>`);
    };
    FILTERS.forEach(({ id, label }) => push(id, label, $("#" + id).value));
    // One chip per pressed scope rather than one listing them all, for the
    // reason the statuses get one each: any single one can then be dropped
    // without retyping the rest.
    [...chosenRawScopes].forEach((v) => chips.push(
        `<span class="chip">Scope: ${esc(v)}`
        + `<button type="button" data-scope-toggle="${esc(v)}"`
        + ` aria-label="Clear ${esc(v)} filter">✕</button></span>`));
    if (chosenStatuses.size < getStatuses().length) {
        // One chip per chosen status rather than one listing them all, so any
        // single one can be dropped without retyping the rest.
        getStatuses()
            .filter((st) => chosenStatuses.has(st.key))
            .forEach((st) => chips.push(
                `<span class="chip">Result: ${esc(st.label)}`
                + `<button type="button" data-status="${esc(st.key)}"`
                + ` aria-label="Clear ${esc(st.label)} filter">✕</button></span>`));
    }
    if (getConditions().deviceFamily) {
        chips.push(`<span class="chip">Device type: ${esc(getConditions().deviceFamily)}`
            + `<button type="button" data-condition="deviceFamily"`
            + ` aria-label="Clear Device type filter">✕</button></span>`);
    }
    if (getConditions().sheet) {
        chips.push(`<span class="chip">Sheet: ${esc(getConditions().sheet)}`
            + `<button type="button" data-condition="sheet"`
            + ` aria-label="Clear Sheet filter">✕</button></span>`);
    }
    DATE_FILTERS.forEach(({ id, label }) => push(id, label, $("#" + id).value));
    push("filterSearch", "Search", $("#filterSearch").value.trim());
    if (getMissingOnly()) {
        chips.push(`<span class="chip">Missing reason`
            + `<button type="button" data-missing="1"`
            + ` aria-label="Clear Missing reason filter">✕</button></span>`);
    }

    $("#detailChips").innerHTML = chips.join("");
    $("#detailChips").querySelectorAll("button[data-missing]").forEach((b) =>
        b.addEventListener("click", () => {
            setMissingOnly(false);
            paintMissingReason();
            setCurrentPage(1);
            onChanged();
        }));
    $("#detailChips").querySelectorAll("button[data-condition]").forEach((b) =>
        b.addEventListener("click", () => {
            getConditions()[b.dataset.condition] = "";
            setCurrentPage(1);
            onChanged();
        }));
    $("#detailChips").querySelectorAll("button[data-clear]").forEach((b) =>
        b.addEventListener("click", () => {
            $("#" + b.dataset.clear).value = "";
            setCurrentPage(1);
            onChanged();
        }));
    $("#detailChips").querySelectorAll("button[data-scope-toggle]").forEach((b) =>
        b.addEventListener("click", () => {
            chosenRawScopes.delete(b.dataset.scopeToggle);
            paintScopeToggles();
            // A narrowing, not a selection: nothing has to be fetched or rebuilt.
            setCurrentPage(1);
            onChanged();
        }));
    $("#detailChips").querySelectorAll("button[data-status]").forEach((b) =>
        b.addEventListener("click", () => {
            chosenStatuses.delete(b.dataset.status);
            paintResultToggles();
            // Dropping a status needs no fetch — the others are already here.
            onReload();
        }));
}

/**
 * Whether a row is a section heading inside the spreadsheet rather than a case.
 *
 * These carry a title in the Case no column — "[Login - normal case]" — and
 * nothing else. Scope being empty is what marks them, but that alone would also
 * excuse a real case whose Scope was genuinely forgotten, so it is paired with
 * "nothing has been recorded against this row". Flagging headings as errors
 * trains people to ignore the flag.
 *
 * @param {Object} d A case row.
 * @returns {boolean}
 */
function isSectionHeader(d) {
    return !d.scope && !d.result && !d.test_date && !d.pic;
}

/**
 * Bootstrap-free class flagging a cell that should have been filled in.
 *
 * Three different rules apply:
 * - identity fields are always mandatory;
 * - result/date/PIC are only expected once *any* of the three is filled, so an
 *   untested case is not flagged, but a half-recorded one is — unless the case
 *   is out of the plan, where the blank is the whole point rather than an
 *   omission (an Out Of Scope case is precisely one that names no PIC, so
 *   flagging that cell would mark every one of them as a mistake);
 * - ticket id and note are required together (either satisfies) for the
 *   statuses the config marks as needing a reason.
 *
 * @param {Object} d A case row.
 * @param {string} field
 * @returns {string} `"flag"` or an empty string.
 */
function cellCls(d, field) {
    if (isSectionHeader(d)) return "";
    const v = d[field];
    if (["case_no", "file_name", "sheet", "device", "scope"].includes(field)) {
        return v ? "" : "flag";
    }
    if (["result", "test_date", "pic"].includes(field)) {
        if (isExcluded(d.status)) return "";
        const has = [d.result, d.test_date, d.pic].filter(Boolean).length;
        return has > 0 && !v ? "flag" : "";
    }
    if (field === "ticket_id" || field === "note") {
        return lacksReason(d) ? "flag" : "";
    }
    return "";
}

/**
 * One `<td>` for a field, carrying its validation highlight.
 *
 * A clipped cell also gets the full value as its tooltip — truncation must not
 * be the same thing as losing the text.
 *
 * @param {Object} d
 * @param {string} field
 * @param {string} [extra] Extra classes.
 * @returns {string} HTML.
 */
function td(d, field, extra = "") {
    const cls = [cellCls(d, field), extra].filter(Boolean).join(" ");
    const value = esc(d[field]);
    const title = extra.includes("clip") && value ? ` title="${value}"` : "";
    return `<td${cls ? ` class="${cls}"` : ""}${title}>${value}</td>`;
}

/** Every cell of one case row. */
function caseCells(d, i) {
    return `<td class="num muted">${i + 1}</td>`
        + td(d, "file_name")
        + td(d, "sheet")
        + td(d, "device")
        + `<td class="num">${d.row_num}</td>`
        + td(d, "case_no", "mono clip clip-sm")
        + td(d, "scope")
        + `<td class="${cellCls(d, "result")}">`
        + `<span class="badge" data-tone="${esc(toneFor(d.status))}">${esc(d.result)}</span></td>`
        + td(d, "test_date", "mono")
        + td(d, "pic")
        + td(d, "ticket_id", "mono")
        + td(d, "note", "clip");
}

/**
 * What the table says when it has no rows to draw.
 *
 * Three different states look identical otherwise, and only one of them is
 * "there is nothing here": cases are still on their way, no status is chosen so
 * nothing was ever asked for, or the filters match nothing.
 *
 * @returns {string}
 */
function emptyMessage() {
    if (getLoading()) return "Loading cases…";
    if (!chosenStatuses.size) return "Pick a status above to list its cases.";
    if (!chosenScopes.size) return "Pick a scope above to list its cases.";
    return "No cases match these filters.";
}

/** The distinct top-level group values, in their sorted order. */
function groupValues(keys) {
    const seen = [];
    getFiltered().forEach((r) => {
        const v = String(r[keys[0]] ?? "");
        if (!seen.includes(v)) seen.push(v);
    });
    return seen;
}

/** Draw the current page, grouped or flat, plus its pager. */
export function renderTable() {
    const keys = groupBy();

    // Mid-fetch the rows on screen belong to the previous selection, so they are
    // cleared rather than left to look like the answer. `aria-busy` says so to a
    // screen reader, which a message in a table cell does not.
    $("#dataBody").closest("table").setAttribute("aria-busy", String(getLoading()));
    if (getLoading()) {
        renderGroupedTable({
            container: "#dataBody",
            rows: [],
            totalCols: COLUMNS.length,
            expanded,
            renderLabelCells: () => "",
            labelCols: 0,
            renderValues: () => "",
            onToggle: () => {},
            emptyMessage: emptyMessage(),
        });
        $("#detailFooter").innerHTML = "";
        return;
    }

    if (!keys.length) {
        const start = getShowAll() ? 0 : (getCurrentPage() - 1) * PAGE_SIZE;
        renderGroupedTable({
            container: "#dataBody",
            rows: getShowAll() ? getFiltered() : getFiltered().slice(start, start + PAGE_SIZE),
            totalCols: COLUMNS.length,
            expanded,
            renderLabelCells: () => "",
            labelCols: 0,
            renderValues: (d, i) => caseCells(d, start + i),
            onToggle: () => {},
            emptyMessage: emptyMessage(),
        });
        renderPageFooter({
            container: "#detailFooter",
            totalItems: getFiltered().length,
            pageSize: PAGE_SIZE,
            currentPage: getCurrentPage(),
            showAll: getShowAll(),
            unit: "case",
            onPageChange: (page) => { setCurrentPage(page); renderTable(); },
            onToggleAll: (all) => { setShowAll(all); setCurrentPage(1); renderTable(); },
        });
        return;
    }

    const values = groupValues(keys);
    const start = (getCurrentPage() - 1) * GROUP_PAGE_SIZE;
    const visible = new Set(getShowAll() ? values : values.slice(start, start + GROUP_PAGE_SIZE));
    const rows = getFiltered().filter((r) => visible.has(String(r[keys[0]] ?? "")));

    renderGroupedTable({
        container: "#dataBody",
        rows,
        groupBy: keys,
        mode: "span",
        summarise: (g) => `${g.length} case${g.length === 1 ? "" : "s"}`,
        totalCols: COLUMNS.length,
        expanded,
        defaultExpanded: DEFAULT_EXPANDED,
        renderLabelCells: () => "",
        labelCols: 0,
        renderValues: (d, i) => caseCells(d, i),
        onToggle: (path) => {
            toggleGroup(expanded, path, DEFAULT_EXPANDED);
            renderTable();
        },
        emptyMessage: emptyMessage(),
    });

    renderPageFooter({
        container: "#detailFooter",
        totalItems: values.length,
        pageSize: GROUP_PAGE_SIZE,
        currentPage: getCurrentPage(),
        showAll: getShowAll(),
        // Paging counts **groups** wherever grouping is on: a page that split a
        // group would make its roll-up a lie, and so would a count of rows.
        unit: "group",
        onPageChange: (page) => { setCurrentPage(page); renderTable(); },
        onToggleAll: (all) => { setShowAll(all); setCurrentPage(1); renderTable(); },
    });
}

/**
 * Draw one toggle per status.
 *
 * Rebuilt from the taxonomy rather than written into the template, and called
 * again whenever the selection changes so `aria-pressed` stays truthful — a
 * toggle group that lies to a screen reader is worse than a plain select.
 */
export function renderResultToggles() {
    $("#filterResult").innerHTML = getStatuses().map((st) =>
        `<button type="button" class="toggle" data-status="${esc(st.key)}"`
        + ` data-tone="${esc(toneFor(st.key))}" aria-pressed="false">${esc(st.label)}</button>`
    ).join("");
    paintResultToggles();
}

/**
 * Draw the Scope toggles: every raw spelling present in the cases in hand.
 *
 * Rebuilt on every `rebuild`, exactly as `populateSelect` refilled the select it
 * replaces — the vocabulary is the data's, not the config's, so a scope nobody
 * has written down this load has no toggle. A pressed scope that disappears
 * that way is dropped from the set at the same time, because a narrowing on a
 * value no case carries would empty the table with no visible control to undo
 * it.
 */
export function renderScopeToggles() {
    const values = uniqueOf(getAllData(), "scope");
    // Drop any pressed value the new data no longer has.
    [...chosenRawScopes].forEach((v) => { if (!values.includes(v)) chosenRawScopes.delete(v); });

    $("#filterScope").innerHTML = values.map((v) =>
        `<button type="button" class="toggle" data-scope-toggle="${esc(v)}"`
        + ` aria-pressed="false">${esc(v)}</button>`).join("");
    paintScopeToggles();
}

/** Reflect `chosenRawScopes` onto the toggles. */
export function paintScopeToggles() {
    $("#filterScope").querySelectorAll("button[data-scope-toggle]").forEach((b) => {
        b.setAttribute("aria-pressed", String(chosenRawScopes.has(b.dataset.scopeToggle)));
    });
}

/**
 * Draw the status card strip: every status, not only the reviewable ones.
 *
 * The leading card is "All" rather than "To review": this screen holds the whole
 * taxonomy now, and pressing it is the deliberate choice to fetch every status.
 * Built here rather than by `main.js`, which has no business knowing what this
 * strip contains.
 */
export function renderDetailCards() {
    renderStatCards({
        container: "#statsRow",
        statuses: getStatuses(),
        totalLabel: "All",
        totalId: "statTotal",
        idPrefix: "stat-",
        inert: [{ label: "Files", id: "statFiles" }],
    });
    paintResultToggles();
}

/** Reflect `chosenStatuses` onto the toggles and the cards. */
export function paintResultToggles() {
    $("#filterResult").querySelectorAll("button[data-status]").forEach((b) => {
        b.setAttribute("aria-pressed", String(chosenStatuses.has(b.dataset.status)));
    });
    // The cards show the same state. "All" is pressed when every status is
    // chosen; a status card is pressed only when it is the *sole* choice,
    // because the toggles can express a combination the single-pick row cannot.
    const all = getStatuses().length > 0 && chosenStatuses.size === getStatuses().length;
    $("#statsRow").querySelectorAll("button[data-status-card]").forEach((b) => {
        const key = b.dataset.statusCard;
        const on = key
            ? chosenStatuses.size === 1 && chosenStatuses.has(key)
            : all;
        b.setAttribute("aria-pressed", String(on));
    });
}

/**
 * Draw the scope pills: All, then one per group with the cases it holds.
 *
 * Counted from the summary rows, so a group is offered — and its size is known
 * — before any of its cases have been fetched. A group the plan excludes is
 * drawn `chip-card--aside`, the pill form of the dashed rule its Summary table
 * carries, and starts unpressed: adding work nobody committed to is a choice
 * somebody makes, not a default.
 *
 * **All is a shortcut, not a mode.** The groups stay multi-select — several
 * pressed at once is the normal question here — and All simply presses every
 * one of them, reading as pressed only when they all are. That is the
 * convention the status cards above already use, and it is why All has no
 * "off": unpressing everything would empty the table, and a control whose only
 * effect is to show nothing is not one worth offering. Its figure is the sum of
 * the rest, so the row adds up to what pressing it would list.
 */
export function renderScopeCards() {
    const counts = countsByScope();
    const total = getScopeGroups().reduce((n, g) => n + (counts[g.key] || 0), 0);
    const pill = (key, label, value, cls = "") =>
        `<button type="button" class="chip-card${cls}"`
        + ` data-scope-card="${esc(key)}" aria-pressed="false">`
        + `<span class="chip-card-label">${esc(label)}</span>`
        + `<span class="chip-card-value num">${value.toLocaleString()}</span></button>`;

    // All carries the empty key, the way the status strip's leading card does.
    $("#detailScopes").innerHTML = pill("", "All", total)
        + getScopeGroups().map((g) => pill(g.key, g.label, counts[g.key] || 0,
                                      g.counted === false ? " chip-card--aside" : "")).join("");
    paintScopeCards();
}

/** Reflect `chosenScopes` onto the cards, and say what they add up to. */
export function paintScopeCards() {
    // All is pressed only when every group is, so it reports the selection
    // rather than claiming one: with three of four pressed it is a shortcut
    // still worth offering, not a description of what is on screen.
    const all = getScopeGroups().length > 0 && chosenScopes.size === getScopeGroups().length;
    $("#detailScopes").querySelectorAll("button[data-scope-card]").forEach((b) => {
        const key = b.dataset.scopeCard;
        b.setAttribute("aria-pressed", String(key ? chosenScopes.has(key) : all));
    });

    const chosen = getScopeGroups().filter((g) => chosenScopes.has(g.key));
    const counts = countsByScope();
    const total = chosen.reduce((n, g) => n + (counts[g.key] || 0), 0);
    // Naming all four when all four are pressed restates the row above it, and
    // grows with the config; the pills are already the list.
    const named = all ? "All scopes" : chosen.map((g) => g.label).join(" + ");
    $("#detailScopeSummary").textContent = chosen.length
        ? `${total.toLocaleString()} cases · ${named}`
        : "No scope selected";
}

/**
 * Build the detail header and make it sortable.
 *
 * Generated rather than written into the template so the sort buttons and their
 * `aria-sort` targets are built the same way as every other table's.
 */
export function renderDetailHead() {
    $("#detailHead").innerHTML = COLUMNS.map((c) => c.col
        ? sortableTh(c.col, c.label, { cls: c.cls || "" })
        : `<th${c.cls ? ` class="${c.cls}"` : ""}>${esc(c.label)}</th>`).join("");
    makeSortable("#detailHead th.sortable", detailSort, () => { setCurrentPage(1); onChanged(); });
    paintSortIndicators("#detailHead th.sortable", detailSort);
}

/** Reflect `missingOnly` onto its button. */
export function paintMissingReason() {
    $("#btnMissingReason").setAttribute("aria-pressed", String(getMissingOnly()));
}
