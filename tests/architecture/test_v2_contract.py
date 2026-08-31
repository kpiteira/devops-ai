"""The framework's own structural gate: the v2 contract's load-bearing surfaces hold.

These assert the *shape* of the contract layer — the pieces whose silent drift would
hollow out the contract without any functional test noticing.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ESCAPE_VALVE = (
    "If a stated fact is false, a decision conflicts with what's actually in "
    "the codebase, or an acceptance test contradicts a job: stop and describe "
    "what you found. Don't comply, and don't classify the problem yourself."
)


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text()


def normalized(text: str) -> str:
    return " ".join(text.replace(">", " ").replace("*", " ").split())


def test_task_pipeline_stays_removed() -> None:
    for gone in ("skills/kplan", "skills/kloop", "skills/kdesign",
                 "rules/tdd.md", "rules/handoffs.md", "templates/acp.md"):
        assert not (ROOT / gone).exists(), f"{gone} crept back in"


def test_v2_lifecycle_surfaces_exist() -> None:
    required = (
        "docs/designs/v2-contract/CONTRACT.md",
        "rules/outcome-contracts.md",
        "rules/test-quality.md",
        "skills/kspec/SKILL.md",
        "skills/kspec/intent-spec.md",
        "skills/kspec/work-brief.md",
        "skills/kspec/feature-close-report.md",
        "skills/kspec/glossary.md",
        "skills/kbuild/SKILL.md",
        "skills/kbuild/divergence-report.md",
        ".devops-ai/check_contract_integrity.py",
        ".devops-ai/check_public_surface.py",
    )
    missing = [p for p in required if not (ROOT / p).is_file()]
    assert not missing, missing


def test_escape_valve_is_verbatim_in_brief_template_and_executor_skill() -> None:
    assert ESCAPE_VALVE in normalized(read("skills/kspec/work-brief.md"))
    assert ESCAPE_VALVE in normalized(read("skills/kbuild/SKILL.md"))


def test_executor_skill_never_claims_the_grader() -> None:
    build = read("skills/kbuild/SKILL.md")
    assert "Acceptance tests are read-only" in build
    assert "writable only in planning and re-planning sessions" in build


def test_contract_guard_protects_briefs_and_acceptance_tests() -> None:
    guard = read(".devops-ai/check_contract_integrity.py")
    assert "tests/acceptance" in guard
    assert "docs/specs/" in guard
    assert 'startswith(("spec/", "replan/"))' in guard


def test_ci_runs_the_guard_from_the_base_commit() -> None:
    ci = read(".github/workflows/ci.yml")
    assert "fetch-depth: 0" in ci
    assert "base.sha }}:.devops-ai/check_contract_integrity.py" in ci, (
        "the guard must be executed from the PR's base commit, or a PR could "
        "neuter the check it is judged by"
    )


def test_generated_guard_matches_dogfooded_copy() -> None:
    from devops_ai.cli.quality import (
        generate_contract_integrity_check,
        generate_public_surface_check,
    )

    guard = read(".devops-ai/check_contract_integrity.py")
    signal = read(".devops-ai/check_public_surface.py")
    assert guard == generate_contract_integrity_check()
    assert signal == generate_public_surface_check()
