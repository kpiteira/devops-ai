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


def section(text: str, heading: str) -> str:
    """The body of one `## <heading>` section, up to the next `## ` heading."""
    marker = f"\n## {heading}\n"
    assert marker in text, f"no `## {heading}` section"
    rest = text[text.index(marker) + 1 :]
    end = rest.find("\n## ", 1)
    return rest if end == -1 else rest[:end]


def block(text: str, starts_with: str) -> str:
    """The blank-line-delimited paragraph that starts with `starts_with`.

    A phrase asserted against a whole section says only that *somewhere* in it the
    words survive. When the same phrase legitimately appears in two places, that is
    not enough: deleting it from the load-bearing one stays green. Naming the block
    is what makes an assertion point at a specific obligation.
    """
    for paragraph in text.split("\n\n"):
        if paragraph.lstrip().startswith(starts_with):
            return paragraph
    raise AssertionError(f"no paragraph starting {starts_with!r}")


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


def test_babysit_loop_runs_in_an_opus_session_and_says_so() -> None:
    """The loop must run on an Opus-grade invoking session (issue #25) — and must be
    visible in the session that runs it (2026-09-14).

    Twice observed running on whatever tier the invoking session happened to be,
    because the tier lived in prose; #45 moved it to frontmatter as ``context: fork``
    + ``model:``. The fork kept the tier and hid the loop: an agent-deck session
    running a forked babysit shows a status line and nothing else, with every round in
    a sidechain transcript (measured on #72 and #66). The human dropped the fork, so
    the tier is now the invoking session's own and the skill's preflight is what
    enforces it. This pins both halves of that: the frontmatter carries none of the
    four execution fields, and the preflight states an accept condition *and* rejects
    everything else — an informational ``MODEL:`` line that stopped nothing would be
    no gate at all.
    """
    skill = read("skills/kbabysit/SKILL.md")
    frontmatter = skill.split("---")[1]
    fields = dict(
        line.split(":", 1) for line in frontmatter.splitlines() if ": " in line
    )
    # All four fields #45 added, not just the two that fork on their own: the shape
    # this PR pins is a frontmatter with no execution pins in it whatsoever.
    for field in ("context", "agent", "background", "model"):
        assert field not in fields, f"execution pin `{field}:` is back in frontmatter"
    preflight = skill.split("## 0. Preflight", 1)[1].split("## 1.", 1)[0]
    # The accept condition, on the MODEL: line itself — "opus" anywhere in the section
    # is also satisfied by the rejection text, which would pass with the accept branch
    # gone or naming any model at all.
    assert "MODEL: claude-opus" in preflight
    # The rejection branch: the check has to end the run, not merely report a tier.
    assert "ends the run here" in preflight
    assert "agent-deck" in preflight
    # A one-shot gate does not replace the frontmatter pin it removed: `model:` was
    # re-applied to every fork and so survived a restart, while a check that runs only
    # at step 0 does not. The pilot measured a session resuming on a different model
    # after a tmux restart and running on unnoticed, which is this PR's regression to
    # own, not a general observation.
    assert "on every resume" in preflight, (
        "the model gate must re-run after a restart, not only at step 0"
    )
    # The launch recipe is the mechanism the tier now rests on, so it has to be the
    # repo's launch contract rather than a recipe of its own: add (with a group and the
    # Opus model) → start → send. Two review rounds on #75 found two separate elements
    # missing, one per round; this is what stops the third.
    # Anchored to its own section, not to "the first bash block in the file" — the
    # skill has seven, and a positional split would go red for the unrelated reason
    # that someone added a block above this one.
    how = skill.split("## How this runs", 1)[1].split("\n## ", 1)[0]
    launch = how.split("```bash", 1)[1].split("```", 1)[0]
    for step in (
        "agent-deck add",
        "-g ",
        "--model claude-opus",
        "agent-deck session start",
        "agent-deck session send",
    ):
        assert step in launch, f"launch recipe is missing `{step}`"


