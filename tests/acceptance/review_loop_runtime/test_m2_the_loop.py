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
    authenticated_login,
    dispositions_file,
    findings_by_id,
    gh,
    gh_json,
    git,
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
    """A comment posted well after the call starts is still in the packet.

    The delay is 30 s, not a few: the comment must not exist when `round` begins, or an
    implementation that ignores `--wait` reads it immediately and passes. Process
    startup cannot plausibly eat 30 s, and `elapsed_s >= 10` — the tool's own view —
    fails such an implementation even if it did.
    """
    poster = _later(30, scratch.comment, 3, "line 3 should say three")
    started = time.monotonic()
    p = _round(scratch, "--wait", "120")
    elapsed = time.monotonic() - started
    poster.join()
    assert p["no_show"] is False
    assert elapsed < 120
    assert 10 <= p["elapsed_s"] < 120
    assert len(p["findings"]) == 1
    f = p["findings"][0]
    assert f["source"] == "thread"
    assert (f["path"], f["line"]) == (scratch.path, 3)
    assert f["body"] == "line 3 should say three"
    assert p["signals"]["budget"] == {"max_rounds": None, "used_this_run": 0}


def test_round_wait_reports_no_show(scratch: ScratchPR) -> None:
    p = _round(scratch, "--wait", "5")
    assert p["no_show"] is True
    assert p["findings"] == []
    assert p["requested"] == "not-requested"
    # the contract is "returns ... else at the deadline": an implementation that gives
    # up immediately also reports no_show, and only elapsed_s tells the two apart
    assert p["elapsed_s"] >= 4.5


def test_round_request_reports_already_reviewed(scratch: ScratchPR) -> None:
    """`--request` does not re-request a reviewer who already reviewed this head.

    The authenticated user stands in for the reviewer: a review comment makes a
    submitted review by that login on `head_sha`, which is the Surface's condition —
    graded here without buying a Copilot review, so `already-reviewed` is not one of
    the outcomes that ships only behind `KREVIEW_ACCEPTANCE_PAID`.
    """
    me = authenticated_login()
    scratch.comment(3, "line 3 should say three")
    p = _round(scratch, "--request", "--reviewer", me)
    assert p["requested"] == "already-reviewed"
    assert (
        gh_json(
            "api", f"repos/{scratch.repo}/pulls/{scratch.number}/requested_reviewers"
        )["users"]
        == []
    )


@pytest.mark.skipif(
    os.environ.get("KREVIEW_ACCEPTANCE_PAID") != "1",
    reason="buys one Copilot review; set KREVIEW_ACCEPTANCE_PAID=1 (spec A3)",
)
def test_round_request_buys_a_copilot_review(scratch: ScratchPR) -> None:
    """One purchase grades all four `requested` outcomes, in the order they occur."""
    p = _round(scratch, "--request")
    assert p["requested"] == "requested"

    # the request is outstanding and Copilot takes minutes, so this call must not
    # request a second time
    pending = _round(scratch, "--request")
    assert pending["requested"] == "pending"

    p = _round(scratch, "--wait", "300")
    assert p["no_show"] is False
    assert any(rv["author"] == COPILOT for rv in p["reviews"])
    assert p["signals"]["copilot_total"] == 1

    after = _round(scratch, "--request")
    assert after["requested"] == "already-reviewed"


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
    """Two OUT_OF_SCOPE findings sharing a root cause file one issue, not two.

    The two titles differ deliberately: with one title shared, an implementation that
    grouped by `issue_title` instead of by the `root_cause` the Surface names would
    pass this test while filing two issues for any real class.
    """
    c1 = scratch.comment(5, "line 5 has no trailing metadata")
    c2 = scratch.comment(12, "line 12 has no trailing metadata either")
    p = _round(scratch)
    assert {f["id"] for f in p["findings"]} == {f"t{c1}", f"t{c2}"}

    titles = {
        c1: f"kreview-acceptance {scratch.tag}: per-line metadata at line 5",
        c2: f"kreview-acceptance {scratch.tag}: per-line metadata at line 12",
    }
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
                        "issue_title": titles[c],
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
    # Which title the one issue carries is pinned, not a disjunction: the first
    # finding of the class in round order wins. `in titles.values()` accepted either,
    # so the selection rule was observable in neither the Surface nor the grader, and
    # two conforming implementations could disagree about the issue's name.
    #
    # Read off the packet's own order rather than hardcoding c1: c1 is also the lowest
    # line and first in the dispositions file, so `== titles[c1]` would pass equally
    # for an implementation ordering by line or by disposition — the same "the test
    # cannot tell which rule is implemented" defect this assertion replaced.
    first_in_round = next(f["id"] for f in p["findings"])
    assert issues[0]["title"] == titles[c1 if first_in_round == f"t{c1}" else c2]
    body = issues[0]["body"]
    assert "line 5 has no trailing metadata" in body
    assert "line 12 has no trailing metadata either" in body
    assert all(scratch.thread_of(c)["resolved"] is True for c in (c1, c2))


SUPPRESSED_REVIEW_BODY = """\
Two moderate issues.

### Suppressed comments (1)

**{path}:4**
* line 4 should say four
"""


def test_apply_records_a_suppressed_finding_without_replying(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    """A suppressed finding gets no reply anywhere, and its disposition is recorded.

    The Surface pins both halves, and until now only the issue-comment half was graded
    live: the suppressed half existed only in `--dry-run` replays of #49, which post
    nothing by construction, so a tool that replied to a suppressed finding or dropped
    it from the state block passed. The review body is the author's own (free); the
    parser keys on the section heading, not on who wrote it.
    """
    review_id = scratch.review(SUPPRESSED_REVIEW_BODY.format(path=scratch.path))
    p = _round(scratch)
    assert p["suppressed_check"] == {"declared": 1, "parsed": 1}
    assert p["signals"]["suppressed"] == 1
    assert len(p["findings"]) == 1
    f = p["findings"][0]
    assert f["id"] == f"s{review_id}-1"
    assert f["source"] == "suppressed"
    assert f["thread"] is None
    assert (f["path"], f["line"]) == (scratch.path, 4)
    before = len(scratch.issue_comments())

    out = _apply(
        scratch,
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f["id"],
                    "verdict": "PUSH_BACK",
                    "shape": "isolated",
                    "reply": "line 4 is a fixture, not a defect",
                },
            )
        ),
    ).json()
    assert out["posted"] == {"replies": 0, "resolved": 0, "issues": []}
    assert scratch.threads() == []  # a suppressed finding has no thread to open
    # the babysit comment is the only comment apply may add
    assert len(scratch.issue_comments()) == before + 1
    recorded = {
        d["id"]: d["verdict"] for d in scratch.state()["rounds"][0]["dispositions"]
    }
    assert recorded == {f["id"]: "PUSH_BACK"}
    assert (out["decision"], out["stop_reason"]) == ("stop", "no-in-scope-implement")


