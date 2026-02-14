# Handoff: Sandbox Provisioning

## Gotchas

- **Slot cleanup on provisioning failure:** Initially cleaned up slot + slot dir when provisioning failed, which made `kinfra sandbox start` recovery impossible (slot not in registry). Fixed: keep slot allocated, only clean up on Docker startup failure. The slot dir already has .env.sandbox and override.yml at that point.

- **mypy variance with list[Path] vs list[str | Path]:** `_env_files_for_slot` returns `list[Path]` but `_compose_cmd` expected `list[str | Path]`. Fix: use `Sequence[str | Path]` for the parameter type (covariant, accepts both).

- **`[sandbox.env]` entries are compose-level variable substitution:** They go into `.env.sandbox` which Docker Compose uses for `${VAR}` substitution in the compose YAML. If the compose file doesn't reference `${APP_ENV}` in a service's `environment:` section, the container won't have that env var. This is correct — the design says env vars are for compose-level config, not arbitrary container injection.

## E2E Validation

| Test | Steps | Result |
|------|-------|--------|
| Provisioning failure | Ran `kinfra impl` with `$APP_SECRET` unset | PASSED — clear error message, suggests `kinfra sandbox start` |
| Recovery via sandbox start | Set `APP_SECRET`, ran `kinfra sandbox start` from worktree | PASSED — config.yaml copied, secret resolved, container started |
| Artifact verification | Checked `.env.secrets`, `.env.sandbox`, container env vars | PASSED — all correct, secret value in container |

## M2 Task 2.1 — Detection Functions

- `detect_env_vars()` uses raw text regex `\$\{([A-Z_][A-Z0-9_]*)(?::-(.*?))?\}` to find `${VAR}` and `${VAR:-default}` patterns, then attributes to services via YAML parsing of `environment:` blocks.
- `detect_gitignored_mounts()` parses volumes, skips named volumes (top-level `volumes:` keys), runs `git check-ignore -q` for gitignore interpretation.
- **Gotcha:** `lstrip('./')` strips individual chars (`.`, `/`), not the prefix string. Use `removeprefix('./')` instead.

## M2 Task 2.2 — Init Flow Integration

- `generate_infra_toml()` extended with `env`, `secrets`, `files` params — appends `[sandbox.env]`, `[sandbox.secrets]`, `[sandbox.files]` sections.
- `--check` flag: runs detection on already-onboarded project, reports gaps with suggested `infra.toml` additions.
- `--auto` mode: calls `_resolve_provisioning_auto()` — env vars → `$VAR_NAME` secrets, file mounts → copy from main repo if source exists.
- **Gotcha:** mypy flow-sensitive typing reuses loop variable type — use distinct names (`ec` for env, `fc` for file) when iterating different dataclass lists in same scope.

## M2 Task 2.3 — E2E Validation

- **Bug found:** `--check` on parameterized compose reported all vars (port vars invisible after parameterization, declared secrets/files not excluded). Fixed by loading existing config in check mode — adds port vars to `known_vars`, filters out declared secrets/env/files.
- `detect_project()` now accepts `extra_known_vars` parameter for this purpose.

| Test | Steps | Result |
|------|-------|--------|
| Dry-run detection | `kinfra init --dry-run --auto` on test project | PASSED — APP_SECRET, LOG_LEVEL, config.yaml detected; named volume app-data excluded |
| Auto init with provisioning | `kinfra init --auto` on test project | PASSED — infra.toml has [sandbox.secrets] and [sandbox.files] sections |
| Check gap detection | Added NEW_API_KEY to compose, `kinfra init --check` | PASSED — only NEW_API_KEY reported, existing vars excluded |
| Check no gaps | Removed NEW_API_KEY, `kinfra init --check` | PASSED — "All good — no gaps detected" |
| khealth check | `kinfra init --check` on khealth project | PASSED — detects TELEGRAM_BOT_TOKEN and config.yaml as gaps |
