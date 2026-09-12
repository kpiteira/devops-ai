---
feature: secret-providers
milestone: M1
spec: ../SPEC.md
blocking: uv run pytest tests/acceptance/secret_providers/test_m1_ksecret_core.py tests/architecture/test_secret_providers.py -q
---

# Brief 1 — ksecret with env, dotenv, 1Password

## Jobs

- **J1** — When a script needs a secret value, its author can run `ksecret read
  --print <ref>` and get the value on stdout, so that a Makefile, a shell script, or
  any language consumes secrets through one command whose code never changes when a
  secret moves between backends — only the reference string does. Without `--print`,
  `read` refuses, so printing is always a deliberate act.
- **J2** — When a project needs secrets inside a process (agent-memory's `docker
  compose up`), the developer can run `ksecret run --env-file <file> -- <cmd>` and the
  command sees every reference resolved in its environment, so that values live only in
  memory and `op run` is no longer required.
- **J3** — When a developer or agent wants to know whether references resolve without
  seeing values, they can run `ksecret check`, so that a session can verify secrets
  exist without leaking them into chat history.
- **J4** — When a newcomer has only a `.env` file, they can declare `[sandbox.secrets]`
  with `$VAR` or `dotenv://` references and `kinfra impl` provisions the sandbox from
  that file, so that adopting kinfra needs no 1Password.
- **J5** — When a project outgrows plain text, its maintainer reads the README and
  finds every scheme with a recommendation ladder, so that the upgrade path is a
  reference edit.

## Surface

**Reference grammar** (one resolver, shared by `ksecret` and kinfra):

| Form | Resolves to |
|------|-------------|
| `bare text` | the text itself (literal) — including an unregistered `word://…` (A8) |
| `$NAME`, `env://NAME` | exported variable `NAME`; else key `NAME` in `./.env` if that file exists; else error |
| `dotenv://<path>#<KEY>` | key `KEY` in the dotenv file at `path` (relative to cwd; for kinfra, relative to the main repo root) |
| `op://<vault>/<item>/<field>` | `op read --no-newline` (unchanged behavior, unchanged error guidance) |

Dotenv file format: `KEY=value` per line, `#` comments and blank lines ignored,
optional single or double quotes around the value, optional `export ` prefix.

**Commands** (console script `ksecret`, declared in `pyproject.toml`):

- `ksecret read --print <ref> [--no-newline]` (`-p` for `--print`) — value on stdout
  followed by a newline unless `--no-newline`; exit 0. Unresolvable: nothing on
  stdout, one actionable line on stderr naming the reference (never a value), exit 1.
  Without `--print`: nothing on stdout, exit 2, one stderr line saying that printing
  requires `--print` and that `ksecret check` verifies without printing.
- `ksecret run [--env-file <file>]… -- <cmd> [args…]` — every `KEY=value` line of each
  file is placed in the child environment; values that are references are resolved
  first; literal lines (e.g. `OP_ACCOUNT=…`) are set in the environment *before*
  resolution so providers see them. The parent environment passes through. Exit code
  is the child's. Any unresolvable reference: the command is not run, stderr lists
  every failing key, exit 1. Nothing is written to disk.
- `ksecret check [<ref>…] [--env-file <file>]…` — one line per reference: the key
  (or the ref when given bare), a status word — `ok`, `literal`, or `error` — and for
  errors the reason; never a value. Exit 0 iff every reference resolves. `literal`
  covers bare text and unregistered schemes.
- `ksecret --help` lists the three commands.

**kinfra:** `[sandbox.secrets]` values go through the same resolver. `.env.secrets` in
the slot dir has mode 0600. `kinfra init --check` and the interactive prompt name
`dotenv://` alongside the legacy forms.

**Docs:** a `## Secrets` section in `README.md` naming every scheme in the grammar
above plus `bao://` and `akv://` (as "coming" or documented, executor's call), the
recommendation ladder (vault-backed over `.env`), and the one-time
`uv tool install -e . --reinstall` needed to obtain the new command.

## Blocking

| Job | Planner-authored test | Observable proof |
|-----|-----------------------|------------------|
| J1 | `test_m1_ksecret_core.py::test_read_env_dotenv_and_literal` | `read` returns the exported value, the dotenv value, the literal, and `$VAR` falls back to `./.env` |
| J1 | `test_m1_ksecret_core.py::test_read_failure_names_ref_not_value` | Missing key → exit 1, stderr names the ref, stdout empty |
| J1 | `test_m1_ksecret_core.py::test_read_refuses_without_print` | Bare `read` → exit 2, stdout empty, stderr points at `--print` and `check`; the value never appears |
| J1 | `test_m1_ksecret_core.py::test_read_op_reference` | An item the test creates in 1Password reads back; skips when Karl does not grant `op` access (there is no scriptable sign-in — A3) |
| J2 | `test_m1_ksecret_core.py::test_run_injects_resolved_env_without_disk` | Child sees resolved values; literal lines pass through; no new file appears; child exit code propagates |
| J2 | `test_m1_ksecret_core.py::test_run_refuses_when_any_ref_fails` | Command not executed, exit 1, stderr names the failing key |
| J3 | `test_m1_ksecret_core.py::test_check_reports_without_values` | Output classifies ok/literal/error; the secret value string is absent from stdout and stderr |
| J4 | `test_m1_ksecret_core.py::test_kinfra_sandbox_resolves_dotenv_and_env_fallback` | `kinfra impl` on a project with `.env` + `dotenv://` and `$VAR` refs writes both values to the slot's `.env.secrets`, mode 0600 |
| J5 | `test_m1_ksecret_core.py::test_readme_documents_every_scheme` | README has a Secrets section naming each scheme and the reinstall step |
| — | `test_m1_ksecret_core.py::test_providers_package_is_in_place` | The providers package exists with at least three modules (env, dotenv, 1Password) |
| — | `tests/architecture/test_secret_providers.py` | Providers are one module each under a providers package; the resolver and CLI import none by name (this standing gate skips itself until the package exists — the row above is what makes that skip safe) |

Plus the standing gates: `make check` exits 0.

## Advisory

- `ksecret check --infra` (or similar) reading `[sandbox.secrets]` from the current
  project — useful for agents, not required.
- `env://` documented as the canonical form with `$VAR` as the shorthand.

## Invariants

- Secret values never appear in argv of spawned processes, logs, or error text.
- Every existing `infra.toml` keeps resolving identically (`op://`, `$VAR`, literal).
- kinfra's command set does not grow; sandbox residency (`.env.secrets`) is unchanged
  apart from the 0600 mode.
- No new entry in `[project.dependencies]`.

## Non-goals

- OpenBao and Azure Key Vault schemes (M2, M3) — the README may name them, the
  resolver need not know them.
- Write (M4). Instance aliases. Client libraries.

## Context

- `src/devops_ai/provision.py` holds today's resolver (`resolve_secret`,
  `resolve_all_secrets`, `generate_secrets_file`) with unit tests in
  `tests/unit/test_provision.py` that patch `subprocess.run` for `op`. Callers:
  `cli/impl.py:266` and `cli/sandbox_cmd.py:110`.
- The main repo root at sandbox time is `repo_root` in `impl_command` and `main_repo`
  in `sandbox_cmd`; `[sandbox.files]` already resolves sources against it — the same
  root is where a project's gitignored `.env` lives.
- `tests/e2e/conftest.py::e2e_project` is the throwaway-project fixture the J4 test
  imports; it runs `python:3.12-slim` in compose and needs Docker.
- agent-memory's `.env.prod` is `OP_ACCOUNT=<account>` plus `KEY=op://…` lines — the
  J2 literal-passthrough behavior is what lets that file work unchanged.
- The public-surface guard (`.devops-ai/check_public_surface.py`) flags new public
  symbols in PR review; it is a signal, not an API contract.

## Decisions

- Printing is opt-in (`--print`) and a bare `read` refuses rather than acting like
  `check`: one verb per meaning, and a refusal teaches an agent faster than a quiet
  success it did not ask for (Karl's review, 2026-09-12).
- Provider modules live one per scheme under `src/devops_ai/secrets/providers/`; the
  resolver discovers providers from that package without importing any by name; the
  CLI imports only the resolver. (A6 — the architecture test pins exactly this.)
- `$VAR` stays supported as shorthand for `env://VAR`; both fall back to `./.env`
  (A4, A5).
- Unregistered schemes pass through as literals (A8) — backward compatibility for
  connection-string literals beats catching typos, and `check` still surfaces them.
- 1Password error guidance (install / sign in / not found) is kept verbatim from
  today's `provision.py`.
- The `op` provider reads `OP_ACCOUNT` from the environment like any other `op`
  invocation — no special handling beyond J2's literal-first ordering.

---

**If a stated fact is false, a decision conflicts with what's actually in the codebase,
or an acceptance test contradicts a job: stop and describe what you found. Don't comply,
and don't classify the problem yourself.**
