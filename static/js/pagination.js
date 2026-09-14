/**
 * Self-contained pagination widget.
 *
 * Deliberately knows nothing about the views: the caller passes its own state
 * in and reacts through `onPageChange`. Keeping the dependency one-way avoids a
 * cycle between this module and the views that use it.
 *
 * A grouped table pages over *groups* rather than rows, which needs no change
 * here — the caller simply passes the group count as `totalItems`.
 */
import { $, esc } from "./dom.js";

/** Pages shown either side of the current one before an ellipsis takes over. */
const PAGE_WINDOW = 2;

/**
 * The page numbers to show, with `null` marking each gap.
 *
 * Always includes the first page, the last page, and `PAGE_WINDOW` pages either
 * side of the current one, e.g. `[1, null, 5, 6, 7, 8, 9, null, 20]`.
 *
 * @param {number} total Total page count.
 * @param {number} current 1-based current page.
 * @returns {Array<number|null>} `null` means "render an ellipsis here".
 */
function pageNumbers(total, current) {
    const pages = new Set([1, total, current]);
    for (let d = 1; d <= PAGE_WINDOW; d++) {
        if (current - d >= 1) pages.add(current - d);
        if (current + d <= total) pages.add(current + d);
    }
    const sorted = [...pages].sort((a, b) => a - b);
    const out = [];
    let prev = 0;
    for (const p of sorted) {
        if (prev && p - prev > 1) out.push(null);   // gap -> ellipsis
        out.push(p);
        prev = p;
    }
    return out;
}

/**
 * Render the pager into `container`, or hide it when there is nothing to page.
 *
 * The buttons are rebuilt on every call, which discards the previous click
 * listeners along with the old elements.
 *
 * @param {Object} opts
 * @param {number} opts.totalItems Rows — or groups — after filtering.
 * @param {number} opts.pageSize Items per page.
 * @param {number} opts.currentPage 1-based current page.
 * @param {(page: number) => void} opts.onPageChange Called with the new page.
 * @param {string} [opts.container] Selector of the `<nav>` to fill; each view
 *   that pages needs its own, so pass one when it isn't the detail view's
 *   `#pagination`.
 */
export function renderPagination({ totalItems, pageSize, currentPage, onPageChange,
                                   container = "#pagination" }) {
    const totalPages = Math.ceil(totalItems / pageSize);
    const nav = $(container);
    if (totalPages <= 1) { nav.hidden = true; nav.innerHTML = ""; return; }
    nav.hidden = false;

    const step = (label, page, disabled) =>
        `<button data-page="${page}"${disabled ? " disabled" : ""} aria-label="${label}">`
        + `${label === "Previous" ? "‹" : "›"}</button>`;

    nav.innerHTML = step("Previous", currentPage - 1, currentPage === 1)
        + pageNumbers(totalPages, currentPage).map((p) => {
            if (p === null) return '<button class="gap" disabled>…</button>';
            const current = p === currentPage ? ' aria-current="page"' : "";
            return `<button data-page="${p}"${current}>${p}</button>`;
        }).join("")
        + step("Next", currentPage + 1, currentPage === totalPages);

    nav.querySelectorAll("button[data-page]").forEach((b) => b.addEventListener("click", () => {
        if (b.disabled) return;
        onPageChange(parseInt(b.dataset.page, 10));
    }));
}

/**
 * A card's footer: how many rows there are, and the way through them.
 *
 * Prev/Next with a page label rather than the numbered pager above, plus a
 * Show-all that drops paging entirely — the design's footer. With several
 * tables on one screen a row of numbered buttons under each reads as a lot of
 * chrome for ten rows.
 *
 * Show all does not make the page taller: the pane it sits under is capped at
 * about ten rows and scrolls, which is the whole reason showing everything is
 * a reasonable thing to offer.
 *
 * Self-contained like the rest of this module — it takes state and reports
 * back, and imports no view.
 *
 * @param {Object} opts
 * @param {string} opts.container Selector for the footer element to fill.
 * @param {number} opts.totalItems Rows or groups, whichever is being paged.
 * @param {number} opts.pageSize
 * @param {number} opts.currentPage
 * @param {boolean} [opts.showAll] Whether paging is currently off.
 * @param {string} [opts.unit] Singular noun for the count, e.g. `"file"`.
 * @param {(page: number) => void} opts.onPageChange
 * @param {(showAll: boolean) => void} opts.onToggleAll
 */
export function renderPageFooter({
    container, totalItems, pageSize, currentPage, showAll = false,
    unit = "row", onPageChange, onToggleAll,
}) {
    const foot = $(container);
    const pageCount = Math.max(1, Math.ceil(totalItems / pageSize));
    const page = Math.min(Math.max(1, currentPage), pageCount);
    const paged = !showAll && pageCount > 1;

    foot.innerHTML = `
        <span class="count">${totalItems.toLocaleString()} `
            + `${esc(unit)}${totalItems === 1 ? "" : "s"}</span>
        <div class="card-foot-end">
            ${paged ? `
                <button type="button" class="btn btn-sm" data-step="prev"
                        ${page === 1 ? "disabled" : ""}>Prev</button>
                <span class="count">${page} / ${pageCount}</span>
                <button type="button" class="btn btn-sm" data-step="next"
                        ${page === pageCount ? "disabled" : ""}>Next</button>` : ""}
            ${pageCount > 1 ? `<button type="button" class="btn btn-sm" data-step="all">`
                + `${showAll ? "Show pages" : "Show all"}</button>` : ""}
        </div>`;

    foot.querySelectorAll("button[data-step]").forEach((b) => b.addEventListener("click", () => {
        if (b.disabled) return;
        if (b.dataset.step === "prev") onPageChange(page - 1);
        else if (b.dataset.step === "next") onPageChange(page + 1);
        else onToggleAll(!showAll);
    }));
}
