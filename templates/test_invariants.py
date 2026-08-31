"""Architecture invariants — structural gates (devops-ai `rules/structural-gates.md`).

These tests gate code STRUCTURE the way ruff gates style: they fail red, you fix
the code. Never fix a failure by editing a threshold, a contract, or the ratchet —
widening anything requires explicit human sign-off, recorded in the feature's spec.

Starter template: adjust SRC_ROOT and the Configuration block below (LAYERING,
UNIQUE_PATTERNS, ratchets, …) to this project's ARCHITECTURE.md, delete entries
that don't apply, then delete this paragraph.
"""

from __future__ import annotations

import ast
from pathlib import Path

# --- Configuration -------------------------------------------------------------------

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"

MAX_FILE_LINES = 400
MAX_CLASSES_PER_MODULE = 8

# Layering contracts: (importing package prefix, forbidden import prefixes, reason).
# Prefixes match on module boundaries: "myapp.api" forbids "myapp.api.routes" but
# not "myapp.apiclient". Relative imports are resolved before checking.
# Example: ("myapp.domain", ("myapp.api", "fastapi"), "domain stays transport-free")
LAYERING: list[tuple[str, tuple[str, ...], str]] = []

# Pattern uniqueness: (glob of files allowed to define it, class-name suffix, reason).
# Example: ("results.py", "Result", "result types live in one module")
UNIQUE_PATTERNS: list[tuple[str, str, str]] = []

# Ratchet: violations that pre-date this gate, frozen at their size at introduction.
# Entries may only be REMOVED (when the file comes into compliance) — never added or
# raised. relative path -> line count at freeze time.
FILE_LINES_RATCHET: dict[str, int] = {}

# Test honesty (see the `test-quality` rule): fakes at I/O seams, not patches everywhere.
# The contract governs UNIT tests (the testing-taxonomy rule lets integration
# tests use what they need) — widen to parents[1] for stricter enforcement.
TESTS_ROOT = Path(__file__).resolve().parents[1] / "unit"
MAX_PATCHES_PER_TEST_FILE = 5
# Patching first-party code welds tests to internal structure. Set to your package
# prefix(es), e.g. ("myapp",). Empty disables the gate.
FIRST_PARTY_PREFIXES: tuple[str, ...] = ()
# Pre-existing offenders, frozen: test file -> patch count at freeze time.
PATCH_RATCHET: dict[str, int] = {}
# Pre-existing first-party patching, frozen: test file -> first-party patch count.
FIRST_PARTY_PATCH_RATCHET: dict[str, int] = {}


# --- Helpers --------------------------------------------------------------------------


def _source_files() -> list[Path]:
    if not SRC_ROOT.is_dir():
        return []
    return [p for p in SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts]


def _rel(path: Path) -> str:
    return str(path.relative_to(SRC_ROOT))


def _module_name(path: Path) -> str:
    parts = path.relative_to(SRC_ROOT).with_suffix("").parts
    return ".".join(parts).removesuffix(".__init__")


def _test_files() -> list[Path]:
    if not TESTS_ROOT.is_dir():
        return []
    me = Path(__file__).resolve()
    return [
        p
        for pattern in ("test_*.py", "conftest.py")
        for p in sorted(TESTS_ROOT.rglob(pattern))
        if "__pycache__" not in p.parts and p.resolve() != me
    ]


def _parse_or_none(path: Path) -> ast.AST | None:
    """Parse a file, or return None — test_gates_are_armed reports the failures,
    so one broken file doesn't crash every gate with the same stack trace."""
    try:
        return ast.parse(path.read_text())
    except SyntaxError:
        return None


def _within(name: str, prefix: str) -> bool:
    """Module-boundary prefix match: 'myapp.api' covers 'myapp.api.routes',
    not 'myapp.apiclient'."""
    return name == prefix or name.startswith(prefix + ".")