def test_apply_stores_reviewer_text_literally(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    """Reviewer text reaches the filed issue byte for byte, and no shell runs it.

    "Reviewer text never passes through a shell" is an invariant of the Surface with no
    grader: every other body in this suite is benign, so an implementation that built
    its `gh issue create` call as a shell string passed. The payload names a file the
    shell would create; the assertion is that it does not exist.
    """
    marker = tmp_path / "reviewer-text-reached-a-shell"
    payload = (
        f"line 7 is wrong $(touch {marker}) `touch {marker}` "
        f"; touch {marker} && touch {marker}"
    )
    scratch.comment(7, payload)
    p = _round(scratch)
    assert [f["body"] for f in p["findings"]] == [payload]

    out = _apply(
        scratch,
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": p["findings"][0]["id"],
                    "verdict": "OUT_OF_SCOPE",
                    "shape": "isolated",
                    "scope_outcome": "the twenty-line file",
                    "issue_title": f"kreview-acceptance {scratch.tag}: line 7",
                },
            )
        ),
    ).json()
    assert len(out["posted"]["issues"]) == 1
    issues = scratch.find_issues()
    assert len(issues) == 1
    assert payload in issues[0]["body"]
    assert not marker.exists()


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
    """`--dry-run` writes nothing — graded where there is something to write to.

    Both writing verdicts are present: IMPLEMENT (which would reply and resolve) and
    OUT_OF_SCOPE (which would also file an issue). With only the first, a dry run that
    still files issues passes.
    """
    c1 = scratch.comment(3, "line 3 should say three")
    c2 = scratch.comment(19, "the repository should also have a LICENSE file")
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
                {
                    "id": f"t{c2}",
                    "verdict": "OUT_OF_SCOPE",
                    "shape": "isolated",
                    "scope_outcome": "the twenty-line file",
                    "issue_title": f"kreview-acceptance {scratch.tag}: LICENSE file",
                },
            )
        ),
    ).json()
    assert out["posted"] == {"replies": 0, "resolved": 0, "issues": []}
    assert out["next"] is None
    for c in (c1, c2):
        thread = scratch.thread_of(c)
        assert thread["resolved"] is False
        assert len(thread["comments"]) == 1
    assert scratch.find_issues() == []
    assert scratch.babysit_comment() is None


def test_apply_refuses_a_closed_pr(scratch: ScratchPR, tmp_path: Path) -> None:
    """A real apply on a closed PR is refused (exit 3) and writes nothing.

    Every other write-side fixture is open and the replays are `--dry-run`, so without
    this a tool that posts to a merged or closed PR passes the gate.
    """
    c1 = scratch.comment(3, "line 3 should say three")
    dispositions = str(
        dispositions_file(
            tmp_path,
            {
                "id": f"t{c1}",
                "verdict": "PUSH_BACK",
                "shape": "isolated",
                "reply": "no",
            },
        )
    )
    gh("pr", "close", str(scratch.number), "--repo", scratch.repo)

    r = _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--dispositions",
        dispositions,
    )
    assert r.code == 3, (r.code, r.out, r.err)
    assert len(scratch.thread_of(c1)["comments"]) == 1
    assert scratch.babysit_comment() is None


A_FIX_COMMIT = "<the round's own fix commit>"  # replaced with a real sha at run time


@pytest.mark.parametrize(
    # each case violates exactly one rule and is otherwise complete: a case missing two
    # fields passes against a tool that validates only the other one, and exit 2 then
    # attributes nothing
    "broken",
    [
        pytest.param(
            {"verdict": "MAYBE", "shape": "isolated", "reply": "no"},
            id="unknown-verdict",
        ),
        pytest.param({"verdict": "PUSH_BACK", "reply": "no"}, id="missing-shape"),
        pytest.param(
            {"verdict": "PUSH_BACK", "shape": "systemic", "reply": "no"},
            id="systemic-without-root-cause",
        ),
        # one case per required-field family of the dispositions table: a tool that
        # validated `shape` and nothing else would otherwise pass the three above
        pytest.param(
            {"verdict": "IMPLEMENT", "shape": "isolated", "reply": "done"},
            id="implement-without-commit",
        ),
        pytest.param(
            {"verdict": "IMPLEMENT", "shape": "isolated", "commit": A_FIX_COMMIT},
            id="implement-without-reply",
        ),
        pytest.param(
            {"verdict": "PUSH_BACK", "shape": "isolated"},
            id="push-back-without-reply",
        ),
        pytest.param(
            {
                "verdict": "OUT_OF_SCOPE",
                "shape": "isolated",
                "issue_title": "kreview-acceptance: no scope outcome",
            },
            id="out-of-scope-without-scope-outcome",
        ),
        pytest.param(
            {
                "verdict": "OUT_OF_SCOPE",
                "shape": "isolated",
                "scope_outcome": "the twenty-line file",
            },
            id="out-of-scope-without-issue-title",
        ),
    ],
)
def test_apply_refuses_each_validation_class(
    scratch: ScratchPR, tmp_path: Path, broken: dict[str, Any]
) -> None:
    """Every validation class the Surface pins is exit 2 with nothing posted.

    The suite covered only "a finding with no disposition" and "a commit not on the PR";
    an implementation that accepted an unknown verdict, a `systemic` with no root cause,
    or an `IMPLEMENT` with no commit still passed.
    """
    c1 = scratch.comment(3, "line 3 should say three")
    case = dict(broken)
    if case.get("commit") == A_FIX_COMMIT:
        # the only thing wrong with this case must be the missing field, so the commit
        # it does carry is a real one on the PR head
        case["commit"] = scratch.push_fix("three")
    r = _kr(
        scratch,
        "apply",
        str(scratch.number),
        "--json",
        "--dispositions",
        str(dispositions_file(tmp_path, {"id": f"t{c1}", **case})),
    )
    assert r.code == 2, (r.code, r.out, r.err)
    assert r.err.strip()
    assert len(scratch.thread_of(c1)["comments"]) == 1
    assert scratch.find_issues() == []
    assert scratch.babysit_comment() is None


def test_apply_refuses_an_id_that_is_not_in_the_round(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    """An id the packet never carried is a validation failure, not a silent skip."""
    c1 = scratch.comment(3, "line 3 should say three")
    # a long, obviously-fake id: a short one like `t1` is a substring of real comment
    # ids, so the stderr assertion could pass without the tool naming anything
    absent = "t999999999999"
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
                {
                    "id": absent,
                    "verdict": "PUSH_BACK",
                    "shape": "isolated",
                    "reply": "no",
                },
            )
        ),
    )
    assert r.code == 2, (r.code, r.out, r.err)
    assert absent in r.err
    assert len(scratch.thread_of(c1)["comments"]) == 1


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
    # the stop is persisted by apply, before any report (decided 2026-09-20): a stop
    # rule that waited for `report --post` depended on the model remembering to post
    state = scratch.state()
    assert state["status"] == "stopped"
    assert (state["stopped"]["reason"], state["stopped"]["kind"]) == (
        "discuss",
        "escalate",
    )
    s = _kr(scratch, "status", str(scratch.number), "--json").json()
    assert s["babysit"]["status"] == "stopped"


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
    """A round whose every disposition re-raises a prior finding ends the loop.

    Round 1 implements (a stop is persisted by `apply`, so a round-1 push-back would
    have ended the loop as `no-in-scope-implement` before round 2 could exist).
    """
    c1 = scratch.comment(3, "line 3 should say three")
    first = _round(scratch)
    sha = scratch.push_fix("three")
    r1 = _apply(
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
                    "verdict": "IMPLEMENT",
                    "shape": "isolated",
                    "commit": sha,
                    "reply": "line 3 now says three",
                },
            )
        ),
    ).json()
    assert r1["decision"] == "continue"

    c2 = scratch.comment(4, "line 4 should say four, same as line 3")
    second = _round(scratch)
    assert {f["id"] for f in second["findings"]} == {f"t{c2}"}
    assert second["ledger"][f"t{c1}"]["verdict"] == "IMPLEMENT"

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
    # D13: one babysit comment, rewritten each round — not one appended per round
    reports = [
        c for c in scratch.issue_comments() if c["body"].startswith("## Babysit report")
    ]
    assert len(reports) == 1
    assert [r["n"] for r in scratch.state()["rounds"]] == [1, 2]


