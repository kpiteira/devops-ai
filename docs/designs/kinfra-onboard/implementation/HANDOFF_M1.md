# Handoff — M1: kinfra init --dry-run and --auto

## Task 1.1 Complete: Refactor init_command() to separate detection from interaction

**Approach:** Created `InitPlan` dataclass and `detect_project(project_root) -> InitPlan` pure function. Extracted compose finding, service parsing, obs identification, name detection, port mapping, and toml generation into the pipeline.

**Gotcha:** `init_command()` still re-parses compose after interactive overrides (user may pick a different compose file or prefix, changing port var names). The plan from `detect_project()` is used for display, but final values are rebuilt from user input. Task 1.2 will need to handle this — in `--auto` mode, use `detect_project()` output directly; in interactive mode, rebuild after prompts.

**Next Task Notes:** Task 1.2 adds `--dry-run`, `--auto`, `--health-endpoint` flags. The `detect_project()` return value has everything needed for dry-run output and auto execution. Wire new params into `init_command()` signature and add branching logic: dry_run → format+print plan; auto → skip prompts and use plan directly.

## Task 1.2 Complete: Add --dry-run, --auto, and --health-endpoint flags

**Approach:** Three new params on `init_command()`. `--auto` uses `detect_project()` plan directly (no prompts, no rebuild). `--dry-run` formats plan with `_format_dry_run_output()` and exits. `--health-endpoint` overrides plan.health_endpoint and regenerates toml. Interactive mode falls through to existing prompt-based flow.

**Gotcha:** When `--auto` and existing config coexist, we auto-confirm the update (skip `typer.confirm`). The `--dry-run` without `--auto` still prompts for values, then previews with the user-provided overrides (builds a temporary `overridden_plan`).

**Next Task Notes:** Task 1.3 is VALIDATION — run `kinfra init --dry-run --auto` and `kinfra init --auto` against a real temp project directory. Test the CLI end-to-end via shell commands.

## Task 1.3 Complete: E2E verification

**E2E test: cli/init-flags-validation — 5 steps — PASSED**

**Gotcha:** Test project pyproject.toml needs `version` field — `uv` validates the pyproject in the cwd even when running a globally-installed tool. Minimal `[project]\nname = "x"` fails; needs `version = "0.1.0"`.

**Note:** The `--auto` re-run on existing config doesn't re-parameterize compose ports (they're already parameterized from first run), so compose rewrite is skipped silently. This is correct behavior — `rewrite_compose` sees `${` in port specs and skips them.