def _patch_calls(tree: ast.AST) -> list[ast.Call]:
    """Calls that patch running code: patch()/patch.object()/patch.dict() — bare,
    aliased, or via mock/mocker — plus monkeypatch.setattr(). Approximate by design."""
    aliases = {"patch"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module in ("unittest.mock", "mock"):
                aliases.update(
                    a.asname or a.name for a in node.names if a.name == "patch"
                )

    def is_patch_ref(f: ast.expr) -> bool:
        # `patch` / an alias of it / `mock.patch` / `mocker.patch`
        return (isinstance(f, ast.Name) and f.id in aliases) or (
            isinstance(f, ast.Attribute) and f.attr == "patch"
        )

    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        is_patch = (
            is_patch_ref(f)
            or (
                isinstance(f, ast.Attribute)
                and f.attr in ("object", "dict")
                and is_patch_ref(f.value)
            )
            or (
                isinstance(f, ast.Attribute)
                and f.attr == "setattr"
                and isinstance(f.value, ast.Name)
                and f.value.id == "monkeypatch"
            )
        )
        if is_patch:
            calls.append(node)
    return calls


def _local_imports(tree: ast.AST) -> dict[str, str]:
    """Local name -> dotted path it was imported as, for resolving patch.object
    targets like `patch.object(services, "save")` back to real modules."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    out[a.asname] = a.name
                else:
                    root = a.name.split(".")[0]
                    out[root] = root
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for a in node.names:
                out[a.asname or a.name] = f"{node.module}.{a.name}"
    return out


def _dotted(node: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _first_party_target(call: ast.Call, imports: dict[str, str]) -> str | None:
    """The first-party thing this call patches, or None. Resolves string targets,
    bare names, and dotted expressions through the file's imports."""
    if not call.args:
        return None
    target = call.args[0]
    if isinstance(target, ast.Constant) and isinstance(target.value, str):
        name = target.value
    else:
        dotted = _dotted(target)
        if dotted is None:
            return None
        root, _, rest = dotted.partition(".")
        resolved = imports.get(root)
        if resolved is None:
            return None
        name = f"{resolved}.{rest}" if rest else resolved
    if any(_within(name, prefix) for prefix in FIRST_PARTY_PREFIXES):
        return name
    return None


def _imports(tree: ast.AST, package: str) -> list[str]:
    """All imported module names, with relative imports resolved against `package`
    (the dotted package containing the file)."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.append(node.module)
            elif node.level:
                parts = package.split(".") if package else []
                if node.level - 1 > len(parts):
                    continue  # escapes SRC_ROOT — nothing to resolve against
                base_parts = parts[: len(parts) - (node.level - 1)]
                base = ".".join(base_parts)
                if node.module:
                    names.append(f"{base}.{node.module}" if base else node.module)
                else:
                    names.extend(
                        f"{base}.{a.name}" if base else a.name for a in node.names
                    )
    return names


def _package(path: Path) -> str:
    return ".".join(path.parent.relative_to(SRC_ROOT).parts)


# --- Gates ----------------------------------------------------------------------------


def test_gates_are_armed() -> None:
    """Misconfiguration must fail loudly: a missing SRC_ROOT or an unparseable file
    would silently exempt code from every gate below."""
    assert SRC_ROOT.is_dir(), (
        f"SRC_ROOT not found: {SRC_ROOT} — fix the path at the top of this file"
    )
    files = _source_files()
    assert files, f"No Python sources under {SRC_ROOT} — the gates are checking nothing"
    bad = [_rel(p) for p in files if _parse_or_none(p) is None]
    bad += [
        str(p.relative_to(TESTS_ROOT))
        for p in _test_files()
        if _parse_or_none(p) is None
    ]
    assert not bad, "Unparseable files are exempt from every gate:\n" + "\n".join(bad)


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
                over.append(
                    f"{_rel(path)}: {lines} lines (ratchet froze it at {frozen})"
                )
        elif lines > MAX_FILE_LINES:
            over.append(f"{_rel(path)}: {lines} lines (max {MAX_FILE_LINES})")
    assert not over, "File budget exceeded — split the module:\n" + "\n".join(over)
    assert not stale_ratchet, (
        "Ratchet entries now compliant — delete them so they can't regress:\n"
        + "\n".join(stale_ratchet)
    )


def test_module_class_caps() -> None:
    """No module collects more than MAX_CLASSES_PER_MODULE classes/dataclasses
    (nested classes count — a god-file hidden inside one class is still a god-file)."""
    over = []
    for path in _source_files():
        tree = _parse_or_none(path)
        if tree is None:
            continue
        count = sum(isinstance(n, ast.ClassDef) for n in ast.walk(tree))
        if count > MAX_CLASSES_PER_MODULE:
            over.append(f"{_rel(path)}: {count} classes (max {MAX_CLASSES_PER_MODULE})")
    assert not over, "Module shape violated — extract a package:\n" + "\n".join(over)


def test_layering_contracts() -> None:
    """Imports respect the layering declared in ARCHITECTURE.md."""
    violations = []
    for path in _source_files():
        tree = _parse_or_none(path)
        if tree is None:
            continue
        module = _module_name(path)
        imported = _imports(tree, _package(path))
        for prefix, forbidden, reason in LAYERING:
            if not _within(module, prefix):
                continue
            for name in imported:
                if any(_within(name, f) for f in forbidden):
                    violations.append(f"{_rel(path)} imports {name} ({reason})")
    assert not violations, "Layering contract violated:\n" + "\n".join(violations)


def test_patch_density() -> None:
    """Patching is a coupling smell; fakes at I/O seams keep tests refactor-proof."""
    over, stale_ratchet = [], []
    for path in _test_files():
        rel = str(path.relative_to(TESTS_ROOT))
        tree = _parse_or_none(path)
        if tree is None:
            continue
        count = len(_patch_calls(tree))
        frozen = PATCH_RATCHET.get(rel)
        if frozen is not None:
            if count <= MAX_PATCHES_PER_TEST_FILE:
                stale_ratchet.append(rel)  # compliant now — remove its entry
            elif count > frozen:
                over.append(f"{rel}: {count} patches (ratchet froze it at {frozen})")
        elif count > MAX_PATCHES_PER_TEST_FILE:
            over.append(f"{rel}: {count} patches (max {MAX_PATCHES_PER_TEST_FILE})")
    assert not over, (
        "Patch density exceeded — replace patches with fakes at the I/O seam:\n"
        + "\n".join(over)
    )
    assert not stale_ratchet, (
        "Ratchet entries now compliant — delete them so they can't regress:\n"
        + "\n".join(stale_ratchet)
    )


def test_no_first_party_patching() -> None:
    """patch("yourpkg.x.y") — or patch.object(yourmodule, "y") — welds the test to
    internal structure; use a fake at the I/O seam instead."""
    if not FIRST_PARTY_PREFIXES:
        return
    violations, stale_ratchet = [], []
    for path in _test_files():
        rel = str(path.relative_to(TESTS_ROOT))
        tree = _parse_or_none(path)
        if tree is None:
            continue
        imports = _local_imports(tree)
        hits = [
            target
            for call in _patch_calls(tree)
            if (target := _first_party_target(call, imports)) is not None
        ]
        frozen = FIRST_PARTY_PATCH_RATCHET.get(rel)
        if frozen is not None:
            if not hits:
                stale_ratchet.append(rel)  # compliant now — remove its entry
            elif len(hits) > frozen:
                violations.append(
                    f"{rel}: {len(hits)} first-party patches "
                    f"(ratchet froze it at {frozen})"
                )
        else:
            violations.extend(f"{rel}: patches {target}" for target in hits)
    assert not violations, (
        "First-party patching — test through the public surface instead:\n"
        + "\n".join(violations)
    )
    assert not stale_ratchet, (
        "Ratchet entries now compliant — delete them so they can't regress:\n"
        + "\n".join(stale_ratchet)
    )


def test_pattern_uniqueness() -> None:
    """One mechanism per job: pattern-bearing classes live only where declared."""
    violations = []
    for path in _source_files():
        tree = _parse_or_none(path)
        if tree is None:
            continue
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        for allowed_glob, suffix, reason in UNIQUE_PATTERNS:
            if path.match(allowed_glob):
                continue
            for name in classes:
                if name.endswith(suffix):
                    violations.append(f"{_rel(path)}: class {name} ({reason})")
    assert not violations, "Pattern uniqueness violated:\n" + "\n".join(violations)