def test_apply_refuses_a_repeat_of_outside_the_ledger(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    """`repeat_of` must name a finding the ledger carries, or any string converges.

    `repeats-only` is a stop rule evaluated from the model's own tags, so an unchecked
    `repeat_of` is a way to end a loop by writing a word: the round below is identical
    to the converging one above except that the id it claims to re-raise was never
    dispositioned.
    """
    c1 = scratch.comment(3, "line 3 should say three")
    first = _round(scratch)
    # round 1 implements: a push-back-only round converges on `no-in-scope-implement`
    # and `apply` persists the stop, so the second apply below would exit 5 for a
    # missing `--reenter` and never reach the `repeat_of` validation under test
    sha = scratch.push_fix("three")
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
                    "verdict": "IMPLEMENT",
                    "shape": "isolated",
                    "commit": sha,
                    "reply": "line 3 now says three",
                },
            )
        ),
    )

    c2 = scratch.comment(4, "line 4 should say four, same as line 3")
    second = _round(scratch)
    absent = "t999999999999"
    assert absent not in second["ledger"]
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
                    "id": f"t{c2}",
                    "verdict": "PUSH_BACK",
                    "shape": "isolated",
                    "repeat_of": absent,
                    "reply": "same point as before",
                },
            )
        ),
    )
    assert r.code == 2, (r.code, r.out, r.err)
    assert absent in r.err
    assert len(scratch.thread_of(c2)["comments"]) == 1
    # round 2 is not recorded: validation happens before anything is written
    assert [rnd["n"] for rnd in scratch.state()["rounds"]] == [1]


def _systemic_fix_round(
    scratch: ScratchPR, tmp_path: Path, line: int, root: str, window: dict | None = None
) -> dict:
    """One round: a comment on `line`, a pushed class fix, a `systemic` IMPLEMENT."""
    cid = scratch.comment(line, f"line {line} has no trailing metadata")
    if window is None:
        window = _round(scratch)["window"]
    sha = scratch.push_fix(f"metadata for line {line}")
    return _apply(
        scratch,
        "--since",
        window["since"],
        "--until",
        window["until"],
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{cid}",
                    "verdict": "IMPLEMENT",
                    "shape": "systemic",
                    "root_cause": root,
                    "commit": sha,
                    "reply": "class fix across every site",
                },
            )
        ),
    ).json()


def test_apply_systemic_third_time_diverges(scratch: ScratchPR, tmp_path: Path) -> None:
    """A repeated systemic root cause is the model's class fix; a third is divergence.

    Decided 2026-09-20: the loop stops when it has converged or is diverging, on
    nothing else. The second occurrence of a root cause is not a stop — it is the
    model's to research across every site and close as one class fix — and the
    output names it so the report can say the first fix did not hold. The third
    occurrence means the class fix was made twice and held neither time.
    """
    root = "the file carries no per-line metadata"
    r1 = _systemic_fix_round(scratch, tmp_path, 3, root)
    assert (r1["decision"], r1["repeat_root_causes"]) == ("continue", [])

    r2 = _systemic_fix_round(scratch, tmp_path, 9, root)
    assert r2["decision"] == "continue"
    assert r2["repeat_root_causes"] == [root]

    r3 = _systemic_fix_round(scratch, tmp_path, 12, root)
    assert (r3["decision"], r3["stop_kind"], r3["stop_reason"]) == (
        "stop",
        "diverging",
        "systemic-third-time",
    )
    r = _kr(
        scratch,
        "report",
        str(scratch.number),
        "--tldr",
        "three rounds, one mechanism",
        "--kselfreview",
        "na",
    )
    assert r.code == 0, (r.out, r.err)
    assert "⚠️ needs human decision (diverging: systemic-third-time)" in r.out
    assert "✅" not in r.out


def test_apply_no_progress_diverges(scratch: ScratchPR, tmp_path: Path) -> None:
    """Two consecutive rounds with no fewer original-diff findings is going nowhere.

    Each round: one new comment on an untouched line of the original file (so it
    blames `original`), an isolated IMPLEMENT with a fix pushed. `on_original` reads
    1, 1, 1 — round 2 is the first non-decrease and continues; round 3 is the second
    and stops as `diverging: no-progress`. A round with nothing on the original diff
    can never fire this rule: that round is second-order, a convergence.
    """
    for line, expected in ((5, "continue"), (7, "continue")):
        cid = scratch.comment(line, f"line {line} should be clearer")
        sha = scratch.push_fix(f"clarified line {line}")
        out = _apply(
            scratch,
            "--dispositions",
            str(
                dispositions_file(
                    tmp_path,
                    {
                        "id": f"t{cid}",
                        "verdict": "IMPLEMENT",
                        "shape": "isolated",
                        "commit": sha,
                        "reply": "clarified",
                    },
                )
            ),
        ).json()
        assert out["decision"] == expected, (line, out)

    cid = scratch.comment(11, "line 11 should be clearer")
    sha = scratch.push_fix("clarified line 11")
    out = _apply(
        scratch,
        "--dispositions",
        str(
            dispositions_file(
                tmp_path,
                {
                    "id": f"t{cid}",
                    "verdict": "IMPLEMENT",
                    "shape": "isolated",
                    "commit": sha,
                    "reply": "clarified",
                },
            )
        ),
    ).json()
    assert (out["decision"], out["stop_kind"], out["stop_reason"]) == (
        "stop",
        "diverging",
        "no-progress",
    )
    rounds = scratch.state()["rounds"]
    assert [r["signals"]["on_original"] for r in rounds] == [1, 1, 1]


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
    assert nxt["signals"]["budget"] == {"max_rounds": None, "used_this_run": 1}
    assert f"t{c1}" in nxt["ledger"]
    assert nxt["ledger"][f"t{c1}"]["verdict"] == "IMPLEMENT"
    s = _kr(scratch, "status", str(scratch.number), "--json").json()
    assert s["babysit"]["rounds"] == 1  # round 2 is open, not yet applied
    assert s["babysit"]["status"] == "running"