def test_babysit_verdict_is_a_function_of_the_stop() -> None:
    """A verdict glyph with no rule attached is a menu, and menus get picked from.

    2026-09-14: three reports wrote ✅ merge-ready over stops that were not convergence
    — #66 and #75 over a `systemic — same mechanism as last round`, #77 over a
    second-order round that also hit the budget and that same repeat. The human read ✅
    as "the reviewer is done", and merged nothing. The rule that replaced the menu is
    prose, which is exactly how the line became a menu in the first place.

    Anchored per-paragraph rather than to the `## 5. Report` section: that section's
    body is a fenced ``markdown`` template whose own ``## Babysit report`` heading ends
    the section as ``section()`` computes it, so a section-scoped check here reads 109
    characters that contain none of these obligations and passes no matter what.
    """
    skill = read("skills/kbabysit/SKILL.md")

    # Every phrase below is matched against whitespace-collapsed text. These are
    # assertions about prose, and prose wraps: "conflicts the loop could not clear"
    # already spans a newline, so the literal substring is absent from a paragraph
    # that plainly contains the rule. Collapsing first means these gates go red for
    # the rule being gone and not for the paragraph being reflowed.
    def flat(text: str) -> str:
        return " ".join(text.split())

    # The template line itself carries the signal slots. Asserting `✅ merge-ready`
    # file-wide would stay green with the template reverted to a bare glyph menu,
    # because the rule paragraphs below quote the glyph too.
    verdict_line = flat(block(skill, "**Verdict:**"))
    for slot in ("(converged: <signal>)", "(stopped: <signal>)"):
        assert slot in verdict_line, f"Verdict template must carry `{slot}`"

    rule = flat(block(skill, "**The verdict is a function of the stop"))
    assert "*convergence* signal only" in rule
    # CI was once enumerated as ⚠️ *and* defined as ❌ in this same paragraph, which
    # left a CI stop with no determinate verdict. Both of ❌'s causes are pinned as a
    # set: pinning only the CI half is how this gate shipped first, and `or conflicts
    # the loop could not clear` could be deleted with every other assertion green.
    assert "never ⚠️" in rule, "CI must be ❌ alone — it was once in both lists"
    for cause in ("CI red", "conflicts the loop could not clear"):
        assert cause in rule, f"❌ must keep its `{cause}` cause"

    # Rounds routinely end on several signals at once; without a precedence rule the
    # convergence one could always be the one quoted.
    multi = flat(block(skill, "**When more than one signal fires"))
    assert "all of them to be convergence signals" in multi
    # The exception's *reason*, which occurs once. "not the binding constraint" reads
    # like the obligation but appears twice in this paragraph — once as the rule and
    # once inside the quoted #66 report — so asserting it leaves the rule deletable
    # with the quote alone keeping the test green.
    assert "the loop would have stopped anyway" in multi, (
        "the budget exception must keep the reason it is an exception"
    )


def test_observer_skill_exists_with_its_launch_guards() -> None:
    skill = read("skills/kobserve/SKILL.md")
    for phrase in (
        "--group",
        "model",
        "checkout",
        "For the human",
        "kinfra done",
        # 2026-09-14: an observer coined "merge-ready" over a ⚠️ report (PR #70)
        "Never upgrade a verdict",
        "verbatim",
    ):
        assert phrase in skill, phrase
    # Those two live outside `## verify` (the bullet is in `## Guardrails`, and
    # "verbatim" occurs three times in the file), so a whole-file check survives the
    # gate being stripped out of `verify` entirely. The verdict rule has two distinct
    # obligations inside `verify` and they are pinned one block each, because
    # "**Why the loop stopped:**" and "verbatim" appear in *both* — a section-wide
    # check stays green when either site loses them.
    verify = section(skill, "verify")
    gate = block(verify, "**In:**")          # what the seat may enter on
    for phrase in ("**newest section**", "**Verdict:** ✅ merge-ready",
                   "**Why the loop stopped:**", "verbatim"):
        assert phrase in gate, f"`verify` `In:` gate must carry {phrase!r}"
    # Keyed on the step's name, not its number: inserting a step ahead of it would
    # renumber `4.` and kill the test with a bare ValueError, so its red would have
    # meant "renumbered" as often as "the relay obligation is gone". `**Report:**`
    # occurs once in `verify`, so this red means exactly one thing.
    assert "**Report:**" in verify, "`## verify` must keep its report step"
    relay = verify[verify.index("**Report:**"):]      # what the seat must say
    for phrase in ("**Why the loop stopped:**", "verbatim"):
        assert phrase in relay, f"`verify` step 4 must carry {phrase!r}"


def test_project_config_template_lists_standing_gates() -> None:
    assert "Standing PR gates" in read("templates/project-config.md")
