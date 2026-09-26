"""A skill's text survives being invoked with arguments.

When a skill is invoked with arguments, the harness rewrites its body before the model
reads it: every `$` followed by digits becomes that argument (counted from 0, the
arguments split into words), and so does `$ARGUMENTS[N]` — anywhere in the text,
fenced shell and awk included. kbabysit invokes kreview with arguments, and on #92's
babysit kreview's suppressed-findings parser arrived with its awk field tests replaced
by words of kbabysit's sentence: broken awk, from a file that was intact on disk (#89).
The same rewrite turned kbabysit's quoted Copilot prices into its PR number: a price of
five cents read `94.05` on `/kbabysit 94`.

`$ARGUMENTS` on its own is the documented slot and stays allowed; awk's `$NF` is not
rewritten either. The slot is filled verbatim — nothing is quoted for a shell — so in a
fenced block it is shell source, and kbabysit's preflight had it inside a double-quoted
string: backticks or `$(…)` in the arguments ran, and a `"` broke the line. In a fenced
block the slot is allowed only as the body of a quoted heredoc that `read` takes in,
the one place a shell neither expands nor runs text. The one text that still escapes is
a line reading exactly the heredoc's delimiter; no quoting written into the skill can
close that, only keeping the arguments out of shell source altogether.
"""

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KBABYSIT = ROOT / "skills" / "kbabysit" / "SKILL.md"

# The harness's own pattern for positional slots (Claude Code 2.1.283): `$` and digits
# not followed by a word character. It also matches inside `\$1`, on purpose: the
# harness honours that backslash only on its substituting path and returns the text
# untouched, backslash and all, when it has no arguments, so an escaped slot reads
# two ways depending on the invocation.
POSITIONAL = re.compile(r"\$ARGUMENTS\[\d+\]|\$\d+(?!\w)")
SLOT = "$ARGUMENTS"
FENCE = re.compile(r"\s*(`{3,}|~{3,})")
# The one opener the gate accepts, as a whole line: `read` from a heredoc whose
# delimiter is quoted, a trailing comment at most. Searching the line above the slot
# for `<<'WORD'` passed six of the placements in BYPASSES below (PR #98's review).
READ_OPENER = re.compile(r"IFS= read -r [A-Za-z_]\w* <<'(\w+)'(?:\s+#.*|\s*)")


