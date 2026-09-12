"""Structural gate for the secret-providers feature: providers are pluggable.

Adding a provider means adding one module under the providers package. Nothing
outside that package may name a specific provider module, and provider modules
may not reach into each other or into the CLI. Enforced structure is run, not read.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "devops_ai"
PROVIDERS = SRC / "secrets" / "providers"

# Standing gate: live once secret-providers M1 has created the package. Until then
# the M1 acceptance test (test_providers_package_is_in_place) is the non-skipping
# check, so an executor cannot satisfy M1 by building elsewhere.
pytestmark = pytest.mark.skipif(
    not PROVIDERS.is_dir(), reason="secret-providers M1 not delivered yet"
)

# `from .providers import X` / `from devops_ai.secrets.providers import X` — X may be
# a package-level helper (fine) or a provider module (not fine); decided by name.
PACKAGE_IMPORT = re.compile(
    r"^\s*from\s+(?:devops_ai\.secrets\.providers|\.providers)\s+import\s+([^\n#]+)",
    re.MULTILINE,
)
MODULE_IMPORT = re.compile(
    r"^\s*(?:from\s+(?:devops_ai\.secrets\.providers|\.providers)\.(\w+)\s+import"
    r"|import\s+devops_ai\.secrets\.providers\.(\w+))",
    re.MULTILINE,
)
SIBLING_IMPORT = re.compile(
    r"^\s*(?:from\s+\.(\w+)\s+import"
    r"|from\s+devops_ai\.secrets\.providers\.(\w+)\s+import"
    r"|from\s+\.\s+import\s+([^\n#]+))",
    re.MULTILINE,
)
CLI_IMPORT = re.compile(r"^\s*(?:from|import)\s+devops_ai\.cli\b", re.MULTILINE)


def provider_modules() -> list[Path]:
    """One module per provider; `_`-prefixed modules are shared code, not providers."""
    return sorted(
        p for p in PROVIDERS.glob("*.py")
        if p.name != "__init__.py" and not p.name.startswith("_")
    )


def names_in(import_list: str) -> set[str]:
    return {n.strip().split(" as ")[0].strip("() ") for n in import_list.split(",")}


def test_providers_package_exists_with_one_module_per_scheme() -> None:
    assert PROVIDERS.is_dir(), "src/devops_ai/secrets/providers/ must exist"
    modules = provider_modules()
    assert len(modules) >= 3, (
        "M1 ships at least env, dotenv, and 1Password as separate modules; "
        f"found {[m.name for m in modules]}"
    )


def test_nothing_outside_the_package_names_a_provider_module() -> None:
    stems = {m.stem for m in provider_modules()}
    offenders = []
    for path in SRC.rglob("*.py"):
        if PROVIDERS in path.parents:
            continue
        text = path.read_text()
        named = {m.group(1) or m.group(2) for m in MODULE_IMPORT.finditer(text)}
        for m in PACKAGE_IMPORT.finditer(text):
            named |= names_in(m.group(1)) & stems
        if named & stems:
            offenders.append(f"{path.relative_to(ROOT)} names {sorted(named & stems)}")
    assert not offenders, (
        "the resolver/CLI must discover providers, not import them by name: "
        f"{offenders}"
    )


def test_provider_modules_are_independent_of_each_other_and_of_the_cli() -> None:
    names = {m.stem for m in provider_modules()}
    offenders = []
    for module in provider_modules():
        text = module.read_text()
        for match in SIBLING_IMPORT.finditer(text):
            targets = (
                names_in(match.group(3)) if match.group(3)
                else {match.group(1) or match.group(2)}
            )
            for target in targets & names - {module.stem}:
                offenders.append(f"{module.name} imports sibling {target}")
        if CLI_IMPORT.search(text):
            offenders.append(f"{module.name} imports devops_ai.cli")
    assert not offenders, offenders
