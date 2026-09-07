# Secret providers

**Status:** planning
**Signed off:**

## Intent

devops-ai stops requiring 1Password. A new command, `ksecret`, resolves secret
references of the form `<scheme>://…` through pluggable providers — host environment,
`.env` files, 1Password, OpenBao/Vault, Azure Key Vault — and can run any command with
those secrets injected in memory. kinfra sandboxes resolve `[sandbox.secrets]` through
the same resolver, so a newcomer with nothing but a `.env` file can adopt the sandbox
system today, and a project that outgrows plain text changes a reference string, not
its tooling. Any project that installs devops-ai gets this client; agent-memory is the
first external consumer, replacing its hand-rolled `op run` / `op read` / `op item
create` calls.

## Outcomes

- `ksecret read <ref>` prints the value of any supported reference; `ksecret run
  --env-file <file> -- <cmd>` executes a command with every `KEY=<ref>` line resolved
  into its environment and writes nothing to disk; `ksecret check` reports which
  references resolve without ever printing a value.
- References name the provider **type** in their scheme, like `op://`: `$VAR` /
  `env://VAR`, `dotenv://<path>#KEY`, `op://vault/item/field`,
  `bao://<mount>/<path>#<key>`, `akv://<vault>/<secret>`. Bare strings stay literals.
- A `$VAR` reference falls back to the project's `.env` file when the variable is not
  exported — compose semantics — so the zero-configuration `.env` workflow works with
  no reference rewriting.
- `kinfra impl` / `kinfra sandbox start|rebuild` accept every scheme above in
  `[sandbox.secrets]` and produce the same values `ksecret read` would.
- A provider is one module; adding one touches no existing module, enforced by an
  architecture test.
- `ksecret write <ref>` (value on stdin) stores a secret in 1Password, OpenBao, Azure
  Key Vault, or a `.env` file — the primitive agent-memory's `agent create` needs.
- The README documents every scheme and recommends the vault-backed ones over plain
  text. The CLI itself never nudges (directive — human: no plaintext warnings in CLI
  output; recommendation lives in the docs).

## Invariants

- Secret values never appear in argv of any process ksecret spawns, in log output, or
  in error messages — stdin, environment, or 0600 files only.
- Existing `op://`, `$VAR`, and literal references in every onboarded project's
  `infra.toml` keep resolving to the same values.
- kinfra sandbox residency is unchanged: resolved values are written to
  `.env.secrets` in the slot dir (accepted trade-off — sandboxes are short-lived test
  environments); the file is mode 0600.
- kinfra's own surface does not grow: secret commands live under `ksecret`, not
  `kinfra`.
- No new runtime dependency in `pyproject.toml`: providers shell out to the tools the
  user already has (`op`, `az`) or speak HTTP with the standard library (OpenBao).

## Non-goals

- Other cloud vaults (AWS Secrets Manager, GCP Secret Manager): the provider shape
  must admit them; no code implements them.
- Instance-named schemes (`homelab://` mapped per user): the grammar leaves room; no
  alias layer ships.
- Python/JS/Rust client libraries: the CLI is the contract; libraries come later.
- Secret rotation, listing, deletion, or any vault administration.
- agent-memory's migration itself — that is a feature in the agent-memory repo whose
  contract is `ksecret run --env-file` accepting its existing `.env.prod` unchanged.
- Updating an existing 1Password item through `ksecret write` (see M4 brief).

## Discovered context

- All current secret handling is `src/devops_ai/provision.py` (~100 lines): three
  forms, two callers (`cli/impl.py`, `cli/sandbox_cmd.py`), output `.env.secrets`
  passed as a second `--env-file` (`sandbox.py:156`). `config.py` only checks that
  `[sandbox.secrets]` is a table.
- `kinfra init` names the three legacy forms in its `--check` hint
  (`init_cmd.py:694`) and interactive prompt; `skills/kworktree/SKILL.md` describes
  provisioning but names no scheme.
- The package declares one console script (`kinfra`); `install.sh` only symlinks
  skills. A new script needs `uv tool install -e . --reinstall` once — README must say so.
- Gitignored files are absent from worktrees: kinfra's `[sandbox.files]` copies from
  the *main repo root*, so a project's `.env` lives there, not in the impl worktree.
- agent-memory's coupling (`src/agent_memory/cli.py`): `op run --env-file
  ~/.kagents/<agent>/.env.prod -- docker compose …`, `op read` of one ref, `op item
  create … --format=json` (it then references the item by ID, since title references
  collide with archived items), and an `OP_ACCOUNT=` line in the env file that must
  reach the `op` process.
- Karl's homelab vault is OpenBao 2.5.x (`bao` CLI installed, `BAO_ADDR` exported,
  `~/.vault-token` present, mode 0600), KV v2 mounted at `kv/`, paths like
  `kv/homelab/lux/<item>`. OpenBao accepts `VAULT_*` and `BAO_*` env vars. The dev-mode
  image (`openbao/openbao`) mounts KV v2 at `secret/` with a fixed root token.
- Azure: `az` is installed and logged in on Karl's machine; khealth already reads and
  writes Key Vault with `az keyvault secret show|set`. No local AKV runtime exists.
- E2E house style: `tests/e2e/conftest.py::e2e_project` builds a throwaway git repo +
  compose + infra.toml and tears down slots/registry/worktree; tests call
  `impl_command()` in-process. Acceptance tests here reuse that fixture.
- `check_contract_integrity.py` protects `tests/acceptance/**` and
  `docs/specs/*/briefs/*.md`; the feature's test dir is `tests/acceptance/secret_providers/`
  (underscore: it must be importable).

## Decomposition

| Milestone | Brief | Jobs | Depends on | Status | Evidence |
|-----------|-------|------|------------|--------|----------|
| M1 — ksecret with env, dotenv, 1Password | briefs/M1-ksecret-core.md | J1, J2, J3, J4, J5 | — | pending | — |
| M2 — OpenBao provider | briefs/M2-openbao.md | J6 | M1 | pending | — |
| M3 — Azure Key Vault provider | briefs/M3-azure-key-vault.md | J7 | M1 | pending | — |
| M4 — write (optional) | briefs/M4-write.md | J8 | M2, M3 | pending | — |

M2 and M3 are independent and may run in parallel. M4 is optional: it may be dropped
at feature close without amendment if it proves heavy.

## Assumptions

- A1 — `ksecret` ships as a second console script of the existing `devops_ai` package
  (installed by the same `uv tool install`), not a new repo or package.
- A2 — The Azure Key Vault acceptance test runs against a real Key Vault in Karl's
  tenant and skips when `az` is not logged in or the vault name env var is unset;
  Karl creates the vault before M3 starts.
- A3 — The 1Password acceptance test skips when `op` is not signed in; no service
  account is provisioned for CI.
- A4 — The `.env` fallback applies to `$VAR` / `env://VAR` references only; an
  exported variable wins over the file.
- A5 — For kinfra sandboxes, `dotenv://` relative paths and the `.env` fallback
  resolve against the main repo root (where gitignored files live), matching
  `[sandbox.files]`. For `ksecret`, relative paths resolve against the working directory.
- A6 — Provider modules live one-per-scheme under `src/devops_ai/secrets/providers/`;
  the resolver discovers them without naming any. This is the shape the architecture
  test enforces.
- A7 — Write (M4) covers 1Password (create only), OpenBao, Azure Key Vault, and
  `.env` files; the host environment is read-only.
- A8 — An unregistered `word://` value passes through as a literal (so
  `postgres://…` connection strings in `[sandbox.secrets]` keep working);
  `ksecret check` labels it so typos are visible.

## Amendments
