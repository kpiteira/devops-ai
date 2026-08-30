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
    # Structural gates (tests/architecture/) — derived from the unit test command.
    test_arch_cmd: str | None = None


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

    # Derive structural-gates command from the unit test command
    test_arch_cmd = _derive_test_arch_cmd(unit_tests)

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
        test_arch_cmd=test_arch_cmd,
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


def _derive_test_arch_cmd(test_unit_cmd: str) -> str | None:
    """Derive the structural-gates command (tests/architecture/) from the unit
    test command. Only when the unit command names tests/unit — otherwise there
    is no convention to map onto."""
    if "tests/unit" in test_unit_cmd:
        return test_unit_cmd.replace("tests/unit", "tests/architecture")
    return None


# Recipe shared by Makefile/Justfile: run the gates when the directory exists,
# stay green (with a notice) for projects that haven't adopted them yet. Once
# tests/architecture/ lands, the gates' own arming test takes over loud-failure.
def _test_arch_recipe(test_arch_cmd: str) -> str:
    return (
        f"@if [ -d tests/architecture ]; then {test_arch_cmd}; "
        'else echo "no tests/architecture/ yet — structural gates not adopted '
        '(see devops-ai rules/structural-gates.md)"; fi'
    )


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

    if plan.test_arch_cmd:
        lines.extend([
            "",
            "# Structural gates (see devops-ai rules/structural-gates.md)",
            "test-arch:",
            f"    {_test_arch_recipe(plan.test_arch_cmd)}",
        ])

    if plan.test_e2e_cmd:
        lines.extend([
            "",
            "# E2E tests (requires running infrastructure)",
            "test-e2e:",
            f"    {plan.test_e2e_cmd}",
        ])

    check_deps = "quality test-unit"
    check_comment = "# Full check: quality + unit tests"
    if plan.test_arch_cmd:
        check_deps += " test-arch"
        check_comment += " + structural gates"
    lines.extend([
        "",
        check_comment,
        f"check: {check_deps}",
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
    if plan.test_arch_cmd:
        targets.append("test-arch")
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

    if plan.test_arch_cmd:
        lines.extend([
            "",
            "test-arch:",
            f"\t{_test_arch_recipe(plan.test_arch_cmd)}",
        ])

    if plan.test_e2e_cmd:
        lines.extend([
            "",
            "test-e2e:",
            f"\t{plan.test_e2e_cmd}",
        ])

    check_deps = "quality test-unit"
    if plan.test_arch_cmd:
        check_deps += " test-arch"
    lines.extend([
        "",
        f"check: {check_deps}",
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


def generate_public_surface_check() -> str:
    """Generate a dependency-free PR signal for newly public symbols."""
    return '''# Public-surface signal - generated by kinfra init
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HUNK = re.compile(r"^@@ -\\d+(?:,\\d+)? \\+(\\d+)(?:,\\d+)? @@")
PYTHON = re.compile(r"^\\s*(?:async\\s+def|def|class)\\s+([A-Za-z]\\w*)")
EXPORT = re.compile(
    r"^\\s*export\\s+(?:default\\s+)?(?:async\\s+)?"
    r"(?:class|function|const|let|var|interface|type|enum)\\s+([A-Za-z]\\w*)"
)
GO = re.compile(r"^\\s*(?:func\\s+(?:\\([^)]*\\)\\s*)?|type\\s+)([A-Z]\\w*)")
PUBLIC = re.compile(
    r"^\\s*public\\s+(?:(?:static|final|abstract|async|override)\\s+)*"
    r"(?:class|interface|record|enum|[A-Za-z_<>,?\\[\\].]+)\\s+([A-Za-z]\\w*)"
)
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".kt", ".cs"}


def is_source_path(path: str) -> bool:
    file_path = Path(path)
    return (
        file_path.suffix in SOURCE_SUFFIXES
        and "tests" not in file_path.parts
        and not file_path.name.startswith("test_")
    )


def public_symbol(path: str, line: str) -> str | None:
    file_path = Path(path)
    if not is_source_path(path):
        return None
    suffix = file_path.suffix
    pattern = {
        ".py": PYTHON,
        ".ts": EXPORT,
        ".tsx": EXPORT,
        ".js": EXPORT,
        ".jsx": EXPORT,
        ".go": GO,
        ".java": PUBLIC,
        ".kt": PUBLIC,
        ".cs": PUBLIC,
    }.get(suffix)
    if pattern is None:
        return None
    match = pattern.match(line)
    if match is None or match.group(1).startswith("_"):
        return None
    return match.group(1)


def findings(diff: str) -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    path: str | None = None
    new_line = 0
    in_hunk = False
    new_file = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path = None
            in_hunk = False
            new_file = False
            continue
        if line.startswith("new file mode "):
            new_file = True
            continue
        if line.startswith("+++ b/"):
            path = line[6:]
            if new_file and is_source_path(path):
                found.append((path, 1, "<module>"))
            in_hunk = False
            continue
        hunk = HUNK.match(line)
        if hunk:
            new_line = int(hunk.group(1))
            in_hunk = True
            continue
        if not in_hunk or path is None:
            continue
        if line.startswith("+"):
            symbol = public_symbol(path, line[1:])
            if symbol is not None:
                found.append((path, new_line, symbol))
            new_line += 1
        elif not line.startswith("-") and line != r"\\ No newline at end of file":
            new_line += 1
    return found


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    result = subprocess.run(
        ["git", "diff", "--unified=0", "--diff-filter=AM", f"{base}...HEAD", "--"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return result.returncode

    added = findings(result.stdout)
    if added:
        print("New public surface:")
        for path, line, symbol in added:
            print(f"::warning file={path},line={line}::New public symbol: {symbol}")
    else:
        print("No new public symbols detected.")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a") as handle:
            handle.write("## Public-surface signal\\n\\n")
            if added:
                handle.write("| File | Line | Symbol |\\n|------|------|--------|\\n")
                for path, line, symbol in added:
                    handle.write(f"| `{path}` | {line} | `{symbol}` |\\n")
            else:
                handle.write("No new public symbols detected.\\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def generate_contract_integrity_check() -> str:
    """Generate a PR guard for planner-owned briefs and acceptance tests."""
    return '''# Contract-integrity guard - generated by kinfra init
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DEFAULT_ACCEPTANCE_ROOT = "tests/acceptance"
ACCEPTANCE_FIELD = re.compile(
    r"^-\\s+\\*\\*Acceptance tests:\\*\\*\\s*(.+)$",
    re.MULTILINE,
)
BRIEF = re.compile(r"^docs/specs/[^/]+/briefs/[^/]+\\.md$")
GUARD_PATHS = {
    ".devops-ai/check_contract_integrity.py",
    ".github/workflows/ci.yml",
}


def acceptance_root() -> str:
    config = Path(".devops-ai/project.md")
    if not config.exists():
        return DEFAULT_ACCEPTANCE_ROOT
    match = ACCEPTANCE_FIELD.search(config.read_text())
    if match is None:
        return DEFAULT_ACCEPTANCE_ROOT
    value = match.group(1).strip().strip("`'\\"").rstrip("/")
    return value or DEFAULT_ACCEPTANCE_ROOT


def contract_path(path: str, root: str) -> bool:
    normalized = path.replace("\\\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    normalized_root = root.replace("\\\\", "/").strip("/")
    return (
        normalized == normalized_root
        or normalized.startswith(f"{normalized_root}/")
        or BRIEF.match(normalized) is not None
    )


def protected_path(path: str, root: str) -> bool:
    normalized = path.replace("\\\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return contract_path(normalized, root) or normalized in GUARD_PATHS


def changed_paths(diff: str) -> list[str]:
    paths: list[str] = []
    for line in diff.splitlines():
        parts = line.split("\\t")
        if len(parts) < 2:
            continue
        paths.extend(parts[1:])
    return paths


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    branch = sys.argv[2] if len(sys.argv) > 2 else ""
    result = subprocess.run(
        ["git", "diff", "--name-status", f"{base}...HEAD", "--"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return result.returncode

    root = acceptance_root()
    protected = sorted({
        path for path in changed_paths(result.stdout)
        if protected_path(path, root)
    })
    if not protected:
        print("Planner-owned contract files are unchanged.")
        return 0

    planning_branch = branch.startswith(("spec/", "replan/"))
    executor_branch = branch.startswith("impl/")
    if planning_branch:
        print("Planner-owned files changed on a planning branch:")
        for path in protected:
            print(f"  {path}")
        return 0

    blocks_contract_change = executor_branch or any(
        contract_path(path, root) for path in protected
    )
    level = "error" if blocks_contract_change else "warning"
    for path in protected:
        print(
            f"::{level} file={path}::Planner-owned contract file changed "
            f"on branch {branch or '<unknown>'}"
        )
    if blocks_contract_change:
        print(
            "Only planning branches may edit work briefs or blocking acceptance tests.",
            file=sys.stderr,
        )
        return 1
    print(
        "Contract ownership could not be inferred from the branch; review required."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def generate_ci_workflow(plan: QualityPlan) -> str:
    """Generate GitHub Actions CI workflow (quality + tests only)."""
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
        "\n"
        "jobs:\n"
        "  check:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "        with:\n"
        "          fetch-depth: 0\n"
        f"{setup_steps}"
        "      - name: Quality + tests\n"
        "        run: make check\n"
        "      - name: Report new public surface\n"
        "        if: github.event_name == 'pull_request'\n"
        "        run: python3 .devops-ai/check_public_surface.py "
        "\"${{ github.event.pull_request.base.sha }}\"\n"
        "      - name: Protect independent grader\n"
        "        if: github.event_name == 'pull_request'\n"
        "        run: |\n"
        "          git show \"${{ github.event.pull_request.base.sha }}:"
        ".devops-ai/check_contract_integrity.py\" "
        "> \"$RUNNER_TEMP/check_contract_integrity.py\"\n"
        "          python3 \"$RUNNER_TEMP/check_contract_integrity.py\" "
        "\"${{ github.event.pull_request.base.sha }}\" \"$GITHUB_HEAD_REF\"\n"
    )


def generate_security_workflow(plan: QualityPlan) -> str:
    """Generate GitHub Actions security scanning workflow (CodeQL only)."""
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
    """Generate Claude Code settings.json with a blocking Stop hook.

    The Stop hook is the mechanical half of the loop: exit code 2 blocks the
    turn from ending while `make check` is red, feeding the failure back to
    Claude. Claude Code's built-in cap (8 consecutive blocks) breaks spins.
    """
    stop_cmd = (
        'out=$(make check 2>&1) || { printf \'%s\\n\' "$out" | tail -n 40 >&2; '
        "echo 'make check failed — the turn cannot end red; fix and finish "
        "again.' >&2; exit 2; }"
    )
    data = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": stop_cmd,
                            "timeout": 600,
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
        "      - uses: astral-sh/setup-uv@v5\n"
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
    """Generic setup steps (adds setup-uv if runner is uv)."""
    uv_step = (
        "      - uses: astral-sh/setup-uv@v5\n"
        if plan.runner == "uv"
        else ""
    )
    return (
        f"{uv_step}"
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
