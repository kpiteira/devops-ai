"""Structural gate for the secret-providers feature: providers are pluggable.

Adding a provider means adding one module under the providers package. Enforced here,
by AST rather than regex so multiline and relative imports cannot slip through:

- one scheme literal (``op://``, ``dotenv://`` …) per provider module, and the M1 set
  is covered — scheme-to-module is decided by content, not by file naming;
- scheme literals live only inside the providers package: the resolver and kinfra's
  provisioning cannot hard-code a scheme, so they must discover providers;
- nothing outside the package imports a provider module by name (statically or via
  a dynamic-import string), providers do not import each other, and providers never
  import the CLI package.

Enforced structure is run, not read.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "devops_ai"
SECRETS = SRC / "secrets"
PROVIDERS = SECRETS / "providers"
PROVIDERS_PKG = "devops_ai.secrets.providers"
REQUIRED_SCHEMES = {"env://", "dotenv://", "op://"}
SCHEME = re.compile(r"\b[a-z][a-z0-9+.-]*://")

# Standing gate: live once secret-providers M1 has created the package. Until then
# the M1 acceptance test (test_providers_package_is_in_place) is the non-skipping
# check, so an executor cannot satisfy M1 by building elsewhere.
pytestmark = pytest.mark.skipif(
    not PROVIDERS.is_dir(), reason="secret-providers M1 not delivered yet"
)


def provider_modules() -> list[Path]:
    """One module per provider; `_`-prefixed modules are shared code, not providers."""
    return sorted(
        p for p in PROVIDERS.glob("*.py")
        if p.name != "__init__.py" and not p.name.startswith("_")
    )


def module_name(path: Path) -> str:
    rel = path.relative_to(SRC.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def string_constants(tree: ast.AST) -> Iterator[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def imports_of(path: Path) -> set[str]:
    """Absolute dotted names this module imports (relative imports resolved)."""
    tree = ast.parse(path.read_text())
    package = module_name(path)
    if path.name != "__init__.py":
        package = package.rpartition(".")[0]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package.split(".")
                base = ".".join(base_parts[: len(base_parts) - node.level + 1])
                base = f"{base}.{node.module}" if node.module else base
            else:
                base = node.module or ""
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    # dynamic imports: any string literal that spells a provider module path
    for text in string_constants(tree):
        if "providers." in text or text.startswith("."):
            names.add(text.lstrip("."))
    return names


def schemes_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {m.group(0) for s in string_constants(tree) for m in SCHEME.finditer(s)}


def test_one_scheme_per_provider_module_and_required_schemes_covered() -> None:
    owners: dict[str, list[str]] = {}
    for module in provider_modules():
        for scheme in schemes_in(module):
            owners.setdefault(scheme, []).append(module.name)
    shared = {s: m for s, m in owners.items() if len(m) > 1}
    assert not shared, f"a scheme literal must appear in exactly one provider: {shared}"
    missing = REQUIRED_SCHEMES - set(owners)
    assert not missing, f"no provider module carries {sorted(missing)}"


def test_scheme_literals_live_only_in_the_providers_package() -> None:
    """The resolver and kinfra provisioning discover providers, never name a scheme."""
    known = {s for m in provider_modules() for s in schemes_in(m)}
    core = [p for p in SECRETS.rglob("*.py") if PROVIDERS not in p.parents]
    core.append(SRC / "provision.py")
    offenders = {
        str(p.relative_to(ROOT)): sorted(schemes_in(p) & known)
        for p in core
        if p.exists() and schemes_in(p) & known
    }
    assert not offenders, f"scheme literals outside providers/: {offenders}"


def test_nothing_outside_the_package_names_a_provider_module() -> None:
    stems = {m.stem for m in provider_modules()}
    targets = {f"{PROVIDERS_PKG}.{s}" for s in stems}
    targets |= {f"providers.{s}" for s in stems}
    offenders = {}
    for path in SRC.rglob("*.py"):
        if PROVIDERS in path.parents:
            continue
        hit = sorted(
            n for n in imports_of(path)
            if n in targets or any(n.startswith(t + ".") for t in targets)
        )
        if hit:
            offenders[str(path.relative_to(ROOT))] = hit
    assert not offenders, (
        "the resolver/CLI must discover providers, not import them by name: "
        f"{offenders}"
    )


def test_provider_modules_are_independent_of_each_other_and_of_the_cli() -> None:
    stems = {m.stem for m in provider_modules()}
    offenders = []
    for module in provider_modules():
        for name in imports_of(module):
            if name.startswith("devops_ai.cli"):
                offenders.append(f"{module.name} imports {name}")
            for other in stems - {module.stem}:
                if name == f"{PROVIDERS_PKG}.{other}" or name.startswith(
                    f"{PROVIDERS_PKG}.{other}."
                ):
                    offenders.append(f"{module.name} imports sibling {other}")
    assert not offenders, offenders
