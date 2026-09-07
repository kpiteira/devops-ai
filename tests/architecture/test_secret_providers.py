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

SPECIFIC_PROVIDER_IMPORT = re.compile(
    r"^\s*(?:from\s+devops_ai\.secrets\.providers\.\w+\s+import"
    r"|import\s+devops_ai\.secrets\.providers\.\w+"
    r"|from\s+\.providers\.\w+\s+import"
    r"|from\s+\.providers\s+import\s+\w+)",
    re.MULTILINE,
)
SIBLING_IMPORT = re.compile(
    r"^\s*(?:from\s+\.\s*(\w+)\s+import|from\s+devops_ai\.secrets\.providers\.(\w+)\s+import)",
    re.MULTILINE,
)
CLI_IMPORT = re.compile(r"^\s*(?:from|import)\s+devops_ai\.cli\b", re.MULTILINE)


def provider_modules() -> list[Path]:
    return sorted(
        p for p in PROVIDERS.glob("*.py") if p.name != "__init__.py"
    )


def test_providers_package_exists_with_one_module_per_scheme() -> None:
    assert PROVIDERS.is_dir(), "src/devops_ai/secrets/providers/ must exist"
    modules = provider_modules()
    assert len(modules) >= 3, (
        "M1 ships at least env, dotenv, and 1Password as separate modules; "
        f"found {[m.name for m in modules]}"
    )


def test_nothing_outside_the_package_names_a_provider_module() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        if PROVIDERS in path.parents:
            continue
        if SPECIFIC_PROVIDER_IMPORT.search(path.read_text()):
            offenders.append(str(path.relative_to(ROOT)))
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
            target = match.group(1) or match.group(2)
            if target in names and target != module.stem:
                offenders.append(f"{module.name} imports sibling {target}")
        if CLI_IMPORT.search(text):
            offenders.append(f"{module.name} imports devops_ai.cli")
    assert not offenders, offenders
