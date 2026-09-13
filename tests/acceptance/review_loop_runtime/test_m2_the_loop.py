"""M2 — the loop: request, wait, apply, state, report, re-entry.

Write-side tests open their own PR in the scratch repository (KREVIEW_ACCEPTANCE_REPO,
spec A2) and post review comments as the authenticated user — a human reviewer, free.
They skip when that variable is unset, and `test_write_side_coverage_is_not_optional`
fails rather than skipping so this blocking command cannot go green on skips.

Replay tests run `apply --dry-run` on #49 inside an explicit window, so a later comment
on that merged PR cannot move what they read. Exactly one test buys a Copilot review and
is gated by KREVIEW_ACCEPTANCE_PAID=1 (A3).
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tests.acceptance.review_loop_runtime.conftest import (
    COPILOT,
    PR49,
    PR49_FIX_AFTER_SECOND_ORDER,
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


def _apply(pr: ScratchPR, *args: str, expect: int = 0):
    r = _kr(pr, "apply", str(pr.number), "--json", *args)
    assert r.code == expect, (r.code, r.out, r.err)
    return r


class _Later:
    """Runs `fn` after `seconds` in a thread; `join()` re-raises what it raised.

    A bare thread would swallow an API failure, and the test would then fail at its
    own deadline on missing data instead of naming the real cause.
    """

    def __init__(self, seconds: float, fn: Any, *args: Any) -> None:
        self._box: dict[str, Any] = {}
        self._thread = threading.Thread(target=self._run, args=(seconds, fn, args))
        self._thread.start()

    def _run(self, seconds: float, fn: Any, args: tuple[Any, ...]) -> None:
        try:
            time.sleep(seconds)
            self._box["value"] = fn(*args)
        except Exception as exc:  # re-raised in join(), on the test's thread
            self._box["error"] = exc

    def join(self) -> Any:
        self._thread.join()
        if "error" in self._box:
            raise self._box["error"]
        return self._box.get("value")


def _later(seconds: float, fn: Any, *args: Any) -> _Later:
    return _Later(seconds, fn, *args)


# --------------------------------------------------------------- J5: wait/request


def test_help_lists_apply_and_report() -> None:
    r = kreview("--help")
    assert r.code == 0, r.err
    for cmd in ("status", "round", "apply", "report"):
        assert cmd in r.out


def test_write_side_coverage_is_not_optional() -> None:
    """The M2 gate is red when the write side was not exercised (spec A2).

    Every scratch-repository test below skips when KREVIEW_ACCEPTANCE_REPO is unset, so
    without this guard the milestone's `blocking:` command exits 0 with J5–J9 entirely
    unexercised. "M2 is not delivered on skips" has to be something the command
    enforces, not something a human notices in the skip count.
    """
    # Read into a local first: asserting on `os.environ.get(...)` makes pytest's
    # assertion rewriting print the entire environment on failure, which is how a
    # token ends up in a CI log.
    configured = os.environ.get("KREVIEW_ACCEPTANCE_REPO")
    assert configured, (
        "KREVIEW_ACCEPTANCE_REPO is unset: the write-side tests would all skip and "
        "this blocking command would go green with J5-J9 unexercised (spec A2). Point "
        "it at the scratch repository before running the M2 gate."
    )


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
    # the contract is "returns ... else at the deadline": an implementation that gives
    # up immediately also reports no_show, and only elapsed_s tells the two apart
    assert p["elapsed_s"] >= 4.5


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


def test_apply_files_one_issue_per_class(scratch: ScratchPR, tmp_path: Path) -> None:
    """Two OUT_OF_SCOPE findings sharing a root cause file one issue, not two."""
    c1 = scratch.comment(5, "line 5 has no trailing metadata")
    c2 = scratch.comment(12, "line 12 has no trailing metadata either")
    p = _round(scratch)
    assert {f["id"] for f in p["findings"]} == {f"t{c1}", f"t{c2}"}

    title = f"kreview-acceptance {scratch.tag}: per-line metadata"
    out = _apply(
        scratch,
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                *(
                    {
                        "id": f"t{c}",
                        "verdict": "OUT_OF_SCOPE",
                        "shape": "systemic",
                        "root_cause": "the file carries no per-line metadata",
                        "scope_outcome": "the twenty-line file",
                        "issue_title": title,
                    }
                    for c in (c1, c2)
                ),
            )
        ),
    ).json()
    assert len(out["posted"]["issues"]) == 1
    assert out["posted"]["replies"] == 2
    assert out["posted"]["resolved"] == 2

    issues = scratch.find_issues()
    assert len(issues) == 1, [i["title"] for i in issues]
    body = issues[0]["body"]
    assert "line 5 has no trailing metadata" in body
    assert "line 12 has no trailing metadata either" in body
    assert all(scratch.thread_of(c)["resolved"] is True for c in (c1, c2))


def test_apply_records_an_issue_comment_disposition(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    """An issue comment is dispositionable, gets no reply, and is not line-anchored."""
    cid = scratch.issue_comment("the README should mention this file")
    p = _round(scratch)
    assert p["findings"] == []
    assert [c["id"] for c in p["comments"]] == [f"c{cid}"]
    before = len(scratch.issue_comments())

    out = _apply(
        scratch,
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"c{cid}",
                    "verdict": "PUSH_BACK",
                    "shape": "isolated",
                    "reply": "the README is not this PR's file",
                },
            )
        ),
    ).json()
    assert out["posted"]["replies"] == 0
    assert out["posted"]["resolved"] == 0
    assert scratch.threads() == []
    # the babysit report is the only comment apply is allowed to add
    assert len(scratch.issue_comments()) == before + 1
    recorded = {
        d["id"]: d["verdict"] for d in scratch.state()["rounds"][0]["dispositions"]
    }
    assert recorded == {f"c{cid}": "PUSH_BACK"}
    assert (out["decision"], out["stop_reason"]) == ("stop", "no-new-findings")


def test_apply_is_idempotent_on_a_rerun(scratch: ScratchPR, tmp_path: Path) -> None:
    """Re-applying the same round posts nothing new (the partial-failure retry path)."""
    c1 = scratch.comment(3, "line 3 should say three")
    c2 = scratch.comment(19, "the repository should also have a LICENSE file")
    p = _round(scratch)
    since, until = p["window"]["since"], p["window"]["until"]
    sha = scratch.push_fix("three")
    dispositions = str(
        dispositions_file(
            tmp_path,
            {
                "id": f"t{c1}",
                "verdict": "IMPLEMENT",
                "shape": "isolated",
                "commit": sha,
                "reply": "line 3 now says three",
            },
            {
                "id": f"t{c2}",
                "verdict": "OUT_OF_SCOPE",
                "shape": "isolated",
                "scope_outcome": "the twenty-line file",
                "issue_title": f"kreview-acceptance {scratch.tag}: LICENSE file",
            },
        )
    )
    window = ("--since", since, "--until", until, "--dispositions", dispositions)

    first = _apply(scratch, *window).json()
    assert (first["posted"]["replies"], first["posted"]["resolved"]) == (2, 2)
    assert len(first["posted"]["issues"]) == 1
    counts = {c: len(scratch.thread_of(c)["comments"]) for c in (c1, c2)}

    second = _apply(scratch, *window).json()
    assert second["posted"] == {"replies": 0, "resolved": 0, "issues": []}
    assert {c: len(scratch.thread_of(c)["comments"]) for c in (c1, c2)} == counts
    assert len(scratch.find_issues()) == 1


def test_apply_dry_run_posts_nothing_on_a_live_thread(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    """`--dry-run` writes nothing — graded where there is something to write to."""
    c1 = scratch.comment(3, "line 3 should say three")
    sha = scratch.push_fix("three")
    out = _apply(
        scratch,
        "--dry-run",
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{c1}",
                    "verdict": "IMPLEMENT",
                    "shape": "isolated",
                    "commit": sha,
                    "reply": "line 3 now says three",
                },
            )
        ),
    ).json()
    assert out["posted"] == {"replies": 0, "resolved": 0, "issues": []}
    assert out["next"] is None
    thread = scratch.thread_of(c1)
    assert thread["resolved"] is False
    assert len(thread["comments"]) == 1
    assert scratch.babysit_comment() is None


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
    # only the before/after equality grades the dry run; pinning the absolute count here
    # would make a stranger's comment on merged #49 fail a correct implementation
    before = len(gh_json("api", "--paginate", f"repos/{REPO}/issues/{PR49}/comments"))
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


def test_apply_stop_reason_from_the_model(tmp_path: Path) -> None:
    """`--stop REASON` is an escalation and outranks the convergence rules (D12).

    The same window with the same two IMPLEMENT dispositions stops as `second-order`
    without the flag (the test above), so this pins the precedence, not just the flag.
    """
    ids = [f"s{PR49_SECOND_ORDER_REVIEW}-1", f"s{PR49_SECOND_ORDER_REVIEW}-2"]
    r = kreview(
        "apply",
        str(PR49),
        "--repo",
        REPO,
        "--json",
        "--dry-run",
        *window_args(W49_SECOND_ORDER),
        "--stop",
        "ci",
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                *(
                    {
                        "id": i,
                        "verdict": "IMPLEMENT",
                        "shape": "isolated",
                        "commit": PR49_FIX_AFTER_SECOND_ORDER,
                        "reply": "anchored",
                    }
                    for i in ids
                ),
            )
        ),
    )
    assert r.code == 0, (r.out, r.err)
    out = r.json()
    assert (out["decision"], out["stop_kind"], out["stop_reason"]) == (
        "stop",
        "escalate",
        "stopped: ci",
    )


def test_apply_repeats_only_stops_the_loop(scratch: ScratchPR, tmp_path: Path) -> None:
    """A round whose every disposition re-raises a prior finding ends the loop."""
    c1 = scratch.comment(3, "line 3 should say three")
    first = _round(scratch)
    _apply(
        scratch,
        "--since",
        first["window"]["since"],
        "--until",
        first["window"]["until"],
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

    c2 = scratch.comment(4, "line 4 should say four, same as line 3")
    second = _round(scratch)
    assert {f["id"] for f in second["findings"]} == {f"t{c2}"}
    assert second["ledger"][f"t{c1}"]["verdict"] == "PUSH_BACK"

    out = _apply(
        scratch,
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{c2}",
                    "verdict": "PUSH_BACK",
                    "shape": "isolated",
                    "repeat_of": f"t{c1}",
                    "reply": "same point as before",
                },
            )
        ),
    ).json()
    assert (out["decision"], out["stop_kind"], out["stop_reason"]) == (
        "stop",
        "converged",
        "repeats-only",
    )


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
    # Round 1's window is pinned by the server-resolved `until` before the second
    # comment is scheduled, so that comment can never land inside round 1 and
    # invalidate the one-entry dispositions file, however slow GitHub or uv happen
    # to be.
    until = _round(scratch)["window"]["until"]
    poster = _later(10, scratch.comment, 5, "and line 5 should say five")
    r = _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--until",
        until,
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


FORBIDDEN_COMMANDS = ("gh", "git", "awk", "jq", "curl")


def _shell_invocations(text: str) -> list[str]:
    """Every fenced line or inline code span that *starts* with a forbidden command.

    The Surface pins "no `gh `, `git `, `awk`, `jq`, or `curl` invocation", so the check
    is generic: a list of spellings would pass a rewrite that reached for `gh repo view`
    or `git status`. Prose about git is not an invocation, so only code is scanned.
    """
    candidates: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            candidates.append(line)
        candidates.extend(re.findall(r"`([^`\n]+)`", line))
    return [
        snippet.strip()
        for snippet in candidates
        if snippet.strip().removeprefix("$").strip().split(" ")[0] in FORBIDDEN_COMMANDS
    ]


def test_skills_contain_no_gh_or_git_commands() -> None:
    for name in ("kbabysit", "kreview"):
        text = (ROOT / "skills" / name / "SKILL.md").read_text()
        found = _shell_invocations(text)
        assert found == [], f"{name}: these are the tool's job now: {found[:5]}"
    kbabysit = (ROOT / "skills" / "kbabysit" / "SKILL.md").read_text()
    for sub in ("kreview status", "kreview round", "kreview apply", "kreview report"):
        assert sub in kbabysit
    assert "kselfreview" in kbabysit
    assert "context: fork" in kbabysit
    assert "Never merge" in kbabysit
