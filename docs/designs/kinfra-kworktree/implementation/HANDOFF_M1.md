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

## Task 1.2 Complete: Config Loader

**Emergent patterns:**
- `load_config()` returns `None` when no infra.toml exists (not an error). Callers decide behavior.
- `InfraConfig.has_sandbox` distinguishes projects with/without Docker sandbox config.
- `parse_mount()` handles Docker-style `host:container[:ro]` — exposed as public API for test access.

**Next task notes:**
- Worktree Manager should import `InfraConfig` and `find_project_root` from `devops_ai.config`.
- For worktrees without infra.toml, prefix falls back to parent directory name — config is optional for spec worktrees.

## Task 1.3 Complete: Worktree Manager

**Emergent patterns:**
- Pure functions (`spec_worktree_path`, `spec_branch_name`, etc.) are separate from git-backed operations — makes unit testing trivial.
- `_run_git()` helper centralizes subprocess calls with consistent `cwd`, `capture_output`, `text=True`.
- `list_worktrees()` parses `git worktree list --porcelain` format and classifies by prefix matching.
- `check_dirty()` gracefully handles missing upstream (returns `has_unpushed=False`).

**Next task notes:**
- CLI commands (Task 1.4) wire `create_spec_worktree`, `remove_worktree`, `list_worktrees`, `check_dirty` to Typer commands.
- `remove_worktree()` takes `repo_root` as first arg (needed to run git from main repo), plus `wt_path` and optional `force`.
