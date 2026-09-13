"""M1 — read side: `kreview status` and the round packet.

Every test runs the real console script against the real GitHub API on merged PRs of
this repository. The numbers asserted were measured on 2026-09-13 with the shell in
kreview 0.4.0 §1 (spec: Discovered context); they are immutable history.
"""

from __future__ import annotations

from tests.acceptance.review_loop_runtime.conftest import (
    COPILOT,
    PR10,
    PR27,
    PR27_BOUNDARY,
    PR27_SIXTH_ORIGINAL,
    PR49,
    PR49_APPROVAL_REVIEW,
    PR49_BOUNDARY,
    PR49_COPILOT_REVIEWS,
    PR49_HEAD,
    PR49_ISSUE_COMMENTS,
    PR49_LAST_REVIEWED,
    PR49_SECOND_ORDER_REVIEW,
    PR49_SUPPRESSED_TOTAL,
    PR49_THREAD_FINDING,
    PR49_THREADS,
    REPO,
    ROOT,
    W27_FIRST,
    W27_SIXTH,
    W49_APPROVAL,
    W49_SECOND_ORDER,
    findings_by_id,
    git,
    kreview,
    window_args,
)

# ------------------------------------------------------------------- J1: status


def test_help_lists_status_and_round() -> None:
    r = kreview("--help")
    assert r.code == 0, r.err
    assert "status" in r.out
    assert "round" in r.out


def test_status_on_merged_pr_49() -> None:
    r = kreview("status", str(PR49), "--repo", REPO, "--json")
    assert r.code == 3, (r.out, r.err)
    s = r.json()
    assert s["verdict"] == "stop: merged"
    assert s["pr"]["state"] == "merged"
    assert s["pr"]["head_sha"].startswith(PR49_HEAD)
    assert s["scope"]["status"] == "present"
    assert "J7" in s["scope"]["text"]
    assert s["reviews"]["copilot_total"] == PR49_COPILOT_REVIEWS
    assert s["reviews"]["effort_levels"] == ["Lite"]
    assert s["reviews"]["effort_parse_failed"] is False
    assert s["boundary"]["status"] == "ok"
    assert s["boundary"]["sha"].startswith(PR49_BOUNDARY)
    assert s["ci"]["status"] == "passing"
    assert s["automation"]["claude_review"] is False
    assert s["babysit"]["report_present"] is True
    assert s["babysit"]["status"] == "none"  # the 0.4.0 report carries no state block


def test_status_reports_missing_scope_on_10() -> None:
    r = kreview("status", str(PR10), "--repo", REPO, "--json")
    assert r.code == 3
    s = r.json()
    assert s["scope"] == {"status": "missing", "text": ""}


def test_status_reentry_advice_on_49() -> None:
    s = kreview("status", str(PR49), "--repo", REPO, "--json").json()
    # Reviews and comments landed after the babysit report (05:10:54Z): a re-entry
    # here would be a paid round, not a kselfreview pass.
    assert s["reentry"] == "paid"
    assert s["reviews"]["last_reviewed_sha"].startswith(PR49_LAST_REVIEWED)
    assert len(s["reviews"]["unreviewed_commits"]) == 1
    assert s["reviews"]["unreviewed_commits"][0].startswith(PR49_HEAD)
    assert s["kselfreview_range"].startswith(PR49_LAST_REVIEWED)
    assert s["kselfreview_range"].endswith(s["pr"]["head_sha"])


# ------------------------------------------------------------- J2/J3: the packet


def test_round_full_history_49_parses_every_suppressed_finding() -> None:
    default = kreview("round", str(PR49), "--repo", REPO, "--json")
    assert default.code == 0, (default.out, default.err)
    p = default.json()
    assert p["suppressed_check"] == {
        "declared": PR49_SUPPRESSED_TOTAL,
        "parsed": PR49_SUPPRESSED_TOTAL,
    }
    assert p["boundary"]["sha"].startswith(PR49_BOUNDARY)
    assert p["boundary"]["status"] == "ok"
    sources = [f["source"] for f in p["findings"]]
    assert sources.count("suppressed") == PR49_SUPPRESSED_TOTAL
    assert sources.count("thread") == 0  # every thread on a merged PR is resolved

    with_resolved = kreview(
        "round", str(PR49), "--repo", REPO, "--json", "--include-resolved"
    ).json()
    assert [f["source"] for f in with_resolved["findings"]].count(
        "thread"
    ) == PR49_THREADS
    assert (
        with_resolved["signals"]["line_anchored"]
        == PR49_SUPPRESSED_TOTAL + PR49_THREADS
    )

    by_id = findings_by_id(with_resolved)
    first = by_id[f"s{PR49_SECOND_ORDER_REVIEW}-1"]
    second = by_id[f"s{PR49_SECOND_ORDER_REVIEW}-2"]
    assert (first["path"], first["line"]) == (
        "src/devops_ai/secrets/providers/azurekeyvault.py",
        245,
    )
    assert (second["path"], second["line"]) == (
        "src/devops_ai/secrets/providers/azurekeyvault.py",
        160,
    )
    assert first["anchor_commit"].startswith("70a8f10")
    assert first["blame_sha"].startswith("23ee88a2")
    assert second["blame_sha"].startswith("63465ed7")
    assert first["provenance"] == second["provenance"] == "review-fix"
    assert first["reviewer"] == COPILOT
    assert first["thread"] is None
    assert "caller-controlled stderr" in first["body"]
    assert first["url"].startswith("https://github.com/")


