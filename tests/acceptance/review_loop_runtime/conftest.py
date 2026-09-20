"""Acceptance fixtures for the review-loop-runtime feature.

Planner-authored (spec/review-loop-runtime). The surface under test is the `kreview`
console script, exercised for real against the GitHub API from inside a clone of the
repository. Nothing here is mocked.

Read-side fixtures are merged PRs of this repository. Their *commits* are immutable,
but their reviews and issue comments are not — anyone can still comment on a merged PR
— so every assertion on a count or a set of findings passes `--until MEASURED_UNTIL`, a
cutoff after the last measured activity. Without it a stranger's comment on #49 turns
this suite red with the implementation unchanged.

Write-side fixtures are throwaway PRs in the scratch repository named by
KREVIEW_ACCEPTANCE_REPO (spec assumption A2); they skip when it is unset, and
`test_write_side_coverage_is_not_optional` fails rather than skipping so the M2
blocking command cannot go green on skips.
"""

from __future__ import annotations

import json
import os
import secrets as _secrets
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
REPO = "kpiteira/devops-ai"
COPILOT = "copilot-pull-request-reviewer[bot]"  # REST spelling, with the suffix

# --- measured on 2026-09-13 (spec: Discovered context) --------------------------
# Cutoff for every read-side window: #49 merged at 16:12:15Z with its last activity at
# 16:12:13Z, #27 earlier still. Anything posted to either PR after this falls outside
# every window these tests read, so the counts below stay true however the PRs are
# commented on later.
MEASURED_UNTIL = "2026-09-13T17:00:00Z"

PR49 = 49
PR49_HEAD = "06af8a4"
PR49_BOUNDARY = "5a9b106"
PR49_LAST_REVIEWED = "7b2b313"
PR49_COPILOT_REVIEWS = 13
PR49_SUPPRESSED_TOTAL = 15
PR49_THREADS = 4
PR49_ISSUE_COMMENTS = 13  # one of them is the babysit report
PR49_SECOND_ORDER_REVIEW = 5191010581  # 2026-09-13T14:27:15Z, commit 70a8f10
PR49_APPROVAL_REVIEW = 5191024505  # 2026-09-13T14:34:49Z, "Approval recommended"
PR49_FIX_AFTER_SECOND_ORDER = "c121936"
W49_SECOND_ORDER = ("2026-09-13T14:27:00Z", "2026-09-13T14:30:00Z")
W49_APPROVAL = ("2026-09-13T14:34:00Z", "2026-09-13T14:35:00Z")
PR49_THREAD_FINDING = (
    "t3998793921"  # azurekeyvault.py:162 at 23ee88a, resolved+outdated
)

PR27 = 27
PR27_BOUNDARY = "84197e4"
W27_FIRST = (None, "2026-09-12T15:09:00Z")  # the first review only
W27_SIXTH = ("2026-09-12T16:13:00Z", "2026-09-12T16:14:00Z")  # review 5187077449
PR27_SIXTH_ORIGINAL = ("skills/kworktree/SKILL.md", 136)  # blames to ed2338dd

PR10 = 10  # merged before the review-scope rule: no `## Review scope`

# --- measured on 2026-09-20: Copilot's two body formats, both on this spec's own PR --
# #66 is this feature's spec PR. Its round-4 review is the last v1 body on this
# repository and its round-5 review the first v2 one, so the two windows below freeze
# one of each; both are read with --include-resolved, since the rounds that answered
# them resolved their threads.
PR66 = 66
PR66_V1_BALANCED_REVIEW = 5194046823  # 2026-09-14T04:52:59Z, commit 5c4c5cb, v1
PR66_V2_REVIEW = 5260930892  # 2026-09-20T15:24:46Z, commit f07e9c0, v2 marker
W66_V1_BALANCED = ("2026-09-14T04:52:00Z", "2026-09-14T04:53:00Z")
W66_V2 = ("2026-09-20T15:24:00Z", "2026-09-20T15:25:00Z")
# closed without merging, and scope-less: grades `closed` ahead of `scope-missing`
PR19 = 19


@dataclass
class Result:
    code: int
    out: str
    err: str

    def json(self) -> Any:
        return json.loads(self.out)


def kreview(
    *args: str,
    cwd: Path | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> Result:
    """Run the real `kreview` console script via uv, from `cwd` (default: repo root)."""
    proc = subprocess.run(
        ["uv", "run", "--project", str(ROOT), "kreview", *args],
        cwd=cwd or ROOT,
        env=env if env is not None else os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return Result(proc.returncode, proc.stdout, proc.stderr)


def window_args(window: tuple[str | None, str | None]) -> list[str]:
    since, until = window
    args: list[str] = []
    if since:
        args += ["--since", since]
    if until:
        args += ["--until", until]
    return args


def gh(*args: str, timeout: int = 120) -> str:
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, timeout=timeout, check=True
    )
    return proc.stdout


def gh_json(*args: str) -> Any:
    return json.loads(gh(*args))


def authenticated_login() -> str:
    """The login `gh` acts as — the reviewer the free write-side tests stand in for."""
    return gh("api", "user", "--jq", ".login").strip()


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def findings_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["id"]: f for f in packet["findings"]}