# --------------------------------- J1/J2 (M1 verdict order, provenance) graded here


def test_round_unknown_provenance_after_a_rebase(scratch: ScratchPR) -> None:
    """A force-push puts the reviewed commit out of history: provenance is unknown.

    The third provenance state cannot be produced from this repository's merged
    fixtures — none was force-pushed after a review — and it is the state the signed
    rule turns on: an unknown must never fire the second-order stop. Here the reviewed
    commit is still served by GitHub but is no longer an ancestor of the head, so no
    boundary is reachable and the finding on it is neither original nor review-fix.
    """
    c1 = scratch.comment(3, "line 3 should say three")
    before = _round(scratch)
    assert before["boundary"]["status"] == "ok"
    assert findings_by_id(before)[f"t{c1}"]["provenance"] == "original"

    scratch.rewrite_head("rewritten")
    p = _round(scratch)
    assert p["boundary"]["status"] == "none-reachable"
    f = findings_by_id(p)[f"t{c1}"]
    assert f["provenance"] == "unknown"
    assert "pre-rebase" in f["provenance_detail"]
    sig = p["signals"]
    assert sig["unknown"] == sig["line_anchored"] == 1
    assert sig["on_review_fix"] == sig["on_original"] == 0
    assert sig["second_order"] is False


def _status_until_ci_settles(pr: ScratchPR, deadline_s: int = 240) -> dict:
    """Poll `status` until the head's CI is no longer pending (Actions takes ~1 min).

    `none` is waited on exactly like `pending`: in the first seconds after the push
    Actions has not created the check run yet, so `status` reports no checks at all.
    Returning on `none` would fail a correct implementation before its check existed —
    "not started" is not a settled state.
    """
    started = time.monotonic()
    while True:
        r = _kr(pr, "status", str(pr.number), "--json")
        assert r.code in (0, 3), (r.out, r.err)
        s = r.json()
        if s["ci"]["status"] not in ("pending", "none"):
            return s
        if time.monotonic() - started > deadline_s:
            return s  # the test's own assertion names the state it timed out on
        time.sleep(15)


def test_status_stops_on_red_ci(scratch_factory) -> None:
    """A red check on the head is a stop, not a fact the model may read past.

    Karl, 2026-09-13 (PR #66 DISCUSS): CI not passing is the kind of debt that creeps;
    the verdict carries it. `checkout-mismatch` outranks it — this test runs from a
    clone on the PR branch, so the checkout matches and only CI decides.
    """
    pr = scratch_factory(failing_workflow=True)
    s = _status_until_ci_settles(pr)
    assert s["ci"]["status"] == "failing", s["ci"]
    assert any(c["status"] == "failing" for c in s["ci"]["checks"])
    assert s["verdict"] == "stop: ci-failing"
    assert s["scope"]["status"] == "present"
    r = _kr(pr, "status", str(pr.number), "--json")
    assert r.code == 3


def test_status_stops_on_draft(scratch_factory) -> None:
    pr = scratch_factory(draft=True)
    r = _kr(pr, "status", str(pr.number), "--json")
    assert r.code == 3, (r.out, r.err)
    s = r.json()
    assert s["pr"]["draft"] is True
    assert s["verdict"] == "stop: draft"


def test_status_stops_on_empty_scope(scratch_factory) -> None:
    pr = scratch_factory(scope="")
    r = _kr(pr, "status", str(pr.number), "--json")
    assert r.code == 3, (r.out, r.err)
    s = r.json()
    assert s["scope"] == {"status": "empty", "text": ""}
    assert s["verdict"] == "stop: scope-empty"


def test_status_stops_on_scope_missing(scratch_factory) -> None:
    """The verdict, not just the field — an **open** PR with no `## Review scope`.

    M1 grades `scope.status` `missing` on #19 and the precedence that `closed` outranks
    it, and every M1 fixture is merged or closed, so a rule above `scope-missing` always
    decides there: a tool that never emitted this verdict passed the whole suite. It is
    the fence kbabysit §0 refuses to start without, so it cannot be the one stop nobody
    grades.
    """
    pr = scratch_factory(scope=None)
    r = _kr(pr, "status", str(pr.number), "--json")
    assert r.code == 3, (r.out, r.err)
    s = r.json()
    assert s["pr"]["state"] == "open"
    assert s["scope"] == {"status": "missing", "text": ""}
    assert s["verdict"] == "stop: scope-missing"


def test_status_is_ready_on_a_fresh_pr(scratch: ScratchPR) -> None:
    """The verdict the whole loop hangs on — `ready`, exit 0 — with its empty states.

    Every other `status` test asserts a *stop*, so a tool that never returned `ready`
    passed them all. A freshly opened PR is also the only place three "nothing yet"
    values occur together: no review, so `boundary` is `none` and `reentry` is `none`;
    no workflow on the branch, so `ci` is `none` with an empty check list.
    """
    r = _kr(scratch, "status", str(scratch.number), "--json")
    assert r.code == 0, (r.out, r.err)
    s = r.json()
    assert s["verdict"] == "ready"
    assert s["pr"]["state"] == "open"
    assert s["checkout"]["matches_pr"] is True
    assert s["scope"]["status"] == "present"
    assert s["boundary"]["status"] == "none"
    assert s["ci"] == {"status": "none", "checks": []}
    assert s["reentry"] == "none"
    assert s["reviews"]["last_reviewed_sha"] is None
    assert s["reviews"]["unreviewed_commits"] == []
    assert s["kselfreview_range"] is None
    assert s["babysit"]["report_present"] is False


def test_status_stops_on_checkout_mismatch(scratch: ScratchPR) -> None:
    """A checkout on another branch stops the run, and only that rule holds here.

    `checkout-mismatch` was graded only as the verdict `merged` outranks on #49, so a
    tool that never emitted it on its own still passed: this PR is open, in scope and
    green, and the checkout is the one thing wrong with it.
    """
    # the everyday version of this mistake: babysitting from the base branch
    git("checkout", "-q", "main", cwd=scratch.clone)  # A2 pins the default branch
    r = _kr(scratch, "status", str(scratch.number), "--json")
    assert r.code == 3, (r.out, r.err)
    s = r.json()
    assert s["pr"]["state"] == "open"
    assert s["checkout"]["matches_pr"] is False
    assert s["verdict"] == "stop: checkout-mismatch"


# ------------------------------------------------------------ J9/J8: report, re-entry


def test_report_refuses_while_running(scratch: ScratchPR, tmp_path: Path) -> None:
    """A report follows a stop and never precedes one (decided 2026-09-20).

    An `apply` that decided `continue` leaves the loop running; a report on it had a
    path to ✅ (no DISCUSS, no escalate stop, CI green) that the verdict rule's own
    next sentence forbids. Both forms exit 5 and the comment is untouched.
    """
    c_fix = scratch.comment(3, "line 3 should say three")
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
            )
        ),
    )
    assert r.code == 0, (r.out, r.err)
    assert r.json()["decision"] == "continue"
    before = scratch.babysit_comment()
    assert before is not None
    assert '"status": "running"' in before

    for form in (["--post"], []):
        r = _kr(
            scratch,
            "report",
            str(scratch.number),
            *form,
            "--tldr",
            "posted too early",
            "--kselfreview",
            "na",
        )
        assert r.code == 5, (form, r.out, r.err)
        assert "apply --stop" in r.err
        assert "posted too early" not in r.out
    assert scratch.babysit_comment() == before
    assert "**Verdict:**" not in before
    s = _kr(scratch, "status", str(scratch.number), "--json").json()
    assert s["babysit"]["status"] == "running"


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