def tracked_skills() -> list[Path]:
    """Every SKILL.md git tracks — untracked WIP in a checkout is not ours."""
    listing = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", "skills/*/SKILL.md"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / name for name in listing.split("\0") if name]


def fenced_blocks(lines: list[str]) -> list[list[int]]:
    """Each fenced block's line indexes, fences left out: the text a model runs."""
    blocks: list[list[int]] = []
    fence = ""
    for index, line in enumerate(lines):
        match = FENCE.match(line)
        mark = match.group(1) if match else ""
        if not fence and mark:
            fence = mark
            blocks.append([])
        elif (
            mark
            and line.strip() == mark
            and mark[0] == fence[0]
            and len(mark) >= len(fence)
        ):
            fence = ""
        elif fence:
            blocks[-1].append(index)
    return blocks


def invoke(text: str, arguments: str | None) -> str:
    """`text` as the harness hands it to the model when invoked with `arguments`.

    Claude Code 2.1.283, read from its skill loader: with no arguments at all the text
    comes back untouched; otherwise every `$ARGUMENTS` becomes the arguments verbatim,
    but for a defused run-on-load marker (`!` then a backtick): a backtick-`!` pair
    gets a space, and a `!` at a line start or after whitespace gains a backslash. One
    load path also turns `<` and `>` into HTML entities, left out here: in the quoted
    heredoc the gate below requires, those are data too. Nothing is quoted for a shell.
    """
    if arguments is None:
        return text
    value = arguments.replace("`!", "` !").replace("!`", "! `")
    value = re.sub(r"(^|\s)!", r"\1\\!", value, flags=re.M)
    return text.replace(SLOT, value)


def preflight() -> str:
    """kbabysit step 0's target block, dedented, as the file carries it."""
    lines = KBABYSIT.read_text().splitlines()
    [block] = [
        rows
        for rows in fenced_blocks(lines)
        if any("TARGET: #" in lines[index] for index in rows)
    ]
    return textwrap.dedent("\n".join(lines[index] for index in block)) + "\n"


# `gh pr view` with no number answers the branch's PR, or fails the way gh does when the
# branch has none; everything else the block asks gets a harmless answer.
FAKE_GH = """#!/bin/sh
case "$1 $2 $3" in
  "pr view --json")
    if [ -n "$BRANCH_PR" ]; then echo "$BRANCH_PR"; exit 0; fi
    echo "no pull requests found for branch" >&2; exit 1 ;;
  "repo view --json") echo "kpiteira/devops-ai" ;;
  *) echo "{}" ;;
esac
"""

# The shells the block meets: the Bash tool runs the user's shell — zsh by default on
# macOS, usually bash on Linux — and macOS's /bin/bash is 3.2.
SHELLS = [
    pytest.param(
        shell,
        marks=pytest.mark.skipif(shutil.which(shell) is None, reason=f"no {shell}"),
    )
    for shell in ("bash", "zsh")
]


def run_preflight(
    arguments: str | None, branch_pr: str, shell: str, tmp_path: Path
) -> list[str]:
    """The TARGET lines the block prints, after checking it ran and ran nothing else."""
    bin_dir, work = tmp_path / "bin", tmp_path / "work"
    bin_dir.mkdir()
    work.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "BRANCH_PR": branch_pr,
    }
    env.pop("ARGUMENTS", None)
    command = [shell, "-f", "-c"] if shell == "zsh" else [shell, "-c"]
    result = subprocess.run(
        [*command, invoke(preflight(), arguments)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    ran = sorted(path.name for path in work.iterdir())
    assert not ran, f"text from the arguments ran as shell and left {ran}"
    assert result.returncode == 0, result.stderr
    return [line for line in result.stdout.splitlines() if line.startswith("TARGET:")]


# Each carries a `touch pwned-…` that only an executed argument can perform.
HOSTILE = {
    # Backticks, as a note quoting a Copilot heading carries them.
    "backticks": "96 note: `touch pwned-backticks` is what Copilot calls it",
    "command-substitution": "96 $(touch pwned-dollar-paren)",
    # An odd count: the double-quoted string on main never closes.
    "double-quote": '96 the "quoted note',
    # Ends a single-quoted slot early, and breaks a heredoc inside $(…) on bash 3.2.
    "apostrophe": "96 it's $(touch pwned-apostrophe)",
    # Escapes the closing quote of a double-quoted slot.
    "trailing-backslash": "96 C:\\",
    # The harness defuses `!` plus a backtick for itself; the backticks are still there.
    "bang-backtick": "96 !`touch pwned-bang`",
    "newline": "96\n$(touch pwned-newline)\n`touch pwned-newline-2`",
    # A later line's number is not the <pr-number>; main read `96` and `42` both.
    "newline-number": "96\n42 is the stacked one",
    # A common delimiter, so a heredoc here must not use it.
    "eof-line": "96\nEOF\ntouch pwned-eof\n)",
}


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("arguments", list(HOSTILE.values()), ids=list(HOSTILE))
def test_hostile_arguments_are_data(arguments: str, shell: str, tmp_path: Path) -> None:
    assert run_preflight(arguments, "96", shell, tmp_path) == ["TARGET: #96"]


NONE = "TARGET: none — no number in the arguments and no PR open for this branch"


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize(
    ("arguments", "branch_pr", "target"),
    [
        ("96", "96", "TARGET: #96"),
        ("#96", "96", "TARGET: #96"),
        ("96 max-rounds: 5", "96", "TARGET: #96"),
        ("42", "96", "TARGET: not this checkout — #42 vs branch PR #96"),
        ("", "96", "TARGET: #96"),
        (None, "96", "TARGET: #96"),
        ("", "", NONE),
        (None, "", NONE),
    ],
    ids=["number", "hash", "max-rounds", "other-pr", "empty", "no-args"]
    + ["none", "none-no-args"],
)
def test_the_target_is_unchanged(
    arguments: str | None, branch_pr: str, target: str, shell: str, tmp_path: Path
) -> None:
    assert run_preflight(arguments, branch_pr, shell, tmp_path) == [target]


def test_the_scan_sees_the_skills() -> None:
    # A glob that matched nothing would make the gate below vacuously green.
    names = {path.parent.name for path in tracked_skills()}
    assert {"kbabysit", "kreview"} <= names


def test_no_skill_carries_a_positional_argument_slot() -> None:
    hits = [
        f"{path.relative_to(ROOT)}:{number}: {match.group()}"
        for path in tracked_skills()
        for number, line in enumerate(path.read_text().splitlines(), 1)
        for match in POSITIONAL.finditer(line)
    ]
    assert not hits, (
        "the harness replaces these with the invocation's arguments before the model "
        "reads the skill — name awk fields with $NF or split(), and write prices "
        "without a dollar sign: " + ", ".join(hits)
    )


def slot_misuses(text: str) -> list[str]:
    """`line: text` for each `$ARGUMENTS` in a fenced block outside the data form.

    The form is three lines at one indentation: the `READ_OPENER` line, the slot alone,
    the delimiter alone. Any other indentation or trailing text on the last two, and a
    shell either does not end the heredoc there or does not read the slot as its body.
    """
    lines = text.splitlines()
    hits = []
    for index in (i for block in fenced_blocks(lines) for i in block):
        if SLOT not in lines[index]:
            continue
        above = lines[index - 1]
        indent = above[: len(above) - len(above.lstrip())]
        opener = READ_OPENER.fullmatch(above.lstrip())
        if not (
            opener
            and lines[index] == indent + SLOT
            and index + 1 < len(lines)
            and lines[index + 1] == indent + opener.group(1)
        ):
            hits.append(f"{index + 1}: {lines[index].strip()}")
    return hits


def fence(*lines: str) -> str:
    return "\n".join(["```bash", *lines, "```"]) + "\n"


BYPASSES = {
    # The slot is shell source: a line of its own, an expanded heredoc, a string, or a
    # comment that a newline in the arguments ends.
    "in-a-comment": fence("# <<'ARGS'", SLOT, "ARGS"),
    "in-a-string": fence("echo \"<<'ARGS'\"", SLOT, "ARGS"),
    "herestring": fence("IFS= read -r L <<<'ARGS'", SLOT, "ARGS"),
    "unquoted-delimiter": fence("IFS= read -r L <<ARGS", SLOT, "ARGS"),
    "double-quoted": fence('ARG_PR=$(printf "%s" "$ARGUMENTS")'),
    "in-a-comment-alone": fence("true  # $ARGUMENTS"),
    # A tab-indented line in the arguments reading ARGS ends the body.
    "tab-stripping": fence("IFS= read -r L <<-'ARGS'", SLOT, "ARGS"),
    # bash 3.2 cannot parse it when the arguments hold an apostrophe.
    "command-substitution": fence("L=$(cat <<'ARGS'", SLOT, "ARGS", ")"),
    # The heredoc does not end where the block says, and swallows the rest of it.
    "glued-hash": fence("IFS= read -r L <<'ARGS'#x", SLOT, "ARGS"),
    "other-delimiter": fence("IFS= read -r L <<'ARGS'", SLOT, "END"),
    "indented-delimiter": fence("IFS= read -r L <<'ARGS'", SLOT, "  ARGS"),
}


@pytest.mark.parametrize("text", list(BYPASSES.values()), ids=list(BYPASSES))
def test_the_gate_sees_every_other_placement(text: str) -> None:
    assert slot_misuses(text), text


def test_the_gate_passes_the_data_form_and_prose() -> None:
    prose = "**Arguments for this run:** `$ARGUMENTS` — in prose, the slot is text.\n"
    top = fence("IFS= read -r ARG_LINE <<'ARGS'      # the first line", SLOT, "ARGS")
    listed = textwrap.indent(fence("IFS= read -r L <<'ARGS'", SLOT, "ARGS"), "  ")
    assert slot_misuses(prose + top + listed) == []


def test_the_slot_reaches_shell_only_as_heredoc_data() -> None:
    hits = [
        f"{path.relative_to(ROOT)}:{hit}"
        for path in tracked_skills()
        for hit in slot_misuses(path.read_text())
    ]
    assert not hits, (
        "the harness pastes the arguments over $ARGUMENTS verbatim, so in a fenced "
        "block it is shell source — put it alone on a line between "
        "`IFS= read -r NAME <<'WORD'` and `WORD`, and nowhere else in the block, "
        "comments included: " + ", ".join(hits)
    )
