# CSS and Template Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `static/css/app.css` (1760 lines) into six linked stylesheets and `templates/index.html` (612 lines) into a shell plus seven view partials, with byte-identical output in both cases.

**Architecture:** Both splits are cuts, not rewrites. The CSS is cut at **contiguous** section boundaries so that concatenating the six files in link order reproduces the original byte for byte — which makes the cascade provably unchanged rather than argued to be unchanged. The template is cut at `<section class="view">` boundaries into `templates/views/*.html`, included from the shell in the order they appear today.

**Tech Stack:** Hand-written CSS, no framework, no preprocessor, no build step. Jinja2 via Flask.

**Spec:** [docs/superpowers/specs/2026-09-20-project-restructure-design.md](../specs/2026-09-20-project-restructure-design.md) — Phase 4.

## Global Constraints

- **No rule text changes.** Not a selector, not a declaration, not a comment, not a blank line. The only new bytes are the six file header comments and the six `<link>` tags.
- **Order is preserved exactly.** `cat base.css controls.css tables.css cards.css charts.css views.css` must equal today's `app.css` byte for byte, modulo the header comments. This is a verified property, not an intention — Task 1 Step 4 is the diff that proves it.
- **`tokens.css` is untouched** and stays the first stylesheet linked. Every file in this split reads its variables and none may define one.
- **The rendered template must not change.** Task 2 Step 5 renders `index.html` before and after through Jinja and diffs the output.
- **No behaviour change anywhere.** No `id` is added, removed or renamed; no class is added, removed or renamed. `main.js` and every view module address the DOM by `id`, so a renamed `id` is a silently broken screen.
- **Python is untouched.** `.venv/bin/python -m pytest -q` must stay at 484 passed throughout.

---

## Ruling: six files, and why the names differ from the spec

The spec names six CSS files — `base`, `layout`, `controls`, `tables`, `cards`, `charts` — and separately requires the link order to reproduce today's concatenation exactly, "because the cascade depends on it".

**Those two requirements are in conflict, and the conflict is real.** `app.css` has 36 comment-delimited sections, and they do not sit in semantic runs. `the panel grid` (layout) sits between `KPI cards` and `today's progress` (both cards); `the folded filter panel` (controls) sits between `a bar inside a table cell` and `charts`; the `narrow` media query sits in the middle rather than at the end. Sorting the sections into the spec's six buckets would move roughly a dozen of them past rules of equal specificity — which is precisely the reordering the spec forbids.

**Ruling: order wins, names bend.** The six files are cut at contiguous boundaries and named for what each run actually holds. Two names change from the spec: `layout` folds into `base` (the shell, the rail and the main column sit directly after the reset, so they are one run), and `views` is added for the tail, which is view- and panel-specific CSS that fits none of the spec's six names.

*Cost if this ruling is wrong:* the file names are slightly less predictable than the spec promised — someone looking for `.rail` opens `base.css` rather than `layout.css`. The alternative cost was an unverifiable cascade change across a 1760-line stylesheet with no test suite behind it, which is not a trade worth making. The spec is amended in Task 3.

---

## File Structure

**Created:**

| File | Lines of today's `app.css` | Sections |
|---|---|---|
| `static/css/base.css` | 1–204 | reset, body, `[hidden]`, CJK leading, `:focus-visible`, the shell, rail navigation, the main column |
| `static/css/controls.css` | 205–497 | buttons, fields, toolbar, toggle group, the summary overview, the progress bar, summary scope cards |
| `static/css/tables.css` | 498–811 | the ledger, the status band, grouped rows, sortable headers, badges, flags, pager |
| `static/css/cards.css` | 812–1144 | stats, scope cards, scope tabs, KPI cards, the panel grid, today's progress |
| `static/css/charts.css` | 1145–1315 | the daily chart, a bar inside a table cell, the folded filter panel, charts |
| `static/css/views.css` | 1316–1760 | cards, card variants, empty states, motion, narrow, Preparing the workbooks, the config editor, the merged source card, the file view |
| `templates/views/summary.html` | index.html 91–123 | `#summaryView` |
| `templates/views/daily.html` | 124–183 | `#dailyView` |
| `templates/views/productivity.html` | 184–209 | `#productivityView` |
| `templates/views/detail.html` | 210–342 | `#detailView` |
| `templates/views/file.html` | 343–408 | `#fileView` |
| `templates/views/tools.html` | 409–521 | `#toolsView` |
| `templates/views/config.html` | 522–605 | `#configView` |

