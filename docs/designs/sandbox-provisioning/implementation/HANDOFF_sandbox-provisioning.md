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

## Next Task Notes

M2 (Discovery) needs to extend `detect_project()` with env var and volume mount detection. The existing `detect_services_from_compose()` parses YAML for ports/images — env var detection should use raw text regex (not YAML parser) to catch `${VAR}` in all contexts. Gitignore detection should use `git check-ignore -q <path>` subprocess.