# ------------------------------------------------------------ scratch repository


@dataclass
class ScratchPR:
    """A throwaway PR in the scratch repository, opened by the test that owns it."""

    repo: str
    number: int
    clone: Path
    branch: str
    path: str  # the one file the PR adds
    tag: str
    issues: list[int] = field(default_factory=list)

    @property
    def head(self) -> str:
        return git("rev-parse", "HEAD", cwd=self.clone)

    def comment(self, line: int, body: str) -> int:
        """Post a review comment on `line` of the PR's file (authenticated user)."""
        out = gh_json(
            "api",
            f"repos/{self.repo}/pulls/{self.number}/comments",
            "-f",
            f"body={body}",
            "-f",
            f"commit_id={self.head}",
            "-f",
            f"path={self.path}",
            "-F",
            f"line={line}",
            "-f",
            "side=RIGHT",
        )
        return int(out["id"])

    def review(self, body: str) -> int:
        """Submit a COMMENT review carrying `body` (authenticated user, free).

        A PR's own author can submit a COMMENT review on it — measured against the
        scratch repository on 2026-09-13; only *approving* one's own PR is refused.
        This is how a review body carrying a `Suppressed comments` section is produced
        without buying a Copilot review.
        """
        out = gh_json(
            "api",
            f"repos/{self.repo}/pulls/{self.number}/reviews",
            "-f",
            "event=COMMENT",
            "-f",
            f"body={body}",
        )
        return int(out["id"])

    def rewrite_head(self, text: str) -> str:
        """Amend the branch tip and force-push: the reviewed commit leaves history.

        This is how the `unknown` provenance state is produced: every earlier review's
        commit is still served by GitHub but is no longer an ancestor of the head, so
        no boundary is reachable.
        """
        file = self.clone / self.path
        file.write_text(file.read_text() + text + "\n")
        git("add", self.path, cwd=self.clone)
        git("commit", "-q", "--amend", "--no-edit", cwd=self.clone)
        git("push", "-q", "--force", "origin", self.branch, cwd=self.clone)
        return self.head

    def issue_comment(self, body: str) -> int:
        out = gh_json(
            "api",
            f"repos/{self.repo}/issues/{self.number}/comments",
            "-f",
            f"body={body}",
        )
        return int(out["id"])

    def threads(self) -> list[dict[str, Any]]:
        owner, name = self.repo.split("/")
        data = gh_json(
            "api",
            "graphql",
            "-f",
            "query=query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r)"
            "{pullRequest(number:$n){reviewThreads(first:100){nodes{id isResolved "
            "comments(first:20){nodes{databaseId author{login} body url}}}}}}}",
            "-f",
            f"o={owner}",
            "-f",
            f"r={name}",
            "-F",
            f"n={self.number}",
        )
        nodes = data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
        return [
            {
                "id": t["id"],
                "resolved": t["isResolved"],
                "first_id": t["comments"]["nodes"][0]["databaseId"],
                "comments": [
                    {"author": c["author"]["login"], "body": c["body"], "url": c["url"]}
                    for c in t["comments"]["nodes"]
                ],
            }
            for t in nodes
        ]

    def thread_of(self, comment_id: int) -> dict[str, Any]:
        return next(t for t in self.threads() if t["first_id"] == comment_id)

    def issue_comments(self) -> list[dict[str, Any]]:
        return gh_json(
            "api", "--paginate", f"repos/{self.repo}/issues/{self.number}/comments"
        )

    def babysit_comment(self) -> str | None:
        for c in self.issue_comments():
            if c["body"].startswith("## Babysit report"):
                return str(c["body"])
        return None

    def state(self) -> dict[str, Any]:
        """The `kreview-state` JSON block at the end of the babysit comment."""
        body = self.babysit_comment()
        assert body is not None, "no babysit report comment on this PR"
        _, _, tail = body.partition("<!-- kreview-state")
        assert tail, "the babysit comment carries no state block"
        return dict(json.loads(tail.rsplit("-->", 1)[0]))

    def push_fix(self, text: str) -> str:
        """Append a line to the PR's file, commit, push; return the new head sha."""
        file = self.clone / self.path
        file.write_text(file.read_text() + text + "\n")
        git("add", self.path, cwd=self.clone)
        git("commit", "-q", "-m", f"fix: {text}", cwd=self.clone)
        git("push", "-q", "origin", self.branch, cwd=self.clone)
        return self.head

    def find_issues(self) -> list[dict[str, Any]]:
        return gh_json(
            "issue",
            "list",
            "--repo",
            self.repo,
            "--state",
            "all",
            "--search",
            f"kreview-acceptance {self.tag} in:title",
            "--json",
            "number,title,body",
        )