def test_report_renders_every_changed_line_in_order(
    scratch: ScratchPR, tmp_path: Path
) -> None:
    """`--changed` given twice puts both lines in the section, in order.

    J9 makes the `--changed` lines the model's entire contribution to *What changed
    because of review*, and every other report test omits the option and asserts only
    the zero-value fallback. An implementation that parsed `--changed` and discarded it
    — or kept just the last one — passed the whole suite.
    """
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
    first = "the first thing that changed"
    second = "the second thing that changed"
    r = _kr(
        scratch,
        "report",
        str(scratch.number),
        "--json",
        "--post",
        "--tldr",
        "One round, two changed lines.",
        "--changed",
        first,
        "--changed",
        second,
        "--kselfreview",
        "na",
    )
    assert r.code == 0, (r.out, r.err)
    comment = scratch.babysit_comment()
    assert comment is not None
    assert f"- {first}" in comment
    assert f"- {second}" in comment
    # order is the order given, and the fallback is gone once a line is supplied
    assert comment.index(first) < comment.index(second)
    assert "nothing — pre-PR gates held" not in comment


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

    # a re-entry is "fresh budget, inherited ledger" (A9): a run that carried
    # used_this_run forward, or dropped run 1's dispositions, also reaches run 2
    p = _round(scratch)
    assert p["signals"]["budget"] == {"max_rounds": None, "used_this_run": 1}
    assert p["ledger"][f"t{c1}"]["verdict"] == "PUSH_BACK"
    assert p["ledger"][f"t{c2}"]["verdict"] == "PUSH_BACK"


# ------------------------------------------------------------------ J10: skills


FORBIDDEN_COMMANDS = ("gh", "git", "awk", "jq", "curl")
# What a shell fence in a rewritten skill may invoke, and nothing else: the tool, the
# self-review pass, the standing gates, and the shell's own plumbing. The model's
# commits and pushes (D5) are prose in the skills, never a fenced `git` line.
ALLOWED_IN_SHELL_FENCES = frozenset(
    {
        "kreview",
        "kselfreview",
        "make",
        "uv",
        "cd",
        "cat",
        "echo",
        "printf",
        "sleep",
        "mktemp",
        "exit",
        "set",
        "true",
        "false",
    }
)
_SHELL_FENCE_LANGS = frozenset({"bash", "sh", "shell", "zsh", "console"})

# where one command ends and the next begins: a pipe, a separator, a subshell, a
# command substitution, a redirection
_COMMAND_BREAK = re.compile(r"\$\(|&&|\|\||[|;&()`{}]")
# a redirection and its target (`2>/dev/null`, `> "$OUT"`, `<<'EOF'`, `<<<"$BODY"`)
# and a `<placeholder>`: neither is a command
_REDIRECT = re.compile(r"\d?(?:<<<|<<-?|[<>]{1,2}&?)\s*\S*")
# a loop or case header: what follows `in` is data, and the body starts after `do`
_LOOP_HEADER = re.compile(r"^\s*(?:for|select|case)\s")
# shell syntax that can precede the command word without being one: a console
# prompt, negation, the keywords. Wrappers (`sudo`, `env`, `xargs`, `time`, `command`,
# `nohup`, `exec`) are deliberately *not* here: stripping them is how the allowlist
# failed open — `env -i gh …` lost `env`, could not classify `-i`, and yielded nothing,
# which both graders read as "no command". A wrapper is a command the allowlist does
# not name, and that is the whole verdict on it.
_NOT_THE_COMMAND = {
    "$",
    "!",
    "if",
    "then",
    "elif",
    "else",
    "while",
    "until",
    "do",
    "fi",
    "done",
    "esac",
    "export",
    "local",
    "readonly",
}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*=")
# a `#` that begins a word starts a comment (POSIX); `"$#"`, `'#'` and `${#x}` do not
_COMMENT = re.compile(r"(^|\s)#.*$")
_COMMAND_WORD = re.compile(r"^[A-Za-z_][\w.-]*$")
_QUOTED = re.compile(r"""^(["'])(.+)\1$""")
# the shell removes quotes and `\` escapes anywhere in a word, not only around or in
# front of it: `g\h`, `g"h"` and `"g"h` all execute `gh`. Enumerating the spellings we
# had seen is what let `g\h api x` through both graders (round 5 of #66); this applies
# the rule instead, so there is no next spelling for the same reason there is no next
# position. Quotes are removed only when the token's own quotes are **balanced**:
# `_COMMAND_BREAK` splits on `|` without knowing about quoting, so a jq expression
# (`'[.[] | select(…)] | length'`) arrives here as fragments, and unquoting `length'`
# would invent a command named `length` in a line that has none — a grader that fails a
# correct rewrite is the corrupted signal the test-quality rule forbids
_ESCAPE = re.compile(r"\\(.)")
_QUOTE = re.compile(r"""["']""")
# `/kbabysit` is a slash command, not a path: one leading slash and no directory
_SLASH_COMMAND = re.compile(r"^/[^/]+$")
# group 2 is the **whole** info string, not its alphabetic prefix. `([A-Za-z]*)` matched
# the empty string on ` ```123 ` and ` ``` || true `, and `_closes` reads "no info
# string"
# as "closer" — so a content line with a non-alphabetic tail ended the block and every
# command after it left both graders (round 6 of #66). The predicate was an enumeration
# of the info strings we had pictured; CommonMark's rule is that a closer carries only
# trailing whitespace, and that is what is read now
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})[ \t]*(.*)$")


def _info(m: re.Match[str] | None) -> str:
    """The fence's info string, trimmed — `""` when it has none."""
    return m.group(2).strip() if m else ""


def _fence_lang(m: re.Match[str]) -> str:
    """The language word of an opening fence: the info string's first word, lowered."""
    info = _info(m)
    return info.split()[0].lower() if info else ""


_HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")


def _closes(m: re.Match[str] | None, fence: str) -> bool:
    """Whether marker `m` closes the block opened by `fence`.

    Same character, at least as long — so a ````bash block wrapping a ``` example stays
    one block — **and no info string**: CommonMark closing fences carry none, so a
    ` ```text ` line inside a ` ```bash ` block is content, not the end of it. Treating
    it as the end dropped every following line out of both graders (round 5 of #66).
    """
    return bool(
        m
        and m.group(1)[0] == fence[0]
        and len(m.group(1)) >= len(fence)
        and not _info(m)
    )


