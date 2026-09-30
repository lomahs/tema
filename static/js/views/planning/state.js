/**
 * Planning's mutable state. Declares it and nothing else.
 *
 * The same rule as `views/detail/state.js`: an imported `let` cannot be
 * reassigned by the importer, so each one is reached through a getter and a
 * setter, while a `Set` or an object is exported directly — mutating one is not
 * rebinding a name. Adding state means adding it here.
 */

/** The date the Day plan is on, "YYYY-MM-DD"; null until the first load. */
let day = null;

/** "matrix" | "list". */
let layout = "matrix";

/** Past phase days the forecast pace is read over: "3" | "5" | "10" | "all". */
let fcWindow = "5";

/** Monday of the phase grid's week on screen; null shows the week holding today. */
let gridWeek = null;

/** The phase grid lists only the files and devices that still need a plan. */
let gridNeedOnly = false;

/** The slot highlighted after a grid click: `{file, device}` (device null = every device). */
let focus = null;

/** Grid files drawn per device. File names live here, never in an attribute. */
export const expanded = new Set();

/** The List layout's sort, in `sorting.js`'s shape. */
export const listSort = { col: "pic", asc: true };

/** The List layout's filters; "" is "all". `file` is an index into the day's files. */
export const listFilter = { pic: "", file: "", status: "" };

/** The last responses: `phase` from /api/plan/phase, `board` from /api/plan/board/<date>,
 *  `phases` from /api/phases (every phase, the active one, the roster). */
export const data = { phase: null, board: null, phases: null };

export const getDay = () => day;
export const setDay = (v) => { day = v; };
export const getLayout = () => layout;
export const setLayout = (v) => { layout = v; };
export const getWindow = () => fcWindow;
export const setWindow = (v) => { fcWindow = v; };
export const getGridWeek = () => gridWeek;
export const setGridWeek = (v) => { gridWeek = v; };
export const getGridNeedOnly = () => gridNeedOnly;
export const setGridNeedOnly = (v) => { gridNeedOnly = v; };
export const getFocus = () => focus;
export const setFocus = (v) => { focus = v; };
