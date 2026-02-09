# Handoff: M1 — Foundation

## Task 1.1 Complete: Package Foundation

**Gotchas:**
- `typer[all]` extra no longer exists in typer 0.21+. Use `typer>=0.9` without the `[all]` extra.
- Python 3.14 is the system python. `requires-python = ">=3.11"` works fine.

**Emergent patterns:**
- CLI test uses `subprocess.run([sys.executable, "-m", "devops_ai.cli.main", "--help"])` rather than Typer's test runner for smoke tests.
- `hatchling` build backend with `[tool.hatch.build.targets.wheel] packages = ["src/devops_ai"]` for src layout.

**Next task notes:**
- Config loader (`src/devops_ai/config.py`) can use `tomllib` directly since Python >=3.11.
- `find_project_root()` walks up from cwd looking for `.devops-ai/` directory.
