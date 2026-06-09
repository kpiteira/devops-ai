"""Architecture invariants — structural gates (see devops-ai `rules/structural-gates.md`).

These tests gate code STRUCTURE the way ruff gates style: they fail red, you fix the code.
Never fix a failure by editing a threshold, a contract, or the ratchet — widening anything
requires explicit human sign-off, recorded in the handoff.

Starter template: adjust SRC_ROOT and the CONTRACTS below to this project's
ARCHITECTURE.md, delete contracts that don't apply, then delete this paragraph.
"""

from __future__ import annotations

import ast
from pathlib import Path

# --- Configuration -------------------------------------------------------------------

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"

MAX_FILE_LINES = 400
MAX_CLASSES_PER_MODULE = 8

# Layering contracts: (importing package prefix, forbidden import prefixes, reason).
# Example: ("myapp.domain", ("myapp.api", "fastapi"), "domain stays transport-free")
LAYERING: list[tuple[str, tuple[str, ...], str]] = []

# Pattern uniqueness: (glob of files allowed to define it, class-name suffix, reason).
# Example: ("results.py", "Result", "result types live in one module")
UNIQUE_PATTERNS: list[tuple[str, str, str]] = []

# Ratchet: violations that pre-date this gate, frozen at their size at introduction.
# Entries may only be REMOVED (when the file comes into compliance) — never added or
# raised. relative path -> line count at freeze time.
FILE_LINES_RATCHET: dict[str, int] = {}


# --- Helpers --------------------------------------------------------------------------


def _source_files() -> list[Path]:
    return [p for p in SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts]


def _rel(path: Path) -> str:
    return str(path.relative_to(SRC_ROOT))


def _module_name(path: Path) -> str:
    parts = path.relative_to(SRC_ROOT).with_suffix("").parts
    return ".".join(parts[:-1] + (parts[-1],)).removesuffix(".__init__")


def _imports(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


# --- Gates ----------------------------------------------------------------------------


def test_file_budgets() -> None:
    """No source file beyond MAX_FILE_LINES; ratcheted files may only shrink."""
    over, stale_ratchet = [], []
    for path in _source_files():
        lines = len(path.read_text().splitlines())
        frozen = FILE_LINES_RATCHET.get(_rel(path))
        if frozen is not None:
            if lines <= MAX_FILE_LINES:
                stale_ratchet.append(_rel(path))  # compliant now — remove its entry
            elif lines > frozen:
                over.append(f"{_rel(path)}: {lines} lines (ratchet froze it at {frozen})")
        elif lines > MAX_FILE_LINES:
            over.append(f"{_rel(path)}: {lines} lines (max {MAX_FILE_LINES})")
    assert not over, "File budget exceeded — split the module:\n" + "\n".join(over)
    assert not stale_ratchet, (
        "Ratchet entries now compliant — delete them so they can't regress:\n"
        + "\n".join(stale_ratchet)
    )


def test_module_class_caps() -> None:
    """No module collects more than MAX_CLASSES_PER_MODULE classes/dataclasses."""
    over = []
    for path in _source_files():
        tree = ast.parse(path.read_text())
        count = sum(isinstance(n, ast.ClassDef) for n in ast.iter_child_nodes(tree))
        if count > MAX_CLASSES_PER_MODULE:
            over.append(f"{_rel(path)}: {count} classes (max {MAX_CLASSES_PER_MODULE})")
    assert not over, "Module shape violated — extract a package:\n" + "\n".join(over)


def test_layering_contracts() -> None:
    """Imports respect the layering declared in ARCHITECTURE.md."""
    violations = []
    for path in _source_files():
        module = _module_name(path)
        imported = _imports(ast.parse(path.read_text()))
        for prefix, forbidden, reason in LAYERING:
            if not module.startswith(prefix):
                continue
            for name in imported:
                if name.startswith(forbidden):
                    violations.append(f"{_rel(path)} imports {name} ({reason})")
    assert not violations, "Layering contract violated:\n" + "\n".join(violations)


def test_pattern_uniqueness() -> None:
    """One mechanism per job: pattern-bearing classes live only where declared."""
    violations = []
    for path in _source_files():
        tree = ast.parse(path.read_text())
        classes = [n.name for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef)]
        for allowed_glob, suffix, reason in UNIQUE_PATTERNS:
            if path.match(allowed_glob):
                continue
            for name in classes:
                if name.endswith(suffix):
                    violations.append(f"{_rel(path)}: class {name} ({reason})")
    assert not violations, "Pattern uniqueness violated:\n" + "\n".join(violations)