def test_round_window_second_order_on_49() -> None:
    r = kreview(
        "round", str(PR49), "--repo", REPO, "--json", *window_args(W49_SECOND_ORDER)
    )
    assert r.code == 0, (r.out, r.err)
    p = r.json()
    assert [rv["id"] for rv in p["reviews"]] == [PR49_SECOND_ORDER_REVIEW]
    review = p["reviews"][0]
    assert review["author"] == COPILOT
    assert review["effort"] == "Lite"
    assert review["commit"].startswith("70a8f10")
    assert "Two moderate diagnostics-matching issues" in review["summary"]
    assert "Suppressed comments" not in review["summary"]
    assert "Review effort level" not in review["summary"]
    assert "<details>" not in review["summary"]

    sig = p["signals"]
    assert sig["findings"] == sig["line_anchored"] == 2
    assert sig["suppressed"] == 2
    assert sig["on_review_fix"] == 2
    assert sig["on_original"] == sig["unknown"] == 0
    assert sig["second_order"] is True
    assert sig["no_new_findings"] is False
    assert sig["effort"] == ["Lite"]
    assert sig["copilot_total"] == PR49_COPILOT_REVIEWS


def test_round_window_approval_only_on_49() -> None:
    p = kreview(
        "round", str(PR49), "--repo", REPO, "--json", *window_args(W49_APPROVAL)
    ).json()
    assert [rv["id"] for rv in p["reviews"]] == [PR49_APPROVAL_REVIEW]
    assert "Approval recommended" in p["reviews"][0]["summary"]
    assert p["reviews"][0]["state"] == "COMMENTED"
    assert p["findings"] == []
    assert p["suppressed_check"] == {"declared": 0, "parsed": 0}
    sig = p["signals"]
    assert sig["no_new_findings"] is True
    assert sig["second_order"] is False
    assert sig["approved"] is False  # Copilot never submits an APPROVED review


def test_round_first_review_on_27_is_all_original() -> None:
    p = kreview(
        "round",
        str(PR27),
        "--repo",
        REPO,
        "--json",
        "--include-resolved",
        *window_args(W27_FIRST),
    ).json()
    assert p["boundary"]["sha"].startswith(PR27_BOUNDARY)
    assert len(p["reviews"]) == 1
    assert p["suppressed_check"] == {"declared": 8, "parsed": 8}
    sig = p["signals"]
    assert sig["line_anchored"] == 11
    assert sig["suppressed"] == 8
    assert sig["on_original"] == 11
    assert sig["on_review_fix"] == sig["unknown"] == 0
    assert sig["second_order"] is False


def test_round_sixth_review_on_27_is_not_second_order() -> None:
    """Counting suppressed comments moves the stop.

    kbabysit 0.4.0 says the second-order stop fires at the 6th of 14 reviews on #27.
    That was measured on threads alone. This review's one thread is on a fix commit,
    but of its four suppressed findings one blames to a commit older than the PR —
    so the round is not second-order, and the rule as signed does not fire here.
    """
    p = kreview(
        "round",
        str(PR27),
        "--repo",
        REPO,
        "--json",
        "--include-resolved",
        *window_args(W27_SIXTH),
    ).json()
    assert len(p["reviews"]) == 1
    sig = p["signals"]
    assert sig["line_anchored"] == 5
    assert sig["suppressed"] == 4
    assert sig["on_review_fix"] == 4
    assert sig["on_original"] == 1
    assert sig["unknown"] == 0
    assert sig["second_order"] is False
    original = [f for f in p["findings"] if f["provenance"] == "original"]
    assert [(f["path"], f["line"]) for f in original] == [PR27_SIXTH_ORIGINAL]
    assert original[0]["blame_sha"].startswith("ed2338dd")


