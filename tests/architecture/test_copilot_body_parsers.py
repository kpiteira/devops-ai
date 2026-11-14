"""The Copilot review-body parsers in kreview and kbabysit, run as the skills ship them.

The parsers live in skill prose, so nothing executed them. From 2026-09-20 Copilot
served v2 bodies; kreview's suppressed-findings parser and its guard agreed at 0 = 0
on every one, and #66's review 5261175937 carried seven findings its babysit reported
as none (#89). kbabysit's effort grep read nothing off the same bodies, three babysits
running. From 2026-10-17 the v2 headings put their count first and dropped the
`(N)` (`1 previously missed issue`), and the effort moved into a `<sub>` footer: the
parser and the `(N)` guard agreed at 0 = 0 again, and homelab#92's review 5898789029
carried a finding only a hand read caught (#86, #87).

These tests take the bash blocks out of the skills **verbatim** and run them against
real review bodies (`fixtures/copilot_reviews.json`, as the REST API served them,
U+200B and CR included), with a stand-in `gh` on PATH that answers `--jq` from the
fixture. A skill edit that stops reading a format, counts a thread list as findings,
makes the guard share the parser's blind spot, or lets a heading the guard cannot
read count as zero goes red here instead of in the next babysit.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "copilot_reviews.json"
KREVIEW = ROOT / "skills" / "kreview" / "SKILL.md"
KBABYSIT = ROOT / "skills" / "kbabysit" / "SKILL.md"

# `gh api [--paginate] <endpoint> --jq <filter>` answered from the fixture file. Real
# `gh --jq` prints strings raw, which is `jq -r`.
FAKE_GH = """#!/bin/sh
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--jq" ]; then filter="$2"; shift; fi
  shift
