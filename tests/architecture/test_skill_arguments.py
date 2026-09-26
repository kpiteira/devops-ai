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
rewritten either.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The harness's own pattern for positional slots (Claude Code 2.1.283): `$` and digits
# not followed by a word character. It also matches inside `\$1`, on purpose: the
# harness honours that backslash only on its substituting path and returns the text
# untouched, backslash and all, when it has no arguments, so an escaped slot reads
# two ways depending on the invocation.
POSITIONAL = re.compile(r"\$ARGUMENTS\[\d+\]|\$\d+(?!\w)")


def tracked_skills() -> list[Path]:
    """Every SKILL.md git tracks — untracked WIP in a checkout is not ours."""
    listing = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", "skills/*/SKILL.md"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / name for name in listing.split("\0") if name]


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