def _scratch_repo() -> str:
    repo = os.environ.get("KREVIEW_ACCEPTANCE_REPO")
    if not repo:
        pytest.skip("KREVIEW_ACCEPTANCE_REPO is not set (spec assumption A2)")
    return repo


FAILING_WORKFLOW = """\
name: kreview-acceptance-fail
on: [pull_request]
jobs:
  fail:
    runs-on: ubuntu-latest
    steps:
      - run: exit 1
"""

DEFAULT_SCOPE = "- the file `{path}` exists with twenty numbered lines\n"


def open_scratch_pr(
    tmp_path: Path,
    *,
    draft: bool = False,
    scope: str | None = DEFAULT_SCOPE,
    failing_workflow: bool = False,
) -> ScratchPR:
    """Open a scratch-repository PR: a twenty-line file and, by default, a review scope.

    `scope=None` omits the `## Review scope` heading; `scope=""` writes the heading
    with nothing under it. `failing_workflow=True` commits a workflow on the PR branch
    whose only job exits 1, so the PR's head gets a failing check.
    """
    repo = _scratch_repo()
    clone = tmp_path / f"scratch-{_secrets.token_hex(2)}"
    gh("repo", "clone", repo, str(clone), "--", "-q")
    base = git("rev-parse", "--abbrev-ref", "HEAD", cwd=clone)
    tag = _secrets.token_hex(4)
    branch = f"kreview-acc/{tag}"
    path = f"acc/{tag}.txt"
    git("checkout", "-q", "-b", branch, cwd=clone)
    (clone / "acc").mkdir(exist_ok=True)
    (clone / path).write_text("".join(f"line {i}\n" for i in range(1, 21)))
    git("add", path, cwd=clone)
    if failing_workflow:
        wf = clone / ".github" / "workflows" / "kreview-acceptance-fail.yml"
        wf.parent.mkdir(parents=True, exist_ok=True)
        wf.write_text(FAILING_WORKFLOW)
        git("add", str(wf.relative_to(clone)), cwd=clone)
    git("commit", "-q", "-m", f"acceptance: {tag}", cwd=clone)
    git("push", "-q", "-u", "origin", branch, cwd=clone)
    body = "Scratch PR opened by the review-loop-runtime acceptance tests.\n"
    if scope is not None:
        body += "\n## Review scope\n\n" + scope.format(path=path)
    args = [
        "pr",
        "create",
        "--repo",
        repo,
        "--head",
        branch,
        "--base",
        base,
        "--title",
        f"kreview-acceptance {tag}",
        "--body",
        body,
    ]
    if draft:
        args.append("--draft")
    url = gh(*args).strip()
    number = int(url.rstrip("/").rsplit("/", 1)[-1])
    return ScratchPR(
        repo=repo, number=number, clone=clone, branch=branch, path=path, tag=tag
    )


def close_scratch_pr(pr: ScratchPR) -> None:
    subprocess.run(
        ["gh", "pr", "close", str(pr.number), "--repo", pr.repo, "--delete-branch"],
        capture_output=True,
        text=True,
    )
    for issue in pr.find_issues():
        subprocess.run(
            ["gh", "issue", "close", str(issue["number"]), "--repo", pr.repo],
            capture_output=True,
            text=True,
        )


@pytest.fixture()
def scratch(tmp_path: Path) -> Iterator[ScratchPR]:
    """A fresh scratch-repository PR: a twenty-line file and a review scope."""
    pr = open_scratch_pr(tmp_path)
    try:
        yield pr
    finally:
        close_scratch_pr(pr)


@pytest.fixture()
def scratch_factory(tmp_path: Path) -> Iterator[Callable[..., ScratchPR]]:
    """Open scratch PRs in other states (draft, scope-less, red CI); closed after."""
    opened: list[ScratchPR] = []

    def _open(**options: Any) -> ScratchPR:
        pr = open_scratch_pr(tmp_path, **options)
        opened.append(pr)
        return pr

    try:
        yield _open
    finally:
        for pr in opened:
            close_scratch_pr(pr)


def dispositions_file(tmp_path: Path, *items: dict[str, Any], note: str = "") -> Path:
    f = tmp_path / "dispositions.json"
    f.write_text(json.dumps({"round_note": note, "dispositions": list(items)}))
    return f
