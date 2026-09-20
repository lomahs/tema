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


def _imported_names(path):
    """Every module name `path` imports, absolute names only."""
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


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
