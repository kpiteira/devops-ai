"""Tests for quality infrastructure detection and artifact generation."""

from pathlib import Path

from devops_ai.cli.quality import (
    QualityPlan,
    detect_quality_config,
    generate_ci_workflow,
    generate_claude_hooks,
    generate_justfile,
    generate_makefile,
    generate_pre_commit_hook,
    generate_review_workflow,
    generate_security_workflow,
)

# --- Detection ---


class TestDetectQualityConfig:
    def test_python_project_from_project_md(self, tmp_path: Path) -> None:
        """Detects Python project config from .devops-ai/project.md."""
        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "project.md").write_text(
            "## Project\n\n"
            "- **Name:** myapp\n"
            "- **Language:** Python\n"
            "- **Runner:** uv\n\n"
            "## Testing\n\n"
            "- **Unit tests:** uv run pytest tests/unit\n"
            "- **Quality checks:** uv run ruff check src/ tests/ && uv run mypy src/\n"
        )

        plan = detect_quality_config(tmp_path)

        assert plan is not None
        assert plan.project_name == "myapp"
        assert plan.language == "python"
        assert plan.runner == "uv"
        assert plan.test_unit_cmd == "uv run pytest tests/unit"
        assert plan.quality_cmd == "uv run ruff check src/ tests/ && uv run mypy src/"

    def test_derives_lint_cmd_from_quality(self, tmp_path: Path) -> None:
        """Derives fast lint (ruff only) from full quality command."""
        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "project.md").write_text(
            "## Project\n\n"
            "- **Name:** myapp\n"
            "- **Language:** Python\n"
            "- **Runner:** uv\n\n"
            "## Testing\n\n"
            "- **Unit tests:** uv run pytest tests/unit\n"
            "- **Quality checks:** uv run ruff check src/ tests/ && uv run mypy src/\n"
        )

        plan = detect_quality_config(tmp_path)

        assert plan is not None
        assert plan.lint_cmd == "uv run ruff check src/ tests/"

    def test_derives_fix_cmd_for_python(self, tmp_path: Path) -> None:
        """Derives ruff --fix from quality command."""
        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "project.md").write_text(
            "## Project\n\n"
            "- **Name:** myapp\n"
            "- **Language:** Python\n"
            "- **Runner:** uv\n\n"
            "## Testing\n\n"
            "- **Unit tests:** uv run pytest tests/unit\n"
            "- **Quality checks:** uv run ruff check src/ tests/ && uv run mypy src/\n"
        )

        plan = detect_quality_config(tmp_path)

        assert plan is not None
        assert plan.fix_cmd == "uv run ruff check --fix src/ tests/"

    def test_derives_setup_cmd_for_uv(self, tmp_path: Path) -> None:
        """Derives robust uv sync command for uv runner."""
        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "project.md").write_text(
            "## Project\n\n"
            "- **Name:** myapp\n"
            "- **Language:** Python\n"
            "- **Runner:** uv\n\n"
            "## Testing\n\n"
            "- **Unit tests:** uv run pytest tests/unit\n"
            "- **Quality checks:** uv run ruff check src/ tests/\n"
        )

        plan = detect_quality_config(tmp_path)

        assert plan is not None
        assert plan.setup_cmd == "uv sync --all-groups --all-extras"

    def test_normalizes_venv_bin_to_uv_run(self, tmp_path: Path) -> None:
        """Normalizes .venv/bin/X to uv run X for portability."""
        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "project.md").write_text(
            "## Project\n\n"
            "- **Name:** myapp\n"
            "- **Language:** Python\n"
            "- **Runner:** uv\n\n"
            "## Testing\n\n"
            "- **Unit tests:** .venv/bin/pytest tests/unit\n"
            "- **Quality checks:** .venv/bin/ruff check src/ && .venv/bin/mypy src/\n"
            "- **Lint (fast):** .venv/bin/ruff check src/\n"
        )

        plan = detect_quality_config(tmp_path)

        assert plan is not None
        assert plan.test_unit_cmd == "uv run pytest tests/unit"
        assert plan.quality_cmd == "uv run ruff check src/ && uv run mypy src/"
        assert plan.lint_cmd == "uv run ruff check src/"

    def test_js_project(self, tmp_path: Path) -> None:
        """Detects JS/TS project from project.md."""
        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "project.md").write_text(
            "## Project\n\n"
            "- **Name:** myapp\n"
            "- **Language:** TypeScript\n"
            "- **Runner:** npm\n\n"
            "## Testing\n\n"
            "- **Unit tests:** npm test\n"
            "- **Quality checks:** npm run lint\n"
        )

        plan = detect_quality_config(tmp_path)

        assert plan is not None
        assert plan.language == "typescript"
        assert plan.runner == "npm"
        assert plan.lint_cmd == "npm run lint"
        assert plan.setup_cmd == "npm install"

    def test_missing_project_md_returns_none(self, tmp_path: Path) -> None:
        """Returns None when project.md doesn't exist."""
        plan = detect_quality_config(tmp_path)
        assert plan is None

    def test_missing_test_commands_returns_none(self, tmp_path: Path) -> None:
        """Returns None when project.md has no test commands."""
        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "project.md").write_text(
            "## Project\n\n"
            "- **Name:** myapp\n"
        )

        plan = detect_quality_config(tmp_path)
        assert plan is None

    def test_e2e_cmd_populated(self, tmp_path: Path) -> None:
        """Populates test_e2e_cmd when E2E section exists."""
        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "project.md").write_text(
            "## Project\n\n"
            "- **Name:** myapp\n"
            "- **Language:** Python\n"
            "- **Runner:** uv\n\n"
            "## Testing\n\n"
            "- **Unit tests:** uv run pytest tests/unit\n"
            "- **Quality checks:** uv run ruff check src/\n\n"
            "## E2E Testing\n\n"
            "- **Command:** uv run pytest tests/e2e\n"
        )

        plan = detect_quality_config(tmp_path)

        assert plan is not None
        assert plan.test_e2e_cmd == "uv run pytest tests/e2e"

    def test_lint_field_used_when_present(self, tmp_path: Path) -> None:
        """Uses explicit Lint field when provided in project.md."""
        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "project.md").write_text(
            "## Project\n\n"
            "- **Name:** myapp\n"
            "- **Language:** Python\n"
            "- **Runner:** uv\n\n"
            "## Testing\n\n"
            "- **Unit tests:** uv run pytest tests/unit\n"
            "- **Quality checks:** uv run ruff check src/ && uv run mypy src/\n"
            "- **Lint (fast):** uv run ruff check src/\n"
        )

        plan = detect_quality_config(tmp_path)

        assert plan is not None
        assert plan.lint_cmd == "uv run ruff check src/"

    def test_project_root_stored(self, tmp_path: Path) -> None:
        """Stores project_root in the plan."""
        config_dir = tmp_path / ".devops-ai"
        config_dir.mkdir()
        (config_dir / "project.md").write_text(
            "## Project\n\n"
            "- **Name:** myapp\n"
            "- **Language:** Python\n"
            "- **Runner:** uv\n\n"
            "## Testing\n\n"
            "- **Unit tests:** uv run pytest tests/unit\n"
            "- **Quality checks:** uv run ruff check src/\n"
        )

        plan = detect_quality_config(tmp_path)

        assert plan is not None
        assert plan.project_root == tmp_path


