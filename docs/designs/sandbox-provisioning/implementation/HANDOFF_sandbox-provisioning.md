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

## Next Task Notes

Task 2.3 (Validation) should verify the full flow: create a test project with env vars and gitignored mounts, run `kinfra init --auto`, confirm infra.toml has correct provisioning sections, run `kinfra init --check` and confirm gap reporting. Also test against khealth if it has relevant env vars.