def _command_word(token: str) -> str | None:
    """The command a segment's first token names, or `None` when it names none.

    `"gh"`, `\\gh`, `g\\h`, `g"h"`, `/usr/bin/gh`, `./tools/gh`, `tools/gh` all invoke
    `gh`, and a grader that accepts only bare identifiers calls every one of them "not a
    command".
    That drops the segment from **both** graders below, so the fail-closed allowlist
    fails open on precisely the spellings an allowlist exists to stop: the first
    version of it passed `/usr/bin/gh api …` silently. `$TOOL` cannot be resolved by
    reading, so it is returned as itself — unresolvable is not the same as allowed, and
    the allowlist must name it rather than skip it. `/kbabysit <pr>` still names no
    command: a slash command is one leading slash with no directory, not a path.
    """
    token = _ESCAPE.sub(lambda m: m.group(1), token)
    if token.count('"') % 2 == 0 and token.count("'") % 2 == 0:
        token = _QUOTE.sub("", token)
    if token.startswith("$") and len(token) > 1:
        return token
    if "/" in token and not _SLASH_COMMAND.match(token):
        token = token.rsplit("/", 1)[-1]
    return token if _COMMAND_WORD.match(token) else None


def _commands(snippet: str) -> list[list[str]]:
    """The command of every segment of `snippet`: `[word, *args]`, keywords stripped.

    `REPO=$(gh repo view …)`, `if git merge-base …`, `… | jq '.x'` and `VAR=1 curl …`
    each yield their real command word; a grader that reads `words[0]` of the whole
    snippet sees none of them. Segments whose first token names no command
    (`<sha>`, `--flag`, `…`, `/kbabysit`, a JSON fragment) yield nothing. A wrapper
    (`sudo`, `env -i`, `timeout 5`) *is* the command word: what it runs is its argument,
    and the allowlist judges it by its own name.
    """
    out: list[list[str]] = []
    for segment in _COMMAND_BREAK.split(_COMMENT.sub(" ", snippet)):
        if _LOOP_HEADER.match(segment):
            continue
        # split() on any whitespace: a space-only split misses `git\tstatus`
        words = _REDIRECT.sub(" ", segment).split()
        while words and (words[0] in _NOT_THE_COMMAND or _ASSIGNMENT.match(words[0])):
            words = words[1:]
        word = _command_word(words[0]) if words else None
        if word:
            out.append([word, *words[1:]])
    return out


def _code(text: str) -> tuple[list[str], list[str]]:
    """(lines of labeled shell fences, every other code: other fences + inline spans).

    Fences close only on a marker at least as long as the one that opened them, so a
    ````bash block wrapping a ``` example stays one block. Heredoc bodies are data and
    `#` comments are prose: both are dropped. A backslash continuation is shell syntax,
    not data: `kreview status 66 \\` followed by `| jq '.verdict'` is one command line
    with a `jq` on it, so continued lines are joined into the line they continue (the
    version that dropped them hid that `jq` from both graders — round 4 of #66).
    """
    shell: list[str] = []
    other: list[str] = []
    fence = ""
    in_shell = False
    heredoc: str | None = None
    joined = ""
    for line in text.splitlines():
        m = _FENCE.match(line)
        if not fence:
            if m:
                fence, in_shell = m.group(1), _fence_lang(m) in _SHELL_FENCE_LANGS
                continue
            other.extend(re.findall(r"`([^`\n]+)`", line))
            continue
        if _closes(m, fence):
            fence, heredoc, joined = "", None, ""
            continue
        if heredoc is not None:
            if line.strip() == heredoc:
                heredoc = None
            continue
        if not in_shell:
            other.append(line)
            continue
        stripped = line.strip()
        if stripped.startswith("#") and not joined:
            continue
        if stripped.endswith("\\"):
            joined += stripped[:-1] + " "
            continue
        line, joined = joined + stripped, ""
        shell.append(line)
        hd = _HEREDOC.search(line)
        if hd:
            heredoc = hd.group(1)
    return shell, other


def _tokens(line: str) -> list[str]:
    """Every command-shaped token of a shell line, in no particular position.

    Separators, redirections and their targets are removed; what remains is read through
    `_command_word`, so `"gh"`, `\\gh` and `/usr/bin/gh` are `gh` and `--json`, `'.x'`,
    `tests/unit/test_git.py` are nothing. Position-free on purpose: four rounds each
    found one more place a command word can stand (after an assignment, a keyword, a
    pipe, a wrapper, a wrapper's option, a continuation), and a reader with no notion of
    position has no next place to miss.
    """
    words = _REDIRECT.sub(" ", _COMMAND_BREAK.sub(" ", _COMMENT.sub(" ", line))).split()
    return [w for w in (_command_word(t) for t in words) if w]


def _shell_invocations(text: str) -> list[str]:
    """Every fenced line or inline code span that *invokes* a forbidden command.

    The Surface pins "no `gh `, `git `, `awk`, `jq`, or `curl` invocation" anywhere in
    code. In a **labeled shell fence** the read is position-free: the forbidden word as
    any token of the line (`_tokens`) is the finding, whatever wraps it — `env -i gh`,
    `sudo -u bob gh`, a `jq` on a continued line. Elsewhere — inline spans, unlabeled
    and non-shell fences — code is closer to prose (`use jq to filter` in a `text`
    fence names a tool), so the read is by command position (`_commands`), and an
    invocation is the command word *plus at least one argument*: a bare `gh` in a code
    span names the CLI, and failing a correct rewrite for naming it is the corrupted
    signal the test-quality rule forbids.
    """
    shell, other = _code(text)
    fenced = [
        s.strip() for s in shell if any(t in FORBIDDEN_COMMANDS for t in _tokens(s))
    ]
    spans = [
        s.strip()
        for s in other
        if any(len(w) >= 2 and w[0] in FORBIDDEN_COMMANDS for w in _commands(s))
    ]
    return fenced + spans


def _unlisted_commands(text: str) -> list[str]:
    """Every labeled shell-fence line whose command is outside the allowlist.

    The blocklist above names what the skills must stop doing; this names what they may
    still do, so a rewrite that reaches for a tool nobody listed — `timeout 5 gh …`,
    `eval`, `bash -c`, a `python` one-liner that shells out — fails closed instead of
    passing until someone thinks of its spelling. Fail-closed holds only while the
    command word is read as written: the version that stripped wrappers before reading
    it passed `env -i gh …` (round 4 of #66), because `-i` classified as nothing and
    nothing is not on any list. So `env` is the command word here, and `env` is
    unlisted.
    """
    shell, _ = _code(text)
    return [
        f"{s.strip()}  [{w[0]}]"
        for s in shell
        for w in _commands(s)
        if w[0] not in ALLOWED_IN_SHELL_FENCES
    ]