done
exec jq -r "$filter" "$FIXTURE"
"""

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None,
    reason="the stand-in gh needs jq, which `gh --jq` embeds",
)

# Real reviews, by id. `(N)` is the heading's declared count.
V1_ONE = 5194046823  # #66: Suppressed comments (1), a fenced snippet after it
V1_FIVE = 5190978594  # #51: Suppressed comments (5), reviewed at Lite
V2_MISSED_7 = 5261175937  # #66: Previously missed (7) beside Open (3), Resolved (6)
V2_NONE_3 = 5262627194  # #85: `Findings: None` and Previously missed (3)
V2_OPEN_9 = 5327351542  # #93: Open (9), a What changed table with U+200B and CR
LEGACY_1 = 3800891523  # #12, February: Comments suppressed due to low confidence (1)
# Count-first v2 headings, served since 2026-10-17 (#86), with a <sub> effort footer
# (#87).
NEW_MISSED_1 = 5898789029  # homelab#92: 1 previously missed issue, 3 resolved since...
NEW_MISSED_1B = 5566361383  # devops-ai#100: the same, beside **No open issues**
NEW_MISSED_3 = 5815796437  # homelab#85: 3 previously missed issues, 3 resolved since...
NEW_OPEN_3 = 5815694172  # homelab#85: 3 open issues, 7 resolved since last review
NEW_CHANGED = 5899998505  # homelab#98: What changed in this PR, and nothing else

FETCH = "**Fetch once, into a file, and check that the fetch worked**"
EFFORT_ROUND = "**Record this round's effort level here**"
EFFORT_SO_FAR = "level read here could only ever describe somebody else's round:"

Served = dict | list[dict]


def bash_block(skill: Path, after: str) -> str:
    """The first fenced bash block after `after`, dedented: the text the model runs."""
    rest = skill.read_text().split(after, 1)[1]
    match = re.search(r"^( *)(`{3,4})bash\n(.*?)^\1\2$", rest, re.S | re.M)
    assert match, f"no bash block after {after!r} in {skill.name}"
    return textwrap.dedent(match.group(3))


def reviews(*ids: int) -> list[dict]:
    by_id = {review["id"]: review for review in json.loads(FIXTURE.read_text())}
    return [by_id[i] for i in ids]


def mutated(review_id: int, old: str, new: str) -> list[dict]:
    review = dict(reviews(review_id)[0])
    assert old in review["body"], old
    review["body"] = review["body"].replace(old, new)
    return [review]


def run(block: str, served: Served, tmp_path: Path) -> str:
    """Run a skill block with `gh` answering from `served`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    data = tmp_path / "served.json"
    data.write_text(json.dumps(served))
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FIXTURE": str(data),
        "REPO": "kpiteira/devops-ai",
        "PR_NUMBER": "0",
        "REVIEW_ID": "0",
    }
    result = subprocess.run(
        ["bash", "-c", block], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


COUNTS = ("parsed", "declared", "unknown formats", "unreadable headings")


def parse(served: list[dict], tmp_path: Path) -> tuple[list[list[str]], dict]:
    """kreview step 1's block: the rows it printed, and its four counts."""
    lines = run(bash_block(KREVIEW, FETCH), served, tmp_path).splitlines()
    counts = {
        key: int(line.split(":", 1)[1])
        for line in lines
        for key in COUNTS
        if line.startswith(f"{key}:")
    }
    assert set(counts) == set(COUNTS), lines
    rows = [line.split("\t") for line in lines if line.count("\t") == 4]
    return rows, counts


def clean(parsed: int, declared: int, unknown: int = 0, unreadable: int = 0) -> dict:
    return {
        "parsed": parsed,
        "declared": declared,
        "unknown formats": unknown,
        "unreadable headings": unreadable,
    }


def reads_clean(counts: dict) -> bool:
    """The skill's rule for a round it may trust: parsed = declared, nothing unknown."""
    return (
        counts["parsed"] == counts["declared"]
        and counts["unknown formats"] == 0
        and counts["unreadable headings"] == 0
    )


@pytest.mark.parametrize(
    ("review_id", "found"),
    [
        (V1_ONE, 1),
        (V1_FIVE, 5),
        (V2_MISSED_7, 7),
        (V2_NONE_3, 3),
        (V2_OPEN_9, 0),
        (NEW_MISSED_1, 1),
        (NEW_MISSED_1B, 1),
        (NEW_MISSED_3, 3),
        (NEW_OPEN_3, 0),
        (NEW_CHANGED, 0),
    ],
)
def test_suppressed_findings_are_read_in_every_format(
    review_id: int, found: int, tmp_path: Path
) -> None:
    rows, counts = parse(reviews(review_id), tmp_path)
    assert counts == clean(found, found)
    assert len(rows) == found
    for submitted_at, rid, sha, path, line in rows:
        assert rid == str(review_id)
        assert re.fullmatch(r"[0-9a-f]{40}", sha)
        assert submitted_at.startswith("2026-")
        # A path git can blame: no zero-width space, no CR, a real line number.
        assert path.isascii() and path.isprintable() and "/" in path
        assert line.isdigit()


def test_the_v2_rows_are_the_findings_the_body_names(tmp_path: Path) -> None:
    rows, _ = parse(reviews(V2_MISSED_7), tmp_path)
    briefs = "docs/specs/review-loop-runtime/briefs"
    assert [f"{path}:{line}" for *_, path, line in rows] == [
        f"{briefs}/M1-read-side.md:50",
        f"{briefs}/M2-the-loop.md:72",
        f"{briefs}/M2-the-loop.md:75",
        f"{briefs}/M2-the-loop.md:167",
        f"{briefs}/M2-the-loop.md:172",
        "tests/acceptance/review_loop_runtime/test_m2_the_loop.py:1727",
        f"{briefs}/M1-read-side.md:267",
    ]


def test_the_count_first_rows_are_the_findings_the_bodies_name(tmp_path: Path) -> None:
    """homelab#92's one finding is the ADR-023 claim a hand read caught (#86)."""
    rows, _ = parse(reviews(NEW_MISSED_1, NEW_MISSED_1B, NEW_MISSED_3), tmp_path)
    fleet = "tests/acceptance/fleet-updates"
    assert [f"{path}:{line}" for *_, path, line in rows] == [
        "docs/architecture/power-and-ups.md:169",
        "skills/kbabysit/SKILL.md:152",
        f"{fleet}/test_m1_2_deadman_fires.sh:77",
        f"{fleet}/test_m1_2_deadman_fires.sh:87",
        f"{fleet}/test_m1_3_one_phone_setting.sh:35",
    ]


def test_a_heading_the_parser_does_not_read_is_declared_anyway(
    tmp_path: Path,
) -> None:
    """#12's February spelling is the live case: the guard fires, not 0 = 0."""
    _, counts = parse(reviews(LEGACY_1), tmp_path)
    assert counts == clean(0, 1)


def test_every_review_is_read_from_one_file(tmp_path: Path) -> None:
    served = reviews(
        V1_ONE,
        V1_FIVE,
        V2_MISSED_7,
        V2_NONE_3,
        V2_OPEN_9,
        NEW_MISSED_1,
        NEW_MISSED_1B,
        NEW_MISSED_3,
        NEW_OPEN_3,
        NEW_CHANGED,
    )
    rows, counts = parse(served, tmp_path)
    assert counts == clean(21, 21)
    assert {row[1] for row in rows} == {
        str(V1_ONE),
        str(V1_FIVE),
        str(V2_MISSED_7),
        str(V2_NONE_3),
        str(NEW_MISSED_1),
        str(NEW_MISSED_1B),
        str(NEW_MISSED_3),
    }


DRIFT: list[tuple[str, Callable[[], list[dict]], dict]] = [
    (
        "v2 section renamed",
        lambda: mutated(V2_MISSED_7, "Previously missed (7)", "Missed earlier (7)"),
        clean(0, 7),
    ),
    (
        "v2 heading tag changed",
        lambda: mutated(
            V2_MISSED_7,
            "<strong>Previously missed (7)</strong>",
            "<b>Previously missed (7)</b>",
        ),
        clean(0, 7),
    ),
    (
        "v2 heading count dropped",
        lambda: mutated(V2_MISSED_7, "Previously missed (7)", "Previously missed"),
        clean(7, 0, unreadable=1),
    ),
    (
        "v1 section renamed",
        lambda: mutated(
            V1_FIVE, "### Suppressed comments (5)", "### Hidden comments (5)"
        ),
        clean(0, 5),
    ),
    (
        "new overview format",
        lambda: mutated(V2_MISSED_7, "ccr-overview-v2", "ccr-overview-v3"),
        clean(7, 7, unknown=1),
    ),
    # #86's mutation: the count-first heading, renamed or reshaped. The old guard, which
    # summed `(N)` alone, read every one of these as 0 = 0.
    (
        "count-first section renamed",
        lambda: mutated(
            NEW_MISSED_1, "1 previously missed issue", "1 overlooked issue"
        ),
        clean(0, 1),
    ),
    (
        "count-first section renamed, count gone",
        lambda: mutated(
            NEW_MISSED_1, "1 previously missed issue", "Overlooked earlier"
        ),
        clean(0, 0, unreadable=1),
    ),
    (
        "count-first heading count dropped",
        lambda: mutated(
            NEW_MISSED_1, "1 previously missed issue", "Previously missed issue"
        ),
        clean(1, 0, unreadable=1),
    ),
    (
        "count-first heading count spelled out",
        lambda: mutated(
            NEW_MISSED_1, "1 previously missed issue", "One previously missed issue"
        ),
        clean(0, 0, unreadable=1),
    ),
    (
        "count-first heading tag changed",
        lambda: mutated(
            NEW_MISSED_1,
            "<strong>1 previously missed issue</strong>",
            "<b>1 previously missed issue</b>",
        ),
        clean(0, 1),
    ),
    (
        "count-first heading tag grew an attribute",
        lambda: mutated(
            NEW_MISSED_1,
            "<strong>1 previously missed issue",
            '<strong class="ccr">1 previously missed issue',
        ),
        clean(0, 1),
    ),
    (
        "count-first heading split across lines",
        lambda: mutated(
            NEW_MISSED_1,
            "<summary><strong>1 previously missed issue</strong></summary>",
            "<summary>\n<strong>1 previously missed issue</strong>\n</summary>",
        ),
        clean(0, 0, unreadable=1),
    ),
    (
        "count-first plural section renamed",
        lambda: mutated(NEW_MISSED_3, "3 previously missed issues", "3 earlier issues"),
        clean(0, 3),
    ),
    (
        "count-first thread list renamed",
        lambda: mutated(NEW_OPEN_3, "3 open issues", "3 new issues"),
        clean(0, 3),
    ),
]


@pytest.mark.parametrize(
    ("served", "expected"),
    [pytest.param(served, expected, id=what) for what, served, expected in DRIFT],
)
def test_the_guard_notices_the_format_moving(
    served: Callable[[], list[dict]], expected: dict, tmp_path: Path
) -> None:
    """Drifts GitHub could ship. None may read as a round the skill trusts."""
    _, counts = parse(served(), tmp_path)
    assert counts == expected
    assert not reads_clean(counts)


def test_the_unrenamed_bodies_read_clean(tmp_path: Path) -> None:
    """The control for the drifts above: each fixture they mutate, as served."""
    for review_id in (V2_MISSED_7, V1_FIVE, NEW_MISSED_1, NEW_MISSED_3, NEW_OPEN_3):
        _, counts = parse(reviews(review_id), tmp_path)
        assert reads_clean(counts), (review_id, counts)


def test_a_finding_title_that_says_missed_is_not_a_heading(tmp_path: Path) -> None:
    """A finding's <summary> carries a severity <picture>; its title is free text."""
    title = "Scope claim to standing hypervisor-root access"
    served = mutated(NEW_MISSED_1, title, "Previously missed (2) retries are dropped")
    rows, counts = parse(served, tmp_path)
    assert counts == clean(1, 1)
    assert len(rows) == 1


def test_a_path_line_quoted_in_a_snippet_is_not_a_finding(tmp_path: Path) -> None:
    served = mutated(
        V1_ONE,
        "```\n- `kbabysit` keeps",
        "```\n**src/quoted.py:1**\n- `kbabysit` keeps",
    )
    rows, counts = parse(served, tmp_path)
    assert counts == clean(1, 1)
    assert [row[3] for row in rows] == ["docs/specs/review-loop-runtime/SPEC.md"]


def test_a_path_line_cited_in_a_finding_body_is_not_another_finding(
    tmp_path: Path,
) -> None:
    """One `path:line` per finding: the first after its <summary>, not every one."""
    # The first finding cites kreview inline; move the citation to a line of its
    # own, shaped exactly like a finding's path line, U+200B and all.
    inline = "(`skills/kreview/SKILL.md:182`)."
    own_line = "(below).\n\n`skills/\u200bkreview/\u200bSKILL.md:182`\n"
    served = mutated(V2_MISSED_7, inline, own_line)
    _, counts = parse(served, tmp_path)
    assert counts == clean(7, 7)


def test_a_body_with_crlf_line_ends_reads_the_same(tmp_path: Path) -> None:
    """v2 tables already carry CR; a body that is CRLF throughout must not go blind."""
    [review] = reviews(V2_MISSED_7)
    crlf = [dict(review, body=review["body"].replace("\n", "\r\n"))]
    rows, counts = parse(crlf, tmp_path)
    assert counts == clean(7, 7)
    assert all(row[4].isdigit() for row in rows)


def effort(served: Served, tmp_path: Path) -> list[str]:
    return run(bash_block(KBABYSIT, EFFORT_ROUND), served, tmp_path).split()


@pytest.mark.parametrize(
    "review_id", [V1_ONE, V2_MISSED_7, V2_OPEN_9, NEW_MISSED_1, NEW_CHANGED]
)
def test_the_round_effort_level_is_read_in_every_spelling(
    review_id: int, tmp_path: Path
) -> None:
    [review] = reviews(review_id)
    assert effort(review, tmp_path) == ["Balanced"]


@pytest.mark.parametrize(
    ("review_id", "quote"),
    [
        (V2_NONE_3, "Parsed from `**Review effort level:** X` footers, per the brief."),
        (NEW_MISSED_1, "Parsed from `<sub>Review effort: X</sub>` footers."),
    ],
)
def test_a_quoted_effort_line_is_not_the_effort_line(
    review_id: int, quote: str, tmp_path: Path
) -> None:
    """#66's review 5192489979 quoted the footer in a finding; a loose grep read X."""
    intro = "In code that hasn't changed since last review"
    [review] = mutated(review_id, intro, f"{intro}\n\n{quote}")
    assert effort(review, tmp_path) == ["Balanced"]


@pytest.mark.parametrize("balanced", [V2_MISSED_7, NEW_MISSED_1])
def test_the_levels_so_far_cover_every_spelling(balanced: int, tmp_path: Path) -> None:
    # Balanced comes only from the v2 body: a v1 Balanced here would mask a v2 miss.
    served = reviews(V1_FIVE, balanced, LEGACY_1)
    block = bash_block(KBABYSIT, EFFORT_SO_FAR)
    lines = run(block, served, tmp_path).splitlines()
    assert lines[0] == "copilot reviews so far: 3"
    # #51 was reviewed at Lite (v1), the other at Balanced (v2); #12 predates the line.
    assert lines[1].split() == ["Balanced", "Lite"]
