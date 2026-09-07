/**
 * Light / dark switching.
 *
 * Three states, not two: with nothing stored the page follows the operating
 * system, and choosing either palette stamps `data-theme` on the root element
 * so the choice wins over `prefers-color-scheme` in both directions.
 *
 * Chart.js bakes colours in when a chart is constructed, so anything that
 * paints outside CSS has to be told when the palette moves — hence the
 * listener list.
 */
import { $ } from "./dom.js";

const STORAGE_KEY = "tcm_theme";

/** @type {Array<() => void>} */
const listeners = [];

/** @returns {"light"|"dark"} What the OS is asking for. */
function systemTheme() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** @returns {"light"|"dark"} The palette actually on screen. */
function currentTheme() {
    return document.documentElement.dataset.theme || systemTheme();
}

/**
 * Run `fn` whenever the palette changes, so canvas-drawn colours can be redrawn.
 * @param {() => void} fn
 */
export function onThemeChange(fn) {
    listeners.push(fn);
}

/**
 * Resolve a CSS custom property to a concrete colour.
 *
 * Chart.js cannot be handed `var(--tone-danger)`, so anything painting to a
 * canvas reads its colours through here rather than repeating the palette.
 *
 * @param {string} name e.g. `"--tone-danger"`.
 * @returns {string} A computed colour, or `""` if the property is unset.
 */
export function cssValue(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * Mix a token toward the ink colour, for distinguishing statuses that share a
 * tone (OK and NG-OK are both green; Cancel and NYS are both grey).
 *
 * Resolved through a probe element because `color-mix()` is not a value
 * `getPropertyValue` will compute on its own.
 *
 * @param {string} token e.g. `"--tone-success"`.
 * @param {number} step 0 leaves the tone alone; each step darkens it further.
 * @returns {string} A computed colour.
 */
export function shade(token, step) {
    const base = cssValue(token);
    if (!step) return base;
    return resolveColour(`color-mix(in oklab, ${base}, var(--ink) ${Math.min(step, 3) * 22}%)`);
}

/**
 * Resolve any CSS colour expression to a concrete `rgb()` / `rgba()` value.
 *
 * A canvas cannot parse `color-mix()` — Chart.js passes colours straight to
 * `fillStyle`, which silently ignores anything it does not understand and
 * paints black. So anything destined for a canvas comes through here first.
 *
 * @param {string} expr Any CSS colour, including `color-mix(...)` and `var(...)`.
 * @returns {string} A computed colour.
 */
export function resolveColour(expr) {
    const probe = document.createElement("span");
    probe.style.cssText = "position:absolute;visibility:hidden;pointer-events:none";
    probe.style.color = expr;
    document.body.appendChild(probe);
    const out = getComputedStyle(probe).color;
    probe.remove();
    return out;
}

function apply(theme) {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;

    const btn = $("#btnTheme");
    if (btn) {
        const next = currentTheme() === "dark" ? "light" : "dark";
        btn.setAttribute("aria-label", `Switch to ${next} theme`);
        btn.textContent = currentTheme() === "dark" ? "◑" : "◐";
    }
    listeners.forEach((fn) => fn());
}

/** Adopt the stored choice and wire the toggle. Call once, at startup. */
export function initTheme() {
    let stored = null;
    try {
        stored = localStorage.getItem(STORAGE_KEY);
    } catch (_) { /* private window, blocked storage — follow the OS */ }
    apply(stored === "light" || stored === "dark" ? stored : null);

    // With nothing stored the page tracks the OS for as long as the tab is open.
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        if (!document.documentElement.dataset.theme) apply(null);
    });

    $("#btnTheme").addEventListener("click", () => {
        const next = currentTheme() === "dark" ? "light" : "dark";
        try {
            localStorage.setItem(STORAGE_KEY, next);
        } catch (_) { /* not fatal; the choice just will not survive a reload */ }
        apply(next);
    });
}