# The grader's own graders. J10 is the one blocking test whose verdict is produced by a
# parser rather than read off an API, so "it was falsified by hand before it was kept"
# is a claim only a committed case table can carry: every row below is a command
# position that escaped some earlier version of it, or an allowed line that must not be
# failed for naming a tool. `blocked` is the blocklist verdict, `unlisted` the
# allowlist's; they differ on purpose — a bare `gh` in a shell fence is not an
# invocation (no argument) but is still not on the allowlist.
J10_CASES = [
    # the escapes: a command word that is not a bare identifier
    ("absolute-path", "/usr/bin/gh api repos/x/y", True, True),
    ("relative-path", "./tools/gh api repos/x/y", True, True),
    ("parent-path", "../bin/gh api repos/x/y", True, True),
    ("bare-dir-path", "tools/gh api repos/x/y", True, True),
    ("quoted-command", '"gh" api repos/x/y', True, True),
    ("escaped-command", "\\gh api repos/x/y", True, True),
    # unresolvable by reading: the allowlist must name it, not skip it
    ("variable-indirection", "$TOOL api repos/x/y", False, True),
    # positions earlier rounds widened the blocklist to reach
    ("plain", "gh api repos/x/y", True, True),
    ("assignment", "REPO=$(gh repo view --json nameWithOwner)", True, True),
    ("shell-keyword", "if git merge-base --is-ancestor a b; then", True, True),
    ("pipe", "kreview status 66 --json | jq '.verdict'", True, True),
    ("env-prefix", "VAR=1 curl -s https://x", True, True),
    ("loop-body", "while gh api x; do sleep 1; done", True, True),
    # the fifth position (round 4 of #66): a wrapper with options, and a continuation.
    # Both escaped a reader that stripped wrappers and dropped continued lines; a
    # position-free blocklist has nowhere for them to hide, and the allowlist names the
    # wrapper itself
    ("wrapper", "timeout 5 gh api repos/x/y", True, True),
    ("wrapper-option", "env -i gh api repos/x/y", True, True),
    ("wrapper-option-arg", "env -u HOME git push", True, True),
    ("wrapper-xargs", "xargs -0 gh api repos/x/y", True, True),
    ("wrapper-sudo-user", "sudo -u bob gh api repos/x/y", True, True),
    ("wrapper-command-v", "command -v gh api", True, True),
    ("wrapper-time", "time -p gh api repos/x/y", True, True),
    ("continuation", "kreview status 66 \\\n  | jq '.verdict'", True, True),
    # after `\`, a line beginning with `#` is a comment in the shell, so this `jq` never
    # runs; the row first asserted the opposite (2026-09-19) and the comment rule
    # measured 2026-09-20 corrected it
    ("continuation-comment", "kreview status 66 \\\n  # | jq '.verdict'", False, False),
    # a command the blocklist cannot read out of a string: the allowlist names the
    # interpreter, which is why both graders exist. The token `"gh` has one quote, so
    # the balanced-quote rule leaves it unclassifiable — deliberately: the alternative
    # invents commands out of jq fragments (see `_QUOTE`)
    ("eval", 'eval "gh api repos/x/y"', False, True),
    ("interpreter", "bash -c 'gh api repos/x/y'", False, True),
    # the spellings the enumeration missed: an escape or a quote *inside* the word
    ("internal-escape", "g\\h api repos/x/y", True, True),
    ("internal-quote", 'g"h" api repos/x/y', True, True),
    ("split-quote", '"g"h api repos/x/y', True, True),
    # a same-length marker carrying an info string is content, not a closing fence —
    # any info string, not only an alphabetic one, which is what round 6 measured
    ("nested-info-marker", "kreview status 66\n```text\ngh api repos/x/y", True, True),
    ("nested-digit-marker", "kreview status 66\n```123\ngh api repos/x/y", True, True),
    (
        "nested-nonalpha-marker",
        "kreview status 66\n``` || true\ngh api repos/x/y",
        True,
        True,
    ),
    # what the position-free read costs, pinned so the brief's claims re-derive. A
    # heredoc body is data and escapes *both* lists (the allowlist reads `cat`, which is
    # allowed) — the same deliberate hole as `comment`, below. And a forbidden word is a
    # hit wherever it stands, so a path whose basename is one, or one inside a quoted
    # argument, reads as an invocation: that is the precision the wider read trades away
    ("heredoc-body", "cat <<EOF\ngh api repos/x/y\nEOF", False, False),
    # a here-string is not a heredoc opener, and `kbabysit` uses two today: if
    # `_HEREDOC` read `<<<"$BODY"` as opening a body, everything after it in the fence
    # would be swallowed. Ungraded until now, and true by the width of one `\w+`
    ("here-string", 'grep -q scope <<<"$BODY"\ngh api repos/x/y', True, True),
    ("path-basename", "cat docs/notes/git", True, False),
    ("quoted-word-arg", 'printf "%s" "run jq on it"', True, False),
    # and what a correct rewrite contains: none of these may fail
    ("allowed-tool", "kreview status 66 --json", False, False),
    ("allowed-gate", "make check", False, False),
    ("allowed-quoted-arg", 'cd "$REPO_ROOT"', False, False),
    # passes because the basename is `test_git.py`, not `git` — `path-basename` above
    # is the other side of this boundary, and neither row proves paths at large are safe
    ("allowed-path-arg", "uv run pytest tests/unit/test_git.py", False, False),
    ("allowed-continuation", "uv run pytest \\\n  tests/unit", False, False),
    ("slash-command", "/kbabysit 66", False, False),
    ("comment", "# gh api repos/x/y was the old way", False, False),
    # a trailing comment ends the line for both graders: measured 2026-09-20, the
    # `(default 3, …)` in kbabysit's usage line read as a command named `default`
    (
        "trailing-comment",
        "make check   # gh api x was the old way (default 3)",
        False,
        False,
    ),
    ("hash-in-quotes", 'printf "%s" "#" "$#"', False, False),
]


@pytest.mark.parametrize(("case", "line", "blocked", "unlisted"), J10_CASES)
def test_j10_grader_reads_every_command_position(
    case: str, line: str, blocked: bool, unlisted: bool
) -> None:
    """Falsify J10's parser before trusting its verdict on the real skills.

    Measured 2026-09-13: `/usr/bin/gh api …` and its four siblings passed *both*
    graders, because a command word that is not a bare identifier yielded no command at
    all — so the fail-closed allowlist failed open on exactly the spellings it exists
    to stop. Measured 2026-09-14: `env -i gh api …` and five more wrapper forms, plus a
    `jq` on a continued line, passed both again — same mechanism, one token to the
    right. The `allowed-*` rows are the other half of the check: a grader that fails a
    correct rewrite is a corrupted signal, not a strict one.
    """
    fenced = f"```bash\n{line}\n```"
    assert bool(_shell_invocations(fenced)) is blocked, (case, _tokens(line))
    assert bool(_unlisted_commands(fenced)) is unlisted, (case, _commands(line))


PROSE_CODE = [
    ("unlabeled-fence", "```\n{}\n```"),
    ("text-fence", "```text\n{}\n```"),
    ("inline-span", "see `{}` above"),
]


