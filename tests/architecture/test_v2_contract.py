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


# --- v7: the pilot synthesis (docs/designs/v2-contract/REVIEW.md) ---


def test_contract_is_v7_and_names_the_pilot_findings() -> None:
    contract = read("docs/designs/v2-contract/CONTRACT.md")
    assert "v7" in contract.splitlines()[2], "header line carries the version"
    for phrase in (
        "product semantics",          # escalation bar
        "Decisions I made alone",     # executor's channel
        "For the human",
        "Facts I corrected",          # T1 fact-correction path
        "integration-level",          # T2 labeled blocking tests
        "observer",                   # T3 the seat
        "kobserve",
        "Independent verification",   # named, wiring deferred to EVOLUTIONS #5
    ):
        assert phrase in contract, phrase


def test_rules_carry_the_pilot_obligations() -> None:
    contracts = read("rules/outcome-contracts.md")
    for phrase in ("Decisions I made alone", "For the human", "Facts I corrected"):
        assert phrase in contracts, phrase
    quality = read("rules/test-quality.md").lower()
    for phrase in ("opposite reading", "clock and timezone", "run-to-the-end",
                   "rendered output", "measured on main"):
        assert phrase in quality, phrase
    assert "integration-level" in read("rules/testing-taxonomy.md")
    assert "review rounds" in read("rules/quality-gates.md")
    assert "restart" in read("rules/effort-and-model-calibration.md")


def test_brief_template_pins_the_completeness_prompts() -> None:
    brief = read("skills/kspec/work-brief.md")
    for phrase in (
        "## Working environment",
        "Measured on main",
        "channel is down",
        "rejected alternative",
        "enumerates",
    ):
        assert phrase in brief, phrase


def test_spec_template_splits_amendments() -> None:
    spec = read("skills/kspec/intent-spec.md")
    assert "- [x]" in spec and "fact-correction" in spec, (
        "fact-corrections are logged pre-checked; decision/outcome changes block"
    )


def test_close_report_promotes_by_kind_and_has_outside_notes() -> None:
    report = read("skills/kspec/feature-close-report.md")
    assert "Outside the outcomes" in report
    for kind in ("e2e", "integration", "unit", "drop"):
        assert kind in report, kind


def test_planner_skill_carries_the_signoff_and_measurement_rules() -> None:
    spec_skill = read("skills/kspec/SKILL.md")
    for phrase in (
        "per-item yes",
        "what the tests pin",
        "Measured on main",
        "opposite reading",
        "instance",           # framework semantics vs instance configuration
        "kobserve",
        "grep",               # archive sweep
    ):
        assert phrase in spec_skill, phrase


def test_executor_skill_has_the_three_pr_sections_and_fact_path() -> None:
    build = read("skills/kbuild/SKILL.md")
    for phrase in ("Decisions I made alone", "For the human", "Facts I corrected"):
        assert phrase in build, phrase
    assert "fresh-context review" in build.lower()


def test_pr_ownership_rule_reaches_the_babysitter() -> None:
    assert "owns" in read("skills/kbabysit/SKILL.md")


def test_babysit_loop_is_pinned_to_a_forked_opus_subagent() -> None:
    """The loop must not run inline on the invoking session's tier (issue #25).

    Twice observed running inline on a top-tier session because the tier lived in
    prose. It lives in frontmatter now, and this is what keeps it there.
    """
    frontmatter = read("skills/kbabysit/SKILL.md").split("---")[1]
    fields = dict(
        line.split(":", 1) for line in frontmatter.splitlines() if ": " in line
    )
    assert fields.get("context", "").strip() == "fork"
    assert fields.get("agent", "").strip() == "general-purpose"
    assert "opus" in fields.get("model", "").strip()


def test_observer_skill_exists_with_its_launch_guards() -> None:
    skill = read("skills/kobserve/SKILL.md")
    for phrase in ("--group", "model", "checkout", "For the human", "kinfra done"):
        assert phrase in skill, phrase


def test_project_config_template_lists_standing_gates() -> None:
    assert "Standing PR gates" in read("templates/project-config.md")