def test_round_thread_finding_carries_anchor_and_replies() -> None:
    p = kreview(
        "round", str(PR49), "--repo", REPO, "--json", "--include-resolved"
    ).json()
    f = findings_by_id(p)[PR49_THREAD_FINDING]
    assert f["source"] == "thread"
    assert f["reviewer"] == COPILOT
    assert f["path"] == "src/devops_ai/secrets/providers/azurekeyvault.py"
    assert f["line"] == 162
    assert f["anchor_commit"].startswith("23ee88a")
    assert f["provenance"] == "review-fix"
    assert f["url"].startswith(f"https://github.com/{REPO}/pull/{PR49}")
    assert f["thread"]["resolved"] is True
    assert f["thread"]["outdated"] is True
    assert f["thread"]["replies"], "the author replied in this thread"
    assert f["thread"]["replies"][0]["author"] == "kpiteira"
    assert "b69053e" in f["thread"]["replies"][0]["body"]


def test_round_repeat_candidates_by_path_and_line() -> None:
    p = kreview(
        "round", str(PR49), "--repo", REPO, "--json", *window_args(W49_SECOND_ORDER)
    ).json()
    by_id = findings_by_id(p)
    # line 160 in this window; the earlier thread finding sat at line 162, same file
    assert (
        PR49_THREAD_FINDING
        in by_id[f"s{PR49_SECOND_ORDER_REVIEW}-2"]["repeat_candidates"]
    )
    # line 245 is far from every earlier finding on that file
    assert (
        PR49_THREAD_FINDING
        not in by_id[f"s{PR49_SECOND_ORDER_REVIEW}-1"]["repeat_candidates"]
    )


def test_round_comments_exclude_the_babysit_report() -> None:
    p = kreview("round", str(PR49), "--repo", REPO, "--json").json()
    assert len(p["comments"]) == PR49_ISSUE_COMMENTS - 1
    assert all(c["id"].startswith("c") and c["id"][1:].isdigit() for c in p["comments"])
    assert not any(c["body"].startswith("## Babysit report") for c in p["comments"])
    assert all({"author", "created_at", "body"} <= set(c) for c in p["comments"])


def test_round_text_form_carries_ids_bodies_and_signals() -> None:
    r = kreview("round", str(PR49), "--repo", REPO, *window_args(W49_SECOND_ORDER))
    assert r.code == 0, r.err
    assert f"s{PR49_SECOND_ORDER_REVIEW}-1" in r.out
    assert "src/devops_ai/secrets/providers/azurekeyvault.py:245" in r.out
    assert "This still searches caller-controlled stderr" in r.out
    assert "second_order: true" in r.out
    assert "review-fix" in r.out


def test_round_fails_closed_on_api_error() -> None:
    r = kreview("round", "1", "--repo", "kpiteira/kreview-no-such-repo-xyz", "--json")
    assert r.code == 1
    assert r.out == ""
    assert r.err.strip()


def test_round_leaves_the_clone_untouched() -> None:
    before = (
        git("rev-parse", "HEAD", cwd=ROOT),
        git("branch", "--list", cwd=ROOT),
        git("status", "--porcelain", cwd=ROOT),
    )
    assert kreview("round", str(PR49), "--repo", REPO, "--json").code == 0
    after = (
        git("rev-parse", "HEAD", cwd=ROOT),
        git("branch", "--list", cwd=ROOT),
        git("status", "--porcelain", cwd=ROOT),
    )
    assert before == after


# ------------------------------------------------------------------- J4: skills


def _skill(name: str) -> str:
    return (ROOT / "skills" / name / "SKILL.md").read_text()


def test_skills_delegate_fetch_and_preflight_to_the_tool() -> None:
    kreview_skill = _skill("kreview")
    assert "kreview round" in kreview_skill
    assert "git blame" not in kreview_skill
    assert "reviewThreads(" not in kreview_skill
    assert "awk" not in kreview_skill

    kbabysit = _skill("kbabysit")
    assert "kreview status" in kbabysit
    # the judgement and the pin are untouched
    assert "context: fork" in kbabysit
    assert "Stopping is a state, not a mood" in kbabysit


def test_readme_names_the_new_script() -> None:
    """The README's reinstall paragraph names kreview beside ksecret.

    The README already names the /kreview skill elsewhere, so the assertion is scoped
    to the paragraph that states the one-time `uv tool install -e . --reinstall`.
    """
    lines = (ROOT / "README.md").read_text().splitlines()
    reinstall = next(i for i, line in enumerate(lines) if "--reinstall" in line)
    paragraph = "\n".join(lines[max(0, reinstall - 8) : reinstall + 1])
    assert "kreview" in paragraph
    assert "ksecret" in paragraph