The six CSS ranges tile 1–1760 exactly: no gap, no overlap.

**The `index.html` ranges in this table are measured against the file as it is today,
before Task 1 runs.** Task 1 replaces one `<link>` with six, shifting every later line
by five. Task 2 therefore derives its boundaries from the file rather than reading them
here; the numbers above are for orientation only.

**Deleted:** `static/css/app.css`

**Modified:** `templates/index.html`, `CLAUDE.md`, `README.md`, `docs/superpowers/specs/2026-09-20-project-restructure-design.md`

---

## Task 1: Split the stylesheet

**Files:**
- Create: the six files above
- Delete: `static/css/app.css`
- Modify: `templates/index.html:12` (one `<link>` becomes six)
- Test: the byte-exact diff in Step 4

**Interfaces:**
- Consumes: nothing.
- Produces: six stylesheets linked in order. `tokens.css` still precedes all six.

- [ ] **Step 1: Snapshot the original**

```bash
cd /Users/lomahs/lomahs/Coding/test-management
cp static/css/app.css /tmp/app-before.css
wc -l /tmp/app-before.css
```

Expected: `1760`. If it is not 1760, the line ranges in this plan are stale — stop and re-derive them from `grep -n "^/\* ---" static/css/app.css` before cutting anything.

- [ ] **Step 2: Cut the six files**

Cut by line range. Do not retype or reflow anything.

```bash
cd /Users/lomahs/lomahs/Coding/test-management/static/css
sed -n '1,204p'    app.css > base.css
sed -n '205,497p'  app.css > controls.css
sed -n '498,811p'  app.css > tables.css
sed -n '812,1144p' app.css > cards.css
sed -n '1145,1315p' app.css > charts.css
sed -n '1316,1760p' app.css > views.css
```

Verify the tiling before going further:

```bash
cat base.css controls.css tables.css cards.css charts.css views.css > /tmp/app-after.css
diff /tmp/app-before.css /tmp/app-after.css && echo "IDENTICAL"
```

Expected: `IDENTICAL` and no diff output. **If this fails, stop.** A non-empty diff means the ranges are wrong and every later step is built on sand.

- [ ] **Step 3: Add one header comment per file**

Only now, with the tiling proven, add a header. Each is a comment block at the very top saying what the file holds and where it sits in the cascade. `base.css` keeps today's 19-line `app.css` preamble (lines 1–19) as its own header — that comment is the design rationale for the whole stylesheet and belongs to the first file a reader opens. Extend it with a paragraph naming the split:

```css
/*
 * [today's 19-line preamble, verbatim]
 *
 * **The stylesheet is six files, and their link order is load-bearing.**
 * base, controls, tables, cards, charts, views — linked in that order from
 * `index.html`, immediately after `tokens.css`. They were cut from one
 * 1760-line file at contiguous section boundaries precisely so that
 * concatenating them reproduces it byte for byte: several rules here are
 * overridden later by a selector of equal specificity, so moving a section
 * between files would change what wins. Add a rule to the file whose subject
 * it shares, at the end of the section it belongs to — never at the top of a
 * file to "keep it near the others".
 */
```

The other five get four lines each, in this shape:

```css
/*
 * Tables: the ledger and everything drawn inside one.
 *
 * Third of six. Loads after `controls.css` and before `cards.css`; see the
 * header of `base.css` for why that order is not negotiable.
 */
```

Write each file's first line to say what it holds:

- `controls.css` — "Controls: buttons, fields, the toolbar, toggle groups — and the summary overview strip, which sits in this run because it sits here in the cascade."
- `tables.css` — "Tables: the ledger and everything drawn inside one."
- `cards.css` — "Cards: the stat strip, the scope cards and tabs, the KPI row, the panel grid."
- `charts.css` — "Charts: the daily bar chart, in-cell bars, the Chart.js tiles — and the folded filter panel, which sits between two of them in the cascade."
- `views.css` — "View- and panel-specific rules, the reduced-motion and narrow-screen queries, and the card variants. Last of six: everything here overrides something above it."

Two of the five headers deliberately admit a section that does not match the file's name. That is the ruling above made visible at the place a reader would otherwise be confused, and it is better than a name that quietly lies.

- [ ] **Step 4: Re-verify after the headers**

