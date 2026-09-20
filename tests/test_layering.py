"""The layering rule, made executable.

The spec's dependency table is only worth something if something checks it.
This walks the AST of every module in the package and asserts what each layer
is allowed to import — which is what stops a later move quietly importing
backwards and leaving the tree layered in name only.
"""
import ast
import pathlib

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "tcm"

#: Nothing in the domain may reach a framework. The vocabularies still read
#: their JSON at import, so this names frameworks rather than forbidding I/O;
#: the ConfigRepository port is where that gets cut properly.
FRAMEWORKS = {"flask", "pandas", "openpyxl", "requests", "msal"}

#: Which `tcm.<layer>` each layer may import. `tcm.settings` sits outside the
#: layers on purpose and is allowed everywhere.
ALLOWED = {
    "domain": {"domain"},
    "infrastructure": {"domain", "infrastructure"},
    "services": {"domain", "infrastructure", "services"},
    "web": {"domain", "infrastructure", "services", "web"},
}


def _modules(layer):
    """Every .py file in one layer, as (layer, path) pairs for parametrising."""
    root = PACKAGE / layer
    return [p for p in sorted(root.rglob("*.py"))] if root.is_dir() else []


def _package_of(path):
    """The dotted package a relative import in `path` resolves against —
    `path`'s own directory, dotted, whether `path` is a regular module or the
    `__init__.py` naming that directory's package."""
    parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
    return ".".join(parts[:-1])


def _resolve_relative(path, level, module):
    """Absolute dotted name a relative import in `path` refers to, following
    the same rule CPython's own import system uses to resolve one."""
    base = _package_of(path).rsplit(".", level - 1)[0]
    return f"{base}.{module}" if module else base


def _imported_names(path):
    """Every module name `path` imports, absolute names only. Relative
    imports are resolved rather than skipped: a `from .` re-export — the
    idiom `__init__.py` files use to surface submodules — would otherwise
    dodge every check below it silently."""
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    yield node.module
            else:
                yield _resolve_relative(path, node.level, node.module)


def _cases(layer):
    return pytest.mark.parametrize(
        "path", _modules(layer), ids=lambda p: str(p.relative_to(PACKAGE)))


@_cases("domain")
def test_the_domain_reaches_no_framework(path):
    for name in _imported_names(path):
        assert name.split(".")[0] not in FRAMEWORKS, (
            f"{path.name} imports {name}; the domain classifies cases and must "
            f"not know how they were read or where they are served")


@pytest.mark.parametrize("layer", sorted(ALLOWED))
def test_each_layer_imports_only_inward(layer):
    for path in _modules(layer):
        for name in _imported_names(path):
            parts = name.split(".")
            if parts[0] != "tcm" or len(parts) < 2 or parts[1] == "settings":
                continue
            assert parts[1] in ALLOWED[layer], (
                f"tcm/{layer}/{path.name} imports {name}, which points outward; "
                f"{layer} may only reach {sorted(ALLOWED[layer])}")


def test_only_the_web_layer_knows_about_flask():
    for layer in ("domain", "infrastructure", "services"):
        for path in _modules(layer):
            for name in _imported_names(path):
                assert name.split(".")[0] != "flask", (
                    f"tcm/{layer}/{path.name} imports flask; HTTP is the web "
                    f"layer's business and nothing below it should have one")


def test_layer_directories_match_the_allowed_table():
    """`_modules()` returns `[]` both for a layer `ALLOWED` names that hasn't
    been built on disk yet (there is no such layer today — all four exist —
    but a future one named in `ALLOWED` ahead of its first module would look
    exactly like this) and for a layer whose directory name was mistyped or
    renamed out from under `ALLOWED` (a silent hole, since a parametrize over
    `[]` collects nothing and the tests above simply stop checking anything
    for it). This pins both directions: every layer-shaped directory that
    exists under `tcm/` must be a key `ALLOWED` knows, and every key
    `ALLOWED` knows that already exists on disk must contain at least one
    module — a directory present but empty of `.py` files would pass the
    other tests vacuously too.
    """
    on_disk = {
        p.name for p in PACKAGE.iterdir()
        if p.is_dir() and p.name != "__pycache__"
    }
    assert on_disk <= set(ALLOWED), (
        f"tcm/ has a layer directory {sorted(on_disk - set(ALLOWED))} that "
        f"ALLOWED doesn't name; add it there before it can be policed")
    for layer in on_disk:
        assert _modules(layer), (
            f"tcm/{layer} exists but contains no .py files; the layering "
            f"tests would pass on it without checking anything")


def test_resolve_relative_import_resolves_to_the_absolute_name():
    """`_resolve_relative` is what stands between a relative import and
    going unseen by every check above; cover its arithmetic directly rather
    than trusting it through whichever real files happen to use it today."""
    status = PACKAGE / "domain" / "status.py"
    init = PACKAGE / "domain" / "__init__.py"
    # from . import x  (inside a regular module: names its own package)
    assert _resolve_relative(status, 1, None) == "tcm.domain"
    # from . import x  (inside __init__.py: same package, not its parent)
    assert _resolve_relative(init, 1, None) == "tcm.domain"
    # from .sibling import y
    assert _resolve_relative(status, 1, "case") == "tcm.domain.case"
    # from ..infrastructure import report  (crosses layers, one level up)
    assert _resolve_relative(status, 2, "infrastructure") == "tcm.infrastructure"