@pytest.mark.parametrize(("where", "template"), PROSE_CODE)
def test_j10_prose_code_keeps_the_command_position_read(
    where: str, template: str
) -> None:
    """The boundary of the 2026-09-19 decision, measured rather than asserted in prose.

    Position-free reading applies to labeled shell fences only; elsewhere code is closer
    to prose (`use jq to filter` in a `text` fence names a tool), so the read is by
    command position. The consequence is the part the brief has to state and this test
    has to pin: a plain invocation is still caught there, but a **wrapper form is held
    by neither list** — the allowlist does not run outside labeled shell fences at all.
    The parametrized table above cannot reach this, because its fixture wraps every line
    in a ```bash fence.
    """
    plain = template.format("gh api repos/x/y")
    assert _shell_invocations(plain), f"{where}: a plain invocation must still be read"

    wrapped = template.format("env -i gh api repos/x/y")
    assert not _shell_invocations(wrapped), f"{where}: expected the weaker read"
    assert not _unlisted_commands(wrapped), f"{where}: the allowlist is fence-scoped"


def _unlabeled_fence_commands(text: str) -> list[str]:
    """Every line of an *unlabeled* fence that names a command, allowed or not.

    The position-free read and the allowlist cover labeled shell fences only, so a
    shell block whose author forgot the ` ```bash ` label would pass both graders and
    be told nothing (measured 2026-09-19: `env -i gh api x` in a bare ` ``` ` fence is
    held by neither list). Decided 2026-09-20: a fence that holds a command is labeled.
    Usage lines (`/kbabysit <pr>`) name no command and keep their bare fence.
    """
    out: list[str] = []
    fence, unlabeled = "", False
    for line in text.splitlines():
        m = _FENCE.match(line)
        if not fence:
            if m:
                fence, unlabeled = m.group(1), not _info(m)
            continue
        if _closes(m, fence):
            fence = ""
            continue
        if unlabeled and _commands(line):
            out.append(line.strip())
    return out


def _heredoc_openers(text: str) -> list[str]:
    """Every labeled shell-fence line that opens a heredoc.

    A heredoc body is data to both graders, so a script generated through one is code no
    grader reads. Decided 2026-09-20: the two skills open none — posting and filing are
    the tool's job, so the rewrite has nothing to write a body for. A here-string
    (`<<<"$BODY"`) is not an opener and stays allowed (the `here-string` row).
    """
    shell, _ = _code(text)
    return [s.strip() for s in shell if _HEREDOC.search(s)]


# The reach assertions' own cases: what each must flag, and what it must leave alone
J10_REACH_CASES = [
    ("unlabeled-command", "```\nkreview status 66 --json\n```", True, False),
    ("unlabeled-forbidden", "```\nenv -i gh api repos/x/y\n```", True, False),
    ("unlabeled-usage", "```\n/kbabysit <pr-number>\n/kbabysit\n```", False, False),
    (
        "unlabeled-usage-comment",
        "```\n/kbabysit <pr> max-rounds: 5   # raise the budget (default 3)\n```",
        False,
        False,
    ),
    ("unlabeled-placeholder", "```\n<sha> — <one line>\n```", False, False),
    ("labeled-command", "```bash\nkreview status 66 --json\n```", False, False),
    ("text-fence-prose", "```text\nuse jq to filter\n```", False, False),
    ("heredoc", "```bash\ncat <<EOF\ngh api repos/x/y\nEOF\n```", False, True),
    ("heredoc-quoted", "```bash\ncat <<'EOF' > f\nx\nEOF\n```", False, True),
    ("here-string", '```bash\ncat <<<"$BODY"\n```', False, False),
    ("heredoc-unlabeled", "```\ncat <<EOF\nx\nEOF\n```", True, False),
]


@pytest.mark.parametrize(("case", "text", "unlabeled", "heredoc"), J10_REACH_CASES)
def test_j10_reach_assertions_read_what_they_claim(
    case: str, text: str, unlabeled: bool, heredoc: bool
) -> None:
    """The two 2026-09-20 assertions, falsified before they grade the real skills.

    `unlabeled` is whether the fence-label rule fires, `heredoc` whether the no-heredoc
    rule does. A usage fence and a placeholder fence must stay silent, a labeled fence
    is the other graders' business, and a here-string is not a heredoc.
    """
    assert bool(_unlabeled_fence_commands(text)) is unlabeled, case
    assert bool(_heredoc_openers(text)) is heredoc, case


def test_j10_case_inventory_matches_this_brief() -> None:
    """The brief's case count is a claim about this file: re-derive it, do not read it.

    Three consecutive passes found this number stale (21 while the table held 25, then
    37, then 41) — a hard-coded count in prose that nothing checks is the defect class
    this PR keeps closing at new sites. Now it is graded, so the brief cannot drift from
    the table without a red test naming both numbers.
    """
    brief = (
        ROOT / "docs" / "specs" / "review-loop-runtime" / "briefs" / "M2-the-loop.md"
    ).read_text()
    for phrase, name in (
        (f"**{len(J10_CASES)}** crafted cases", "J10_CASES"),
        (f"`J10_REACH_CASES` holds {len(J10_REACH_CASES)} cases", "J10_REACH_CASES"),
        (f"`PROSE_CODE` {len(PROSE_CODE)} for", "PROSE_CODE"),
    ):
        assert phrase in brief, (
            f"the brief does not state {name}'s real size: expected {phrase!r}"
        )


def test_skills_contain_no_gh_or_git_commands() -> None:
    for name in ("kbabysit", "kreview"):
        text = (ROOT / "skills" / name / "SKILL.md").read_text()
        found = _shell_invocations(text)
        assert found == [], f"{name}: these are the tool's job now: {found[:5]}"
        unlisted = _unlisted_commands(text)
        assert unlisted == [], (
            f"{name}: a shell fence invokes something outside the allowlist "
            f"(ALLOWED_IN_SHELL_FENCES): {unlisted[:5]} — a rewrite that needs it is "
            "the escape valve, not an edit here"
        )
        # the two graders above read labeled shell fences; code that hides from them
        # (decided 2026-09-20) is a label away, or a heredoc that has no reason to exist
        unlabeled = _unlabeled_fence_commands(text)
        assert unlabeled == [], (
            f"{name}: an unlabeled fence holds a command, which neither grader reads — "
            f"label it ```bash: {unlabeled[:5]}"
        )
        heredocs = _heredoc_openers(text)
        assert heredocs == [], (
            f"{name}: a shell fence opens a heredoc, whose body no grader reads — "
            f"posting and filing are the tool's job: {heredocs[:5]}"
        )
    kbabysit = (ROOT / "skills" / "kbabysit" / "SKILL.md").read_text()
    for sub in ("kreview status", "kreview round", "kreview apply", "kreview report"):
        assert sub in kbabysit
    assert "kselfreview" in kbabysit
    # the fork was dropped 2026-09-14 (it hid the loop); the tier is the session's now,
    # and the preflight check is what the rewrite must keep
    assert "context: fork" not in kbabysit
    assert "MODEL:" in kbabysit
    assert "Never merge" in kbabysit
    # the Surface pins the observer seat too: without this, kobserve can be left on the
    # old report flow and J10 still passes
    kobserve = (ROOT / "skills" / "kobserve" / "SKILL.md").read_text()
    assert "kreview status" in kobserve
