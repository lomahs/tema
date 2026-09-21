"""The page and its assets, which no /api test covers.

Every other test in this suite asks for JSON. If `template_folder` or
`static_folder` were wrong, all of them would still pass and the app would
serve nothing a browser could use -- so this is the only thing standing
between a factory refactor and a blank page.
"""
import pathlib
import posixpath
import re

from tcm.web.app import create_app

#: The component stylesheets, in the order `index.html` links them.
#: Written out rather than globbed: this list is the assertion, and a glob
#: would agree with whatever the directory happened to contain.
STYLESHEETS = ("base", "controls", "tables", "cards", "charts", "views")


def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_the_index_page_renders_the_shell():
    response = client().get("/")
    assert response.status_code == 200
    # A view section from templates/index.html: proves the template was found
    # and rendered, not merely that a route answered.
    assert b"summaryView" in response.data


def test_the_static_assets_are_served():
    c = client()
    for path in ("/static/js/main.js", "/static/css/tokens.css"):
        assert c.get(path).status_code == 200, path


def test_every_stylesheet_the_shell_links_is_served():
    """The six component files, in the order the cascade depends on.

    Named one by one rather than globbed: a glob would pass just as happily
    against five files as six, and the failure this guards against — a link
    pointing at a stylesheet that is not there — renders a page that still
    mostly works, so nothing louder would catch it.
    """
    c = client()
    for name in STYLESHEETS:
        path = f"/static/css/{name}.css"
        assert c.get(path).status_code == 200, path


def test_the_stylesheets_are_linked_in_cascade_order():
    """Order, not merely presence.

    The six were cut from one file at contiguous boundaries, so several rules
    in an earlier one are overridden by a selector of equal specificity in a
    later one. Reordering the links therefore changes what wins — and it does
    so silently, because the page still renders and still looks nearly right.
    `tokens.css` leads: everything below reads its variables.
    """
    html = client().get("/").data.decode()
    order = [html.index(f"css/{name}.css") for name in ("tokens", *STYLESHEETS)]
    assert order == sorted(order), (
        "stylesheet links are out of cascade order: "
        f"{['tokens', *STYLESHEETS]} must appear in that order"
    )


#: An `import`/`export ... from "spec"` specifier. Applied to source with its
#: comments stripped, because a comment holding an apostrophe or a semicolon
#: would otherwise end the match early and drop that module from the walk.
_IMPORT = re.compile(r'\b(?:import|export)\b(?:[^"\';]|\n)*?\bfrom\s+["\']([^"\']+)["\']')

#: Line and block comments. JS has no nested block comments, so this is exact.
_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def test_every_es_module_import_resolves():
    """Walk the module graph from the shell's entry point and assert it is whole.

    There is no bundler and no JS test framework, so a mistyped or stale import
    specifier fails nowhere except a browser console -- the page loads, the
    stylesheet applies, and the app simply does nothing. That is the failure
    this catches, and it is the one the view splits could most easily have
    introduced: a browser resolves no directory index, so `views/detail/` is a
    404 where `views/detail/index.js` is not.

    Three things are asserted, and the third is what makes this more than a
    404 check. The entry point is read out of the rendered page rather than
    named here, so breaking the `<script type="module">` fails this test
    instead of leaving it green. Every reachable specifier must resolve. And
    the reachable set must equal every `.js` file on disk -- which catches the
    opposite failure, a module orphaned by an import that was dropped rather
    than mistyped, and would otherwise sit unreferenced and untested.

    Bare specifiers are skipped: the only one is the Chart.js CDN tag, which is
    a <script> in the shell rather than an import, and the suite reaches no
    network.
    """
    c = client()
    html = c.get("/").data.decode()
    entry = re.search(r'<script type="module" src="([^"]+)"', html)
    assert entry, "the shell has no <script type=\"module\"> entry point"

    seen, queue = {}, [entry.group(1)]
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        response = c.get(path)
        seen[path] = response.status_code
        if response.status_code != 200:
            continue
        source = _COMMENT.sub("", response.data.decode())
        for spec in _IMPORT.findall(source):
            if not spec.startswith("."):
                continue
            queue.append(posixpath.normpath(posixpath.join(posixpath.dirname(path), spec)))

    broken = {p: code for p, code in seen.items() if code != 200}
    assert not broken, f"unresolvable module imports: {broken}"

    root = pathlib.Path(__file__).resolve().parents[2] / "static" / "js"
    on_disk = {f"/static/js/{p.relative_to(root).as_posix()}" for p in root.rglob("*.js")}
    assert set(seen) == on_disk, (
        f"unreachable from the entry point: {sorted(on_disk - set(seen))}; "
        f"walked but absent from disk: {sorted(set(seen) - on_disk)}"
    )
