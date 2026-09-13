"""M2 — the loop: request, wait, apply, state, report, re-entry.

Write-side tests open their own PR in the scratch repository (KREVIEW_ACCEPTANCE_REPO,
spec A2) and post review comments as the authenticated user — a human reviewer, free.
Replay tests run `apply --dry-run` on #49's immutable history. Exactly one test buys a
Copilot review and is gated by KREVIEW_ACCEPTANCE_PAID=1 (A3).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from tests.acceptance.review_loop_runtime.conftest import (
    COPILOT,
    PR49,
    PR49_FIX_AFTER_SECOND_ORDER,
    PR49_ISSUE_COMMENTS,
    PR49_SECOND_ORDER_REVIEW,
    REPO,
    ROOT,
    W49_SECOND_ORDER,
    ScratchPR,
    dispositions_file,
    gh_json,
    kreview,
    window_args,
)


def _kr(pr: ScratchPR, *args: str, timeout: int = 600):
    return kreview(*args, "--repo", pr.repo, cwd=pr.clone, timeout=timeout)


def _round(pr: ScratchPR, *extra: str) -> dict:
    r = _kr(pr, "round", str(pr.number), "--json", *extra)
    assert r.code == 0, (r.out, r.err)
    return r.json()


def _later(seconds: float, fn, *args) -> threading.Thread:
    t = threading.Thread(target=lambda: (time.sleep(seconds), fn(*args)))
    t.start()
    return t


# --------------------------------------------------------------- J5: wait/request


def test_help_lists_apply_and_report() -> None:
    r = kreview("--help")
    assert r.code == 0, r.err
    for cmd in ("status", "round", "apply", "report"):
        assert cmd in r.out


def test_round_wait_returns_when_a_review_arrives(scratch: ScratchPR) -> None:
    poster = _later(8, scratch.comment, 3, "line 3 should say three")
    started = time.monotonic()
    p = _round(scratch, "--wait", "120")
    elapsed = time.monotonic() - started
    poster.join()
    assert p["no_show"] is False
    assert elapsed < 120
    assert p["elapsed_s"] < 120
    assert len(p["findings"]) == 1
    f = p["findings"][0]
    assert f["source"] == "thread"
    assert (f["path"], f["line"]) == (scratch.path, 3)
    assert f["body"] == "line 3 should say three"
    assert p["signals"]["budget"] == {"max_rounds": 3, "used_this_run": 0}


def test_round_wait_reports_no_show(scratch: ScratchPR) -> None:
    p = _round(scratch, "--wait", "5")
    assert p["no_show"] is True
    assert p["findings"] == []
    assert p["requested"] == "not-requested"


@pytest.mark.skipif(
    os.environ.get("KREVIEW_ACCEPTANCE_PAID") != "1",
    reason="buys one Copilot review; set KREVIEW_ACCEPTANCE_PAID=1 (spec A3)",
)
def test_round_request_buys_a_copilot_review(scratch: ScratchPR) -> None:
    p = _round(scratch, "--request", "--wait", "300")
    assert p["requested"] == "requested"
    assert p["no_show"] is False
    assert any(rv["author"] == COPILOT for rv in p["reviews"])
    assert p["signals"]["copilot_total"] == 1


# ----------------------------------------------------------------- J6: apply


def test_apply_replies_resolves_files_an_issue_and_records_state(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    c_fix = scratch.comment(3, "line 3 should say three")
    c_oos = scratch.comment(19, "the repository should also have a LICENSE file")
    p = _round(scratch)
    assert {f["id"] for f in p["findings"]} == {f"t{c_fix}", f"t{c_oos}"}
    sha = scratch.push_fix("three")

    r = _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{c_fix}",
                    "verdict": "IMPLEMENT",
                    "shape": "isolated",
                    "commit": sha,
                    "reply": "line 3 now says three",
                },
                {
                    "id": f"t{c_oos}",
                    "verdict": "OUT_OF_SCOPE",
                    "shape": "isolated",
                    "scope_outcome": "the twenty-line file",
                    "issue_title": f"kreview-acceptance {scratch.tag}: LICENSE file",
                },
            )
        ),
    )
    assert r.code == 0, (r.out, r.err)
    out = r.json()
    assert out["round"] == 1 and out["run"] == 1
    assert out["decision"] == "continue"
    assert out["posted"]["replies"] == 2
    assert out["posted"]["resolved"] == 2
    assert len(out["posted"]["issues"]) == 1
    assert out["next"] is None

    fix_thread = scratch.thread_of(c_fix)
    assert fix_thread["resolved"] is True
    assert fix_thread["comments"][-1]["body"].startswith(f"Fixed in `{sha[:7]}")
    assert "line 3 now says three" in fix_thread["comments"][-1]["body"]

    issue = scratch.find_issues()[0]
    assert issue["number"] == out["posted"]["issues"][0]
    assert "the repository should also have a LICENSE file" in issue["body"]
    assert scratch.thread_of(c_oos)["comments"][0]["url"] in issue["body"]
    assert "serves none of the twenty-line file" in issue["body"]
    oos_thread = scratch.thread_of(c_oos)
    assert oos_thread["resolved"] is True
    assert f"#{issue['number']}" in oos_thread["comments"][-1]["body"]
    assert "outside this PR's scope" in oos_thread["comments"][-1]["body"]

    comment = scratch.babysit_comment()
    assert comment is not None
    assert comment.startswith(f"## Babysit report — PR #{scratch.number}")
    assert "in progress" in comment
    assert "<!-- kreview-state" in comment

    s = _kr(scratch, "status", str(scratch.number), "--json").json()
    assert s["babysit"]["status"] == "running"
    assert s["babysit"]["rounds"] == 1
    assert s["babysit"]["run"] == 1


def test_apply_refuses_incomplete_dispositions(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    c1 = scratch.comment(3, "first")
    scratch.comment(4, "second")
    r = _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{c1}",
                    "verdict": "PUSH_BACK",
                    "shape": "isolated",
                    "reply": "no",
                },
            )
        ),
    )
    assert r.code == 2, (r.out, r.err)
    assert r.err.strip()
    assert all(len(t["comments"]) == 1 for t in scratch.threads())
    assert scratch.babysit_comment() is None


def test_apply_refuses_a_commit_not_on_the_pr(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    c1 = scratch.comment(3, "first")
    foreign = "0000000000000000000000000000000000000000"
    r = _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{c1}",
                    "verdict": "IMPLEMENT",
                    "shape": "isolated",
                    "commit": foreign,
                    "reply": "fixed",
                },
            )
        ),
    )
    assert r.code == 2
    assert foreign[:7] in r.err
    assert len(scratch.thread_of(c1)["comments"]) == 1


def test_apply_fails_closed_when_github_is_unreachable(tmp_path: Path) -> None:
    r = kreview(
        "apply",
        "1",
        "--repo",
        "kpiteira/kreview-no-such-repo-xyz",
        "--json",
        "--dispositions",
        str(dispositions_file(tmp_path)),
    )
    assert r.code == 1
    assert r.out == ""


# --------------------------------------------------------------- J7: decisions


def test_apply_discuss_stops_and_leaves_the_thread_open(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    c1 = scratch.comment(3, "should the file be YAML instead?")
    r = _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{c1}",
                    "verdict": "DISCUSS",
                    "shape": "isolated",
                    "reply": "Trade-off: YAML is structured, text is what is pinned.",
                },
            )
        ),
    )
    assert r.code == 0, (r.out, r.err)
    out = r.json()
    assert (out["decision"], out["stop_kind"], out["stop_reason"]) == (
        "stop",
        "escalate",
        "discuss",
    )
    t = scratch.thread_of(c1)
    assert t["resolved"] is False
    assert t["comments"][-1]["body"].startswith("Trade-off:")


def test_apply_dry_run_second_order_on_49_history(tmp_path: Path) -> None:
    before = len(gh_json("api", "--paginate", f"repos/{REPO}/issues/{PR49}/comments"))
    assert before == PR49_ISSUE_COMMENTS
    r = kreview(
        "apply",
        str(PR49),
        "--repo",
        REPO,
        "--json",
        "--dry-run",
        *window_args(W49_SECOND_ORDER),
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"s{PR49_SECOND_ORDER_REVIEW}-1",
                    "verdict": "IMPLEMENT",
                    "shape": "isolated",
                    "commit": PR49_FIX_AFTER_SECOND_ORDER,
                    "reply": "anchored",
                },
                {
                    "id": f"s{PR49_SECOND_ORDER_REVIEW}-2",
                    "verdict": "IMPLEMENT",
                    "shape": "isolated",
                    "commit": PR49_FIX_AFTER_SECOND_ORDER,
                    "reply": "anchored",
                },
            )
        ),
    )
    assert r.code == 0, (r.out, r.err)
    out = r.json()
    assert (out["decision"], out["stop_kind"], out["stop_reason"]) == (
        "stop",
        "converged",
        "second-order",
    )
    assert out["posted"] == {"replies": 0, "resolved": 0, "issues": []}
    assert out["next"] is None
    after = len(gh_json("api", "--paginate", f"repos/{REPO}/issues/{PR49}/comments"))
    assert after == before


def test_apply_dry_run_precedence_on_49_history(tmp_path: Path) -> None:
    ids = [f"s{PR49_SECOND_ORDER_REVIEW}-1", f"s{PR49_SECOND_ORDER_REVIEW}-2"]
    push_backs = kreview(
        "apply",
        str(PR49),
        "--repo",
        REPO,
        "--json",
        "--dry-run",
        *window_args(W49_SECOND_ORDER),
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                *(
                    {
                        "id": i,
                        "verdict": "PUSH_BACK",
                        "shape": "isolated",
                        "reply": "no",
                    }
                    for i in ids
                ),
            )
        ),
    ).json()
    # no IMPLEMENT and second-order both hold; second-order is checked first
    assert push_backs["stop_reason"] == "second-order"

    pinned = kreview(
        "apply",
        str(PR49),
        "--repo",
        REPO,
        "--json",
        "--dry-run",
        *window_args(W49_SECOND_ORDER),
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": ids[0],
                    "verdict": "DISCUSS",
                    "shape": "systemic",
                    "root_cause": "unvalidated akv segments reach the error text",
                    "on_pinned_surface": True,
                    "reply": "the class sits on pinned Surface",
                },
                {
                    "id": ids[1],
                    "verdict": "IMPLEMENT",
                    "shape": "isolated",
                    "commit": PR49_FIX_AFTER_SECOND_ORDER,
                    "reply": "anchored",
                },
            )
        ),
    ).json()
    assert (pinned["stop_kind"], pinned["stop_reason"]) == (
        "escalate",
        "systemic-on-pinned-surface",
    )

    quiet = kreview(
        "apply",
        str(PR49),
        "--repo",
        REPO,
        "--json",
        "--dry-run",
        "--since",
        "2026-09-13T06:00:00Z",
        "--until",
        "2026-09-13T13:00:00Z",
        "--dispositions",
        str(dispositions_file(tmp_path)),
    )
    # nothing happened on #49 in that window: an empty file is the whole round
    assert quiet.code == 0, (quiet.out, quiet.err)
    assert quiet.json()["stop_reason"] == "no-new-findings"


def test_apply_budget_stops_after_max_rounds(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    c1 = scratch.comment(3, "line 3 should say three")
    sha = scratch.push_fix("three")
    out = _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--max-rounds",
        "1",
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{c1}",
                    "verdict": "IMPLEMENT",
                    "shape": "isolated",
                    "commit": sha,
                    "reply": "done",
                },
            )
        ),
    ).json()
    assert (out["decision"], out["stop_kind"], out["stop_reason"]) == (
        "stop",
        "escalate",
        "budget",
    )


def test_apply_next_chains_into_the_next_packet(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    c1 = scratch.comment(3, "line 3 should say three")
    sha = scratch.push_fix("three")
    poster = _later(10, scratch.comment, 5, "and line 5 should say five")
    r = _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--next",
        "--reviewer",
        "none",
        "--wait",
        "120",
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{c1}",
                    "verdict": "IMPLEMENT",
                    "shape": "isolated",
                    "commit": sha,
                    "reply": "done",
                },
            )
        ),
    )
    poster.join()
    assert r.code == 0, (r.out, r.err)
    out = r.json()
    assert out["decision"] == "continue"
    nxt = out["next"]
    assert nxt is not None
    assert nxt["no_show"] is False
    assert [f["body"] for f in nxt["findings"]] == ["and line 5 should say five"]
    assert nxt["signals"]["budget"] == {"max_rounds": 3, "used_this_run": 1}
    assert f"t{c1}" in nxt["ledger"]
    assert nxt["ledger"][f"t{c1}"]["verdict"] == "IMPLEMENT"
    s = _kr(scratch, "status", str(scratch.number), "--json").json()
    assert s["babysit"]["rounds"] == 1  # round 2 is open, not yet applied
    assert s["babysit"]["status"] == "running"


# ------------------------------------------------------------ J9/J8: report, re-entry


def test_report_renders_and_posts_from_state(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    c1 = scratch.comment(3, "line 3 should say three")
    _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{c1}",
                    "verdict": "PUSH_BACK",
                    "shape": "isolated",
                    "reply": "three is not the scope's concern",
                },
            )
        ),
    )
    r = _kr(
        scratch,
        "report",
        str(scratch.number),
        "--json",
        "--post",
        "--tldr",
        "One round, one push-back, nothing implemented.",
        "--kselfreview",
        "na",
    )
    assert r.code == 0, (r.out, r.err)
    comment = scratch.babysit_comment()
    assert comment is not None
    assert "**TL;DR:** One round, one push-back, nothing implemented." in comment
    assert "**Verdict:** ✅ merge-ready" in comment
    assert "### Rounds" in comment
    assert "| 1 |" in comment
    assert "nothing — pre-PR gates held" in comment
    assert (
        "three is not the scope's concern" not in comment
    )  # reasoning lives in-thread
    assert "**Why the loop stopped:** no-in-scope-implement" in comment
    assert "**Push-backs:** 1 of 1 findings" in comment
    assert "**Paid rounds:** 0 this run · 0 total" in comment
    s = _kr(scratch, "status", str(scratch.number), "--json").json()
    assert s["babysit"]["status"] == "stopped"
    assert s["reentry"] == "none"  # nothing newer than the report


def test_reentry_is_advised_and_gated(scratch: ScratchPR, tmp_path: Path) -> None:
    c1 = scratch.comment(3, "line 3 should say three")
    _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{c1}",
                    "verdict": "PUSH_BACK",
                    "shape": "isolated",
                    "reply": "no",
                },
            )
        ),
    )
    _kr(
        scratch,
        "report",
        str(scratch.number),
        "--json",
        "--post",
        "--tldr",
        "t",
        "--kselfreview",
        "na",
    )
    scratch.push_fix("an unreviewed fix")

    s = _kr(scratch, "status", str(scratch.number), "--json").json()
    assert s["babysit"]["status"] == "stopped"
    assert s["reentry"] == "selfreview"

    c2 = scratch.comment(4, "line 4 too")
    blocked = _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{c2}",
                    "verdict": "PUSH_BACK",
                    "shape": "isolated",
                    "reply": "no",
                },
            )
        ),
    )
    assert blocked.code == 5
    assert "--reenter" in blocked.err
    assert len(scratch.thread_of(c2)["comments"]) == 1

    s = _kr(scratch, "status", str(scratch.number), "--json").json()
    assert s["reentry"] == "paid"  # a new thread since the report

    reentered = _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--reenter",
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{c2}",
                    "verdict": "PUSH_BACK",
                    "shape": "isolated",
                    "reply": "no",
                },
            )
        ),
    )
    assert reentered.code == 0, (reentered.out, reentered.err)
    assert reentered.json()["run"] == 2
    assert reentered.json()["round"] == 2
    s = _kr(scratch, "status", str(scratch.number), "--json").json()
    assert s["babysit"]["run"] == 2
    assert s["babysit"]["rounds"] == 2


# ------------------------------------------------------------------ J10: skills


def test_skills_contain_no_gh_or_git_commands() -> None:
    for name in ("kbabysit", "kreview"):
        text = (ROOT / "skills" / name / "SKILL.md").read_text()
        for cmd in (
            "gh api",
            "gh pr",
            "gh issue",
            "git blame",
            "git log",
            "git fetch",
            "awk ",
            "jq ",
            "curl ",
        ):
            assert cmd not in text, f"{name}: {cmd!r} is the tool's job now"
    kbabysit = (ROOT / "skills" / "kbabysit" / "SKILL.md").read_text()
    for sub in ("kreview status", "kreview round", "kreview apply", "kreview report"):
        assert sub in kbabysit
    assert "kselfreview" in kbabysit
    assert "context: fork" in kbabysit
    assert "Never merge" in kbabysit
