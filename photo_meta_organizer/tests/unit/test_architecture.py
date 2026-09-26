"""PMO-22: the dependency rule, checked on the source (a tiny import-linter).

Clean Architecture here means dependencies point inward:
``api``/``main`` -> ``application`` -> ``domain``, and ``infrastructure`` implements
the ``application.interfaces`` Protocols. The only exception is the composition root,
``application/composition.py``, whose job is to pick the concrete classes.
"""

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PKG = "photo_meta_organizer"

# The composition root may name concrete infrastructure classes; nothing else inward may.
COMPOSITION_ROOTS = {"application/composition.py"}


def _modules(layer: str):
    for path in sorted((PACKAGE_ROOT / layer).rglob("*.py")):
        yield path.relative_to(PACKAGE_ROOT).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def _imported_modules(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


def _violations(layer: str, forbidden: tuple[str, ...]):
    found = []
    for rel, tree in _modules(layer):
        if rel in COMPOSITION_ROOTS:
            continue
        for name in _imported_modules(tree):
            if any(name == f or name.startswith(f + ".") for f in forbidden):
                found.append(f"{rel} imports {name}")
    return found


def _outer(*layers: str) -> tuple[str, ...]:
    return tuple(f"{PKG}.{layer}" for layer in layers) + tuple(layers)


@pytest.mark.unit
class TestDependencyRule:
    def test_domain_imports_no_outer_layer(self) -> None:
        assert _violations("domain", _outer("application", "infrastructure", "api", "main")) == []

    def test_application_imports_no_infrastructure_or_api(self) -> None:
        assert _violations("application", _outer("infrastructure", "api", "main")) == []

    def test_infrastructure_does_not_import_api_or_cli(self) -> None:
        assert _violations("infrastructure", _outer("api", "main")) == []


@pytest.mark.unit
class TestDomainHasNoIO:
    """Domain services are pure: no file opening, no stat/resolve, no os calls."""

    FORBIDDEN_MODULES = ("os", "shutil", "glob", "io")

    def test_domain_does_not_import_filesystem_modules(self) -> None:
        bad = []
        for rel, tree in _modules("domain"):
            for name in _imported_modules(tree):
                if name.split(".")[0] in self.FORBIDDEN_MODULES:
                    bad.append(f"{rel} imports {name}")
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "pathlib":
                    concrete = [a.name for a in node.names if not a.name.startswith("Pure")]
                    if concrete:
                        bad.append(f"{rel} imports pathlib.{', '.join(concrete)}")
        assert bad == []

    def test_domain_never_calls_open(self) -> None:
        calls = [
            rel
            for rel, tree in _modules("domain")
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
        ]
        assert calls == []
