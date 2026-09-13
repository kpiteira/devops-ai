"""Authoring hygiene for tracked markdown: no tool-artifact tag lines at EOF.

Nine tracked files carried a trailing tool-artifact tag for weeks (#46), one of
them under `rules/`, which loads into every session's context — so agents read a
tool artifact as part of a rule. #48 deleted them; this gate stops the next
authoring tool from leaving another (#54).

Scope is deliberately narrow: only the *last* non-empty line of a file. Inline
HTML anywhere else in a document is legitimate markdown and is not touched.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# A whole line that is nothing but an XML/HTML-shaped tag, open or closing.
TAG_LINE = re.compile(r"^</?[A-Za-z_][A-Za-z0-9_-]*>$")

# Tag literals in this file are assembled from pieces rather than spelled out:
# a bare tag line in the source is exactly the artifact that made some authoring
# tools truncate their own output, and these tests would become the next report.
_OPEN = "<"
_CLOSE = "</"


def offending_last_line(text: str) -> str | None:
    """The document's last non-empty line if it is a bare tag, else None."""
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        return stripped if TAG_LINE.match(stripped) else None
    return None


def tracked_markdown(root: Path) -> list[str]:
    """Every markdown path git tracks — untracked WIP in a checkout is not ours."""
    listing = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", "*.md"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [name for name in listing.split("\0") if name]


def scan(root: Path) -> tuple[list[str], list[str]]:
    """(tracked markdown paths, one description per offender among them)."""
    paths = tracked_markdown(root)
    offenders = []
    for name in paths:
        path = root / name
        if not path.is_file():  # tracked but deleted in the working tree
            continue
        found = offending_last_line(path.read_text(encoding="utf-8", errors="replace"))
        if found is not None:
            offenders.append(f"{name} (last line: {found})")
    return paths, offenders


def enforce(root: Path) -> None:
    """The gate itself. Raises AssertionError naming every offender it found."""
    paths, offenders = scan(root)
    assert paths, "no tracked markdown found — the gate would be vacuously green"
    assert not offenders, (
        "tracked markdown ending in a bare tag line — almost always a tool "
        "artifact, not content. Delete the line:\n  " + "\n  ".join(offenders)
    )


def test_no_tracked_markdown_ends_with_a_tool_artifact_tag() -> None:
    enforce(ROOT)


def test_gate_flags_artifact_tags() -> None:
    artifacts = (
        f"# Doc\n\nReal prose.\n{_CLOSE}content>\n",
        f"# Doc\n\nReal prose.\n{_CLOSE}invoke>\n",
        f"# Doc\n\nReal prose.\n{_OPEN}parameter>\n",
        f"# Doc\n\nReal prose.\n{_CLOSE}content>\n\n\n",  # trailing blank lines
        f"# Doc\n\nReal prose.\n  {_CLOSE}content>  \n",  # surrounding whitespace
        f"# Doc\n\nReal prose.\n{_CLOSE}my-tag_2>\n",
    )
    missed = [text for text in artifacts if offending_last_line(text) is None]
    assert not missed, missed


def test_gate_leaves_real_documents_alone() -> None:
    documents = (
        "# Doc\n\nA closing sentence of ordinary prose.\n",
        "",
        "\n\n",
        # inline HTML *elsewhere* in the file is legitimate markdown
        f"# Doc\n\n{_OPEN}details>\n{_OPEN}summary>More{_CLOSE}summary>\n"
        f"hidden\n{_CLOSE}details>\n\nAnd then a real closing sentence.\n",
        # tag-shaped text that is not the whole line
        f"# Doc\n\nUse a {_OPEN}br> to break the line.\n",
        f"# Doc\n\n`{_CLOSE}content>` is what the gate hunts for.\n",
        # a fenced block's terminator, not a tag
        "# Doc\n\n```\nsome code\n```\n",
    )
    tripped = [text for text in documents if offending_last_line(text) is not None]
    assert not tripped, tripped


def test_selection_scans_tracked_files_only(tmp_path: Path) -> None:
    """The pathspec half of the gate, falsifiable without dirtying this checkout.

    Without this, a regression in `tracked_markdown` — a wrong pathspec, a walk
    that picks up untracked files — would leave the gate green, because the real
    corpus it scans is clean either way.
    """
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    artifact = "# Doc\n\nprose\n" + _CLOSE + "content>\n"

    (tmp_path / "tracked-offender.md").write_text(artifact)
    (tmp_path / "tracked-clean.md").write_text("# Doc\n\nordinary prose.\n")
    (tmp_path / "tracked-gone.md").write_text("# Doc\n\nprose\n")
    (tmp_path / "not-markdown.txt").write_text(artifact)
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "tracked-offender.md",
         "tracked-clean.md", "tracked-gone.md", "not-markdown.txt"],
        check=True,
    )
    (tmp_path / "tracked-gone.md").unlink()  # tracked, deleted in the tree
    (tmp_path / "untracked-offender.md").write_text(artifact)

    paths, offenders = scan(tmp_path)

    assert sorted(paths) == [
        "tracked-clean.md",
        "tracked-gone.md",
        "tracked-offender.md",
    ]
    assert offenders == [f"tracked-offender.md (last line: {_CLOSE}content>)"]

    # and the gate itself goes red, naming the tracked offender and only it
    with pytest.raises(AssertionError) as failure:
        enforce(tmp_path)
    assert "tracked-offender.md" in str(failure.value)
    assert "untracked-offender.md" not in str(failure.value)


def test_an_empty_corpus_is_not_a_pass(tmp_path: Path) -> None:
    """A gate that scans nothing must go red, not green.

    Silently passing over an empty set is the failure this gate exists to
    prevent. This exercises `enforce` itself, so deleting the guard turns it
    red — asserting a copy of the guard here would not.
    """
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "notes.txt").write_text("not markdown\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "notes.txt"], check=True)

    assert scan(tmp_path) == ([], []), "fixture should hold no tracked markdown"
    with pytest.raises(AssertionError, match="vacuously green"):
        enforce(tmp_path)