# --- Justfile generator ---


class TestGenerateJustfile:
    def test_has_standard_targets(self) -> None:
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/ tests/",
            quality_cmd="uv run ruff check src/ tests/ && uv run mypy src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd="uv run pytest tests/e2e",
            fix_cmd="uv run ruff check --fix src/ tests/",
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_justfile(plan)

        assert "lint:" in content
        assert "quality:" in content
        assert "test-unit:" in content
        assert "test-e2e:" in content
        assert "check:" in content
        assert "fix:" in content
        assert "setup:" in content

    def test_check_target_runs_quality_and_tests(self) -> None:
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/ tests/",
            quality_cmd="uv run ruff check src/ tests/ && uv run mypy src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_justfile(plan)

        # check should call quality and test-unit
        assert "check: quality test-unit" in content

    def test_no_e2e_omits_target(self) -> None:
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/",
            quality_cmd="uv run ruff check src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_justfile(plan)

        assert "test-e2e:" not in content

    def test_no_fix_omits_target(self) -> None:
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/",
            quality_cmd="uv run ruff check src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_justfile(plan)

        assert "fix:" not in content


# --- Makefile generator ---


class TestGenerateMakefile:
    def test_has_phony_and_tabs(self) -> None:
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/ tests/",
            quality_cmd="uv run ruff check src/ tests/ && uv run mypy src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_makefile(plan)

        assert ".PHONY:" in content
        # Makefile recipes use tabs
        assert "\tuv run ruff check src/ tests/" in content

    def test_check_runs_quality_and_tests(self) -> None:
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/",
            quality_cmd="uv run ruff check src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_makefile(plan)

        assert "check: quality test-unit" in content


# --- Pre-commit hook generator ---