The headers are the only new bytes. Strip them and the files must still reconstruct the original:

```bash
cd /Users/lomahs/lomahs/Coding/test-management/static/css
python3 - <<'PY'
import re, pathlib
names = ["base", "controls", "tables", "cards", "charts", "views"]
out = []
for n in names:
    t = pathlib.Path(f"{n}.css").read_text()
    # drop exactly one leading /* ... */ block
    m = re.match(r"\A/\*.*?\*/\n", t, re.S)
    assert m, f"{n}.css has no header comment"
    out.append(t[m.end():])
rebuilt = "".join(out)
original = pathlib.Path("/tmp/app-before.css").read_text()
# base.css's header absorbed the original preamble, so put it back
m = re.match(r"\A/\*.*?\*/\n", original, re.S)
assert m, "app.css preamble not found"
print("IDENTICAL" if rebuilt == original[m.end():] else "DIFFERS")
PY
```

Expected: `IDENTICAL`.

- [ ] **Step 5: Link the six and delete the original**

In `templates/index.html`, replace line 12 with six links **in this order**:

```html
    <link rel="stylesheet" href="{{ url_for('static', filename='css/base.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/controls.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/tables.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/cards.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/charts.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/views.css') }}">
```

`tokens.css` stays on line 11, above all six.

```bash
git rm static/css/app.css
grep -rn "app\.css" static/ templates/ tcm/ tests/ README.md CLAUDE.md
```

Expected: only prose mentions in `README.md` and `CLAUDE.md`, which Task 3 rewrites. A hit in `tcm/` or `tests/` means something serves or asserts the filename and this plan missed it — fix it before committing.

- [ ] **Step 6: Load the app and confirm six 200s**

```bash
.venv/bin/python app.py
```

Open http://127.0.0.1:5000, open the Network tab, and reload. Six CSS requests, all 200, in the order above. A 404 renders an unstyled page, which is obvious; a **wrong order** renders a page that looks nearly right, which is not — check the order explicitly rather than trusting the page.

- [ ] **Step 7: Commit**

```bash
git add static/css templates/index.html
git commit -m "Split app.css into six stylesheets, cut at contiguous boundaries

1760 lines in one file. The six are cut by line range rather than sorted
into semantic buckets, because app.css's 35 sections do not sit in semantic
runs -- the panel grid sits between two card sections, the folded filter
panel between two chart ones -- and several rules are overridden later by a
selector of equal specificity. Concatenating the six reproduces the original
byte for byte, which is what makes the cascade provably unchanged rather
than argued to be.

That costs two of the spec's six names: layout folds into base, and views is
added for the tail. Two file headers name the section they hold that their
own name does not cover.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Split the template

**Files:**
- Create: `templates/views/{summary,daily,productivity,detail,file,tools,config}.html`
- Modify: `templates/index.html`
- Test: the rendered-output diff in Step 5

**Interfaces:**
- Consumes: the six `<link>` tags from Task 1.
- Produces: a shell of about 100 lines that includes seven partials.

- [ ] **Step 1: Snapshot the rendered page**

Render through Jinja with a real app context, because `url_for` needs one:

```bash
cd /Users/lomahs/lomahs/Coding/test-management
.venv/bin/python - <<'PY' > /tmp/index-before.html
from tcm.web.app import create_app
app = create_app()
with app.test_request_context():
    print(app.jinja_env.get_template("index.html").render(), end="")
PY
wc -c /tmp/index-before.html
```

Note the byte count. This is the artifact Step 5 diffs against, and it is the only verification this task has.

- [ ] **Step 2: Cut the seven partials**

**Derive the line ranges from the file as it now stands. Do not type the numbers below.**
Task 1 replaced one `<link>` with six, so every line after 12 has shifted by five, and the
ranges quoted in this plan's File Structure table were measured before that. They are
illustrative; the derivation is the authority.

The boundaries are unambiguous — each view starts at its own `<section class="view"`
and ends on the line before the next one, with the last ending at the line before
`</main>`:

```bash
mkdir -p templates/views
python3 - <<'PY'
import pathlib, re
p = pathlib.Path("templates/index.html")
lines = p.read_text().splitlines(keepends=True)

starts = [(i, re.search(r'id="(\w+)View"', l).group(1))
          for i, l in enumerate(lines) if '<section class="view' in l]
