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

## Task 1.4 Complete: CLI commands — spec, done, worktrees

**Emergent patterns:**
- Each command has a testable `_command()` function in its own module that returns exit codes. The Typer command in `main.py` is a thin wrapper that calls the function and raises `typer.Exit(code)`.
- `done_command` finds worktrees by exact-match-first, then partial match. Returns `(exit_code, message)` tuple.
- Config is optional everywhere — prefix falls back to `repo_root.name` when no `.devops-ai/` exists.

**Next task notes:**
- `kinfra init` (Task 1.5) needs to create `.devops-ai/infra.toml`. It should detect compose files, parse services/ports, and prompt interactively.
- The `init` stub in `main.py` needs to be wired like spec/done/worktrees.

## Task 1.5 Complete: CLI init — project inspection + config generation

**Emergent patterns:**
- Pure functions (`detect_services_from_compose`, `identify_observability_services`, `detect_project_name`, `generate_infra_toml`) are separated from interactive flow (`init_command`).
- `generate_infra_toml()` builds TOML via string formatting — simple and correct for this format.
- `check_existing_config()` returns `(exists, project_name)` for re-init detection.
- Port env var naming: `{PREFIX}_{SERVICE}_PORT` with dashes replaced by underscores.

**Next task notes:**
- Task 1.6 adds compose parameterization to `init_cmd.py` — replaces host ports with `${VAR:-default}` and comments out observability services.
- `ruamel.yaml` round-trip mode preserves comments. Import: `from ruamel.yaml import YAML; yml = YAML()`.