class TestGeneratePreCommitHook:
    def test_runs_make_check(self) -> None:
        content = generate_pre_commit_hook()

        assert "#!/bin/sh" in content or "#!/usr/bin/env" in content
        assert "make check" in content

    def test_exits_on_failure(self) -> None:
        content = generate_pre_commit_hook()

        assert "exit" in content or "set -e" in content


# --- CI workflow generator ---


class TestGenerateCiWorkflow:
    def test_python_workflow(self) -> None:
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/",
            quality_cmd="uv run ruff check src/ && uv run mypy src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_ci_workflow(plan)

        assert "name:" in content
        assert "push:" in content or "pull_request:" in content
        assert "make check" in content
        assert "python" in content.lower() or "uv" in content.lower()

    def test_no_ai_review_in_ci(self) -> None:
        """CI workflow should NOT include AI review (separate workflow)."""
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/",
            quality_cmd="uv run ruff check src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_ci_workflow(plan)

        assert "anthropic" not in content.lower()
        assert "ai-review" not in content

    def test_js_workflow(self) -> None:
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="typescript",
            runner="npm",
            lint_cmd="npm run lint",
            quality_cmd="npm run lint",
            test_unit_cmd="npm test",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="npm install",
        )

        content = generate_ci_workflow(plan)

        assert "node" in content.lower() or "npm" in content.lower()


# --- Security workflow generator ---


class TestGenerateSecurityWorkflow:
    def test_has_codeql(self) -> None:
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/",
            quality_cmd="uv run ruff check src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_security_workflow(plan)

        assert "codeql" in content.lower() or "CodeQL" in content

    def test_has_actions_read_permission(self) -> None:
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/",
            quality_cmd="uv run ruff check src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_security_workflow(plan)

        assert "actions: read" in content

    def test_no_ai_review_in_security(self) -> None:
        """Security workflow should NOT include AI review."""
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/",
            quality_cmd="uv run ruff check src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_security_workflow(plan)

        assert "anthropic" not in content.lower()
        assert "ai-security-review" not in content


# --- Review workflow generator ---


class TestGenerateReviewWorkflow:
    def test_uses_stable_action(self) -> None:
        content = generate_review_workflow()

        assert "claude-code-action@v1" in content
        assert "@beta" not in content

    def test_has_timeout(self) -> None:
        content = generate_review_workflow()

        assert "timeout-minutes: 10" in content

    def test_has_oidc_permission(self) -> None:
        content = generate_review_workflow()

        assert "id-token: write" in content


# --- Claude hooks generator ---


class TestGenerateClaudeHooks:
    def test_task_completed_hook(self) -> None:
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/ tests/",
            quality_cmd="uv run ruff check src/ tests/ && uv run mypy src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_claude_hooks(plan)

        # Should be valid JSON with event-keyed hooks
        import json
        data = json.loads(content)
        assert "hooks" in data
        assert isinstance(data["hooks"], dict)
        # Should have a Stop hook
        assert "Stop" in data["hooks"]
        stop_rules = data["hooks"]["Stop"]
        assert len(stop_rules) == 1
        assert stop_rules[0]["hooks"][0]["type"] == "command"

    def test_runs_make_lint(self) -> None:
        plan = QualityPlan(
            project_root=Path("/tmp/test"),
            project_name="myapp",
            language="python",
            runner="uv",
            lint_cmd="uv run ruff check src/ tests/",
            quality_cmd="uv run ruff check src/ tests/ && uv run mypy src/",
            test_unit_cmd="uv run pytest tests/unit",
            test_e2e_cmd=None,
            fix_cmd=None,
            setup_cmd="uv sync --all-groups --all-extras",
        )

        content = generate_claude_hooks(plan)

        assert "make lint" in content


# --- Conftest guardrails ---


class TestGenerateConftest:
    def test_blocks_socket_connect(self) -> None:
        from devops_ai.cli.quality import generate_conftest

        content = generate_conftest()

        assert "socket" in content
        assert "connect" in content
        assert "RuntimeError" in content or "pytest.fail" in content

    def test_existing_conftest_preserved(self, tmp_path: Path) -> None:
        """Don't generate if conftest already exists."""
        from devops_ai.cli.quality import should_generate_conftest

        unit_dir = tmp_path / "tests" / "unit"
        unit_dir.mkdir(parents=True)
        (unit_dir / "conftest.py").write_text("# custom\n")

        assert should_generate_conftest(tmp_path) is False

    def test_non_python_skipped(self, tmp_path: Path) -> None:
        """Don't generate conftest for non-Python projects."""
        from devops_ai.cli.quality import should_generate_conftest

        # No tests/unit/ directory
        assert should_generate_conftest(tmp_path) is False