end = next(i for i, l in enumerate(lines) if "</main>" in l)
assert len(starts) == 7, f"expected 7 views, found {len(starts)}: {[n for _, n in starts]}"

bounds = [(s, (starts[k + 1][0] if k + 1 < len(starts) else end), name)
          for k, (s, name) in enumerate(starts)]
for s, e, name in bounds:
    pathlib.Path(f"templates/views/{name}.html").write_text("".join(lines[s:e]))
    print(f"{name}.html  lines {s+1}-{e}  ({e-s} lines)")
PY
```

Expected: seven lines naming `summary`, `daily`, `productivity`, `detail`, `file`,
`tools`, `config` in that order. If the count assertion fires, a view was added or
renamed since this plan was written — reconcile before cutting.

Check each partial opens and closes its own `<section class="view">`:

```bash
for f in templates/views/*.html; do
  echo "$f: open=$(grep -c '<section class="view' $f) close=$(grep -c '</section>' $f)"
done
```

`open` must be 1 for every file. `close` counts the nested `.card` sections too, so it will be larger — what matters is that it equals the number of `<section` opens in that file:

```bash
for f in templates/views/*.html; do
  o=$(grep -o '<section' $f | wc -l); c=$(grep -o '</section>' $f | wc -l)
  [ "$o" = "$c" ] && echo "OK $f ($o)" || echo "UNBALANCED $f: $o open, $c close"
done
```

Expected: seven `OK` lines. An unbalanced partial means a range boundary landed inside an element, and the rendered diff in Step 5 will fail.

- [ ] **Step 3: Replace the views in the shell with includes**

Edit `templates/index.html`: delete everything from the first `<section class="view"` through the line before `</main>` — the exact span Step 2 just printed — and put seven include tags in its place, in the same order.

```html
        {% include "views/summary.html" %}
        {% include "views/daily.html" %}
        {% include "views/productivity.html" %}
        {% include "views/detail.html" %}
        {% include "views/file.html" %}
        {% include "views/tools.html" %}
        {% include "views/config.html" %}
```

Jinja's `include` inserts the partial's rendered text at the tag's position without adding or trimming anything, so the output is unchanged as long as each partial ends with the newline its source range ended with. `sed -n 'A,Bp'` preserves that.

Add a comment above the block saying what the list is:

```html
        <!-- One partial per view, in the order `main.js`'s VIEWS list names
             them. Adding a view means an entry there, a partial here, and
             nothing else. File is in the list but not in the rail: it is a
             drill-in, entered by clicking a file name. -->
```

- [ ] **Step 4: Update the shell's own header comment**

`index.html`'s top-of-file comment describes a single-file template. Amend it to say the views now live in `templates/views/` and that the shell holds the rail, the page heading and the script tags.

Leave the Chart.js `<script>` before the module tag. That ordering is load-bearing — Chart.js resolves colours at construction, and `charts.js` depends on the global existing.

- [ ] **Step 5: Prove the rendered output is identical**

```bash
cd /Users/lomahs/lomahs/Coding/test-management
.venv/bin/python - <<'PY' > /tmp/index-after.html
from tcm.web.app import create_app
app = create_app()
with app.test_request_context():
    print(app.jinja_env.get_template("index.html").render(), end="")
PY
diff /tmp/index-before.html /tmp/index-after.html && echo "IDENTICAL"
```

Expected: `IDENTICAL`.

A diff of only the comment added in Step 3 is acceptable — confirm that by reading it, and that it is the *only* difference. Any difference in a `<section>`, an `id`, a `class` or an attribute is a defect: fix it and re-run, do not accept it.

- [ ] **Step 6: Run the suite and walk the app**

```bash
.venv/bin/python -m pytest -q
```

Expected: 484 passed.

Then start the app and walk all seven views in both themes. The rendered diff already proves the markup is identical, so this walk is checking the **stylesheets** from Task 1, which have no automated proof at all:

| # | Check |
|---|---|
| 1 | The rail: dark, sticky, nav items invert when selected |
| 2 | Every table is a rounded hairline pane, with `<thead>` and `<tfoot>` sticky inside it and clipped into the corners |
| 3 | Panes cap at about ten rows and scroll internally; the page does not grow |
| 4 | Badges are full pills; status tones match the taxonomy |
| 5 | The status band's `band--aside` dashed rule is still dashed |
| 6 | The Summary progress bar fills its track, segments stepped by tone |
| 7 | Scope cards and pills invert when pressed; an excluded one keeps its dashed border *through* the press |
| 8 | The folded filter panel opens and its narrowing-count pill shows |
| 9 | The Chart.js tiles and the Daily CSS bar chart both draw, light and dark |
| 10 | Tools: the prepare panel, and `.btn-danger` on Apply is the only coloured control in the app |
| 11 | The config editor's table and selects |
| 12 | Narrow the window below 860px: the rail goes full-width to the top and stops being sticky |
| 13 | Both themes, on every view |

Item 12 is the one most likely to break, because the `narrow` media query sits in the middle of the original file and now sits in `views.css`. It targets only `.shell`, `.rail` and `.main`, none of which is restyled after it — but check it rather than trusting the analysis.

- [ ] **Step 7: Commit**

```bash
git add templates
git commit -m "Split index.html into a shell and seven view partials

612 lines holding the rail, the heading and all seven views. Each
<section class=\"view\"> becomes templates/views/<name>.html, included from
the shell in the order main.js's VIEWS list names them.

Verified by rendering the template through Jinja before and after and
diffing the output: identical but for the comment naming the include block.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Document, and amend the spec

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `docs/superpowers/specs/2026-09-20-project-restructure-design.md`

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: nothing code depends on.

- [ ] **Step 1: Rewrite `CLAUDE.md`'s "No CSS framework" paragraph**

It currently says the UI is "hand-written CSS in two files" and names `app.css`. It is now eight files. Replace the first sentence and add the ordering rule:

> **No CSS framework.** The UI is hand-written CSS in eight files.
> [static/css/tokens.css](static/css/tokens.css) holds every colour, type and
> spacing token (light palette on bare `:root`, dark redefined under both
> `prefers-color-scheme` and `[data-theme="dark"]`), and the components are split
> across `base`, `controls`, `tables`, `cards`, `charts` and `views` — **linked
> from `index.html` in exactly that order, which is load-bearing.** They were cut
> from one 1760-line `app.css` at contiguous section boundaries rather than sorted
> into semantic buckets, because its sections do not sit in semantic runs and
> several rules are overridden later by a selector of equal specificity;
> concatenating the six reproduces the original byte for byte, which is what makes
> the cascade provably unchanged. Two files therefore hold a section their name
> does not cover, and each says so in its header. A new rule goes in the file
> whose subject it shares, at the end of the section it belongs to — never at the
> top of a file to keep it near a related one.

Then find and fix every other `app.css` mention:

```bash
grep -n "app\.css" CLAUDE.md
```

- [ ] **Step 2: Add the template paragraph to `CLAUDE.md`**

The **Frontend state ownership** section says `templates/index.html` loads `main.js`. Extend it:

> `templates/index.html` is the shell — the rail, the page heading and the two
> script tags — and includes one partial per view from `templates/views/`. Adding
> a view means an entry in `main.js`'s `VIEWS`, a `templates/views/<name>.html`
> holding its `<section class="view" id="<name>View">`, and an `{% include %}`
> beside the others. The Chart.js `<script>` stays before the module tag.

- [ ] **Step 3: Update `README.md`**

The Vietnamese structure tree lists `static/css/app.css` and `templates/index.html`. Replace them with the eight stylesheets and the `templates/views/` directory, in the project's existing Vietnamese prose style.

- [ ] **Step 4: Amend the spec**

The spec's Phase 4 section names six files including `layout` and does not name `views`. Rewrite those two paragraphs to describe what was built, and add one sentence recording why:

> The six are cut at contiguous section boundaries rather than sorted into
> semantic buckets. `app.css`'s sections do not sit in semantic runs — the panel
> grid sits between two card sections, the folded filter panel between two chart
> ones — so bucketing them would move rules past others of equal specificity,
> which is the reordering this phase's whole constraint forbids. `layout` folds
> into `base` and `views` holds the tail.

A spec describing a shape that was tried and rejected is worse than no spec, which is the same reason Phase 2's `report/layout.py` note was corrected rather than left.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md docs/superpowers/specs/2026-09-20-project-restructure-design.md
git commit -m "Record the stylesheet and template split, and amend the spec

The spec's six CSS names assumed the sections sat in semantic runs. They do
not, and sorting them would have reordered the cascade -- which the same spec
forbids. Records the contiguous cut that was built instead, and the two file
names that changed because of it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```
