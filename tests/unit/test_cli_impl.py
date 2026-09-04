"""Unit tests for CLI impl command (pure functions only)."""

from __future__ import annotations

from pathlib import Path

from devops_ai.cli.impl import (
    _find_milestone_file,
    impl_command,
    parse_feature_milestone,
)


class TestParseFeatureMilestone:
    def test_simple(self) -> None:
        feature, milestone = parse_feature_milestone("wellness-reminders/M1")
        assert feature == "wellness-reminders"
        assert milestone == "M1"

    def test_no_slash(self) -> None:
        """Missing slash → error."""
        try:
            parse_feature_milestone("no-slash")
            raise AssertionError("Should have raised")
        except ValueError as e:
            assert "feature/milestone" in str(e).lower()


class TestFindMilestoneFile:
    def test_v2_brief_layout(self, tmp_path: Path) -> None:
        briefs = tmp_path / "docs" / "specs" / "challenges" / "briefs"
        briefs.mkdir(parents=True)
        brief = briefs / "M1-run-day-one.md"
        brief.write_text("---\nmilestone: M1\n---\n")

        assert _find_milestone_file(tmp_path, "challenges", "M1") == brief
        assert _find_milestone_file(tmp_path, "challenges", "M2") is None

    def test_v1_layout_still_found(self, tmp_path: Path) -> None:
        impl = tmp_path / "docs" / "designs" / "auth" / "implementation"
        impl.mkdir(parents=True)
        ms = impl / "M1_login.md"
        ms.write_text("# M1")

        assert _find_milestone_file(tmp_path, "auth", "M1") == ms

    def test_v2_preferred_over_v1(self, tmp_path: Path) -> None:
        briefs = tmp_path / "docs" / "specs" / "f" / "briefs"
        briefs.mkdir(parents=True)
        (briefs / "M1-x.md").write_text("v2")
        impl = tmp_path / "docs" / "designs" / "f" / "implementation"
        impl.mkdir(parents=True)
        (impl / "M1_x.md").write_text("v1")

        found = _find_milestone_file(tmp_path, "f", "M1")
        assert found is not None and found.read_text() == "v2"

    def test_missing(self, tmp_path: Path) -> None:
        assert _find_milestone_file(tmp_path, "nothing", "M1") is None


class TestMissingBriefMessage:
    def test_names_both_searched_locations(self, tmp_path: Path) -> None:
        """The failure names the v2 brief path and the v1 fallback path."""
        code, message = impl_command(
            "challenges/M1", repo_root=tmp_path, session=False
        )

        assert code == 1
        assert "docs/specs/challenges/briefs/M1-*.md" in message
        assert "docs/designs/challenges/implementation/M1_*.md" in message
