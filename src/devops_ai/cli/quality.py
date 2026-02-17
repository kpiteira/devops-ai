"""Quality infrastructure detection and artifact generation.

Pure functions — no CLI interaction, no file writes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class QualityPlan:
    """Detected quality configuration for a project."""

    project_root: Path
    project_name: str
    language: str  # "python", "typescript", "go", "rust"
    runner: str  # "uv", "npm", "go", "cargo"
    lint_cmd: str  # fast: ruff only
    quality_cmd: str  # full: ruff + mypy
    test_unit_cmd: str
    test_e2e_cmd: str | None
    fix_cmd: str | None
    setup_cmd: str


def detect_quality_config(project_root: Path) -> QualityPlan | None:
    """Read project.md and derive quality configuration.

    Returns None if project.md doesn't exist or lacks test commands.
    """
    project_md = project_root / ".devops-ai" / "project.md"
    if not project_md.exists():
        return None

    content = project_md.read_text()

    # Extract fields
    name = _extract_field(content, "Name")
    language = _extract_field(content, "Language")
    runner = _extract_field(content, "Runner")
    unit_tests = _extract_field(content, "Unit tests")
    quality_checks = _extract_field(content, "Quality checks")
    lint_fast = _extract_field(content, "Lint \\(fast\\)")
    e2e_cmd = _extract_field(content, "Command", section="E2E")

    if not unit_tests or not quality_checks:
        return None

    # Normalize language
    lang = (language or "").lower().strip()
    if lang in ("typescript", "javascript", "ts", "js"):
        lang = "typescript" if lang in ("typescript", "ts") else "javascript"
    elif lang in ("python", "py"):
        lang = "python"
    elif not lang:
        lang = "python"  # default

    # Normalize runner
    run = (runner or "").split("—")[0].split("–")[0].strip().lower()
    if not run:
        run = "uv" if lang == "python" else "npm"

    # Normalize commands for portability (e.g., .venv/bin/ruff → uv run ruff)
    if run == "uv":
        quality_checks = _normalize_uv_cmd(quality_checks)
        unit_tests = _normalize_uv_cmd(unit_tests)
        if lint_fast:
            lint_fast = _normalize_uv_cmd(lint_fast)
        if e2e_cmd:
            e2e_cmd = _normalize_uv_cmd(e2e_cmd)

    # Derive lint command (after normalization so fix_cmd inherits clean paths)
    lint_cmd = lint_fast or _derive_lint_cmd(quality_checks, lang)

    # Derive fix command
    fix_cmd = _derive_fix_cmd(lint_cmd, lang)

    # Derive setup command
    setup_cmd = _derive_setup_cmd(run)

    return QualityPlan(
        project_root=project_root,
        project_name=name or project_root.name,
        language=lang,
        runner=run,
        lint_cmd=lint_cmd,
        quality_cmd=quality_checks,
        test_unit_cmd=unit_tests,
        test_e2e_cmd=e2e_cmd,
        fix_cmd=fix_cmd,
        setup_cmd=setup_cmd,
    )


def _extract_field(
    content: str, field: str, section: str | None = None,
) -> str | None:
    """Extract a markdown field value like '- **Name:** value'."""
    if section:
        # Find the section first, then search within it
        section_match = re.search(
            rf"##\s+{section}.*?\n(.*?)(?=\n##|\Z)",
            content,
            re.DOTALL,
        )
        if not section_match:
            return None
        content = section_match.group(1)

    match = re.search(
        rf"-\s+\*\*{field}:\*\*\s*(.+)",
        content,
    )
    if match:
        return match.group(1).strip()
    return None


def _derive_lint_cmd(quality_cmd: str, language: str) -> str:
    """Extract fast lint command from full quality command.

    For Python with ruff+mypy: extract just the ruff part.
    For others: use the full quality command.
    """
    if language == "python" and "&&" in quality_cmd:
        # Take first part (typically ruff check)
        parts = quality_cmd.split("&&")
        first = parts[0].strip()
        if "ruff" in first:
            return first
    return quality_cmd


def _derive_fix_cmd(lint_cmd: str, language: str) -> str | None:
    """Derive auto-fix command from lint command."""
    if language == "python" and "ruff check" in lint_cmd:
        return lint_cmd.replace("ruff check", "ruff check --fix")
    return None


def _normalize_uv_cmd(cmd: str) -> str:
    """Normalize .venv/bin/X to uv run X for portability.

    Handles chained commands like '.venv/bin/ruff check && .venv/bin/mypy'.
    """
    return re.sub(r"\.venv/bin/", "uv run ", cmd)


def _derive_setup_cmd(runner: str) -> str:
    """Derive setup command from runner."""
    if runner == "uv":
        return "uv sync --all-groups --all-extras"
    if runner in ("npm", "npx"):
        return "npm install"
    if runner == "pnpm":
        return "pnpm install"
    if runner == "yarn":
        return "yarn install"
    if runner == "go":
        return "go mod download"
    if runner == "cargo":
        return "cargo build"
    return f"{runner} install"


def generate_justfile(plan: QualityPlan) -> str:
    """Generate Justfile content with standard quality targets."""
    lines = [
        "# Quality infrastructure — generated by kinfra init",
        "",
        "# Fast lint only (ruff)",
        "lint:",
        f"    {plan.lint_cmd}",
        "",
        "# Full quality checks (lint + type checking)",
        "quality:",
        f"    {plan.quality_cmd}",
        "",
        "# Unit tests",
        "test-unit:",
        f"    {plan.test_unit_cmd}",
    ]

    if plan.test_e2e_cmd:
        lines.extend([
            "",
            "# E2E tests (requires running infrastructure)",
            "test-e2e:",
            f"    {plan.test_e2e_cmd}",
        ])

    lines.extend([
        "",
        "# Full check: quality + unit tests",
        "check: quality test-unit",
    ])

    if plan.fix_cmd:
        lines.extend([
            "",
            "# Auto-fix lint issues",
            "fix:",
            f"    {plan.fix_cmd}",
        ])

    lines.extend([
        "",
        "# Install/update dependencies",
        "setup:",
        f"    {plan.setup_cmd}",
        "",
    ])

    return "\n".join(lines)


def generate_makefile(plan: QualityPlan) -> str:
    """Generate Makefile content with standard quality targets."""
    targets = ["lint", "quality", "test-unit", "check", "setup"]
    if plan.test_e2e_cmd:
        targets.append("test-e2e")
    if plan.fix_cmd:
        targets.append("fix")

    lines = [
        "# Quality infrastructure — generated by kinfra init",
        "",
        f".PHONY: {' '.join(targets)}",
        "",
        "lint:",
        f"\t{plan.lint_cmd}",
        "",
        "quality:",
        f"\t{plan.quality_cmd}",
        "",
        "test-unit:",
        f"\t{plan.test_unit_cmd}",
    ]

    if plan.test_e2e_cmd:
        lines.extend([
            "",
            "test-e2e:",
            f"\t{plan.test_e2e_cmd}",
        ])

    lines.extend([
        "",
        "check: quality test-unit",
    ])

    if plan.fix_cmd:
        lines.extend([
            "",
            "fix:",
            f"\t{plan.fix_cmd}",
        ])

    lines.extend([
        "",
        "setup:",
        f"\t{plan.setup_cmd}",
        "",
    ])

    return "\n".join(lines)


def generate_pre_commit_hook() -> str:
    """Generate pre-commit hook that runs make check."""
    return (
        "#!/bin/sh\n"
        "# Pre-commit hook — generated by kinfra init\n"
        "# Runs full quality checks + unit tests before each commit.\n"
        "\n"
        "set -e\n"
        "\n"
        "# Unset git env vars that leak into subprocesses and break tests\n"
        "# that create their own git repos.\n"
        "unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE\n"
        "\n"
        "echo 'Running pre-commit checks...'\n"
        "make check\n"
    )


def generate_ci_workflow(plan: QualityPlan) -> str:
    """Generate GitHub Actions CI workflow."""
    if plan.language == "python":
        setup_steps = _python_setup_steps(plan)
    elif plan.language in ("typescript", "javascript"):
        setup_steps = _node_setup_steps(plan)
    else:
        setup_steps = _generic_setup_steps(plan)

    return (
        "# CI workflow — generated by kinfra init\n"
        "name: CI\n"
        "\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "  pull_request:\n"
        "    branches: [main]\n"
        "\n"
        "permissions:\n"
        "  contents: read\n"
        "  pull-requests: write\n"
        "  id-token: write\n"
        "\n"
        "jobs:\n"
        "  check:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        f"{setup_steps}"
        "      - name: Quality + tests\n"
        "        run: make check\n"
        "\n"
        "  ai-review:\n"
        "    if: github.event_name == 'pull_request'\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "        with:\n"
        "          fetch-depth: 0\n"
        "      - uses: anthropics/claude-code-action@beta\n"
        "        with:\n"
        "          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}\n"
        "          direct_prompt: |\n"
        "            Review this PR. Check:\n"
        "            1. Code quality and correctness\n"
        "            2. New features covered by unit tests in tests/unit/?\n"
        "            3. Unit tests avoid real I/O? (no network, subprocess, Docker)\n"
        "            4. For significant features: what E2E scenarios"
        " should cover this?\n"
        "            5. Security concerns and breaking changes\n"
        "            If test coverage is clearly inadequate, request changes.\n"
    )


def generate_security_workflow(plan: QualityPlan) -> str:
    """Generate GitHub Actions security scanning workflow."""
    codeql_lang = _codeql_language(plan.language)

    return (
        "# Security workflow — generated by kinfra init\n"
        "name: Security\n"
        "\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "  pull_request:\n"
        "    branches: [main]\n"
        "  schedule:\n"
        "    - cron: '0 6 * * 1'  # Weekly Monday 6am UTC\n"
        "\n"
        "permissions:\n"
        "  actions: read\n"
        "  contents: read\n"
        "  security-events: write\n"
        "  pull-requests: write\n"
        "  id-token: write\n"
        "\n"
        "jobs:\n"
        "  codeql:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: github/codeql-action/init@v3\n"
        "        with:\n"
        f"          languages: {codeql_lang}\n"
        "      - uses: github/codeql-action/analyze@v3\n"
        "\n"
        "  ai-security-review:\n"
        "    if: github.event_name == 'pull_request'\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "        with:\n"
        "          fetch-depth: 0\n"
        "      - uses: anthropics/claude-code-action@beta\n"
        "        with:\n"
        "          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}\n"
        "          direct_prompt: |\n"
        "            Security review this PR. Check for:\n"
        "            1. Credentials or secrets in code\n"
        "            2. Injection vulnerabilities (SQL, command, XSS)\n"
        "            3. OWASP top 10 issues\n"
        "            4. Dependency security concerns\n"
    )


def generate_conftest() -> str:
    """Generate conftest.py that blocks socket.connect in unit tests."""
    return (
        '"""Unit test guardrails — generated by kinfra init."""\n'
        "\n"
        "import socket\n"
        "\n"
        "_original_connect = socket.socket.connect\n"
        "\n"
        "\n"
        "def _guarded_connect(self, address):  # type: ignore[no-untyped-def]\n"
        '    raise RuntimeError(\n'
        '        f"Unit tests must not make network connections (tried {address}). "\n'
        '        "Move this test to tests/integration/ if it needs real I/O."\n'
        "    )\n"
        "\n"
        "\n"
        "socket.socket.connect = _guarded_connect  # type: ignore[assignment]\n"
    )


def should_generate_conftest(project_root: Path) -> bool:
    """Check if conftest.py should be generated.

    Only for Python projects with tests/unit/ and no existing conftest.
    """
    unit_dir = project_root / "tests" / "unit"
    if not unit_dir.is_dir():
        return False
    if (unit_dir / "conftest.py").exists():
        return False
    return True


def generate_claude_hooks(plan: QualityPlan) -> str:
    """Generate Claude Code settings.json with Stop hook for lint."""
    data = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "make lint",
                            "timeout": 120,
                        },
                    ],
                },
            ],
        },
    }
    return json.dumps(data, indent=2) + "\n"


# --- Internal helpers ---


def _python_setup_steps(plan: QualityPlan) -> str:
    """GitHub Actions setup steps for Python projects."""
    return (
        "      - uses: actions/setup-python@v5\n"
        "        with:\n"
        "          python-version: '3.12'\n"
        "      - uses: astral-sh/setup-uv@v4\n"
        "      - name: Install dependencies\n"
        f"        run: {plan.setup_cmd}\n"
    )


def _node_setup_steps(plan: QualityPlan) -> str:
    """GitHub Actions setup steps for Node.js projects."""
    return (
        "      - uses: actions/setup-node@v4\n"
        "        with:\n"
        "          node-version: '20'\n"
        "          cache: npm\n"
        "      - name: Install dependencies\n"
        f"        run: {plan.setup_cmd}\n"
    )


def _generic_setup_steps(plan: QualityPlan) -> str:
    """Generic setup steps."""
    return (
        "      - name: Install dependencies\n"
        f"        run: {plan.setup_cmd}\n"
    )


def _codeql_language(language: str) -> str:
    """Map project language to CodeQL language identifier."""
    mapping = {
        "python": "python",
        "typescript": "javascript-typescript",
        "javascript": "javascript-typescript",
        "go": "go",
        "rust": "cpp",  # CodeQL doesn't support Rust natively
        "java": "java",
    }
    return mapping.get(language, "python")
