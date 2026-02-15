"""Unit tests for CLI impl command (pure functions only)."""

from __future__ import annotations

from devops_ai.cli.impl import parse_feature_milestone


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
