# Secret providers

**Status:** in progress
**Signed off:** 2026-09-12 — Karl (review conversation: A1–A8 confirmed, `read` prints only with `--print`, host-side resolution model; machine-credential provisioning flagged for a later discussion)

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

- `ksecret check` reports which references resolve without ever printing a value;
  `ksecret run --env-file <file> -- <cmd>` executes a command with every `KEY=<ref>`
  line resolved into its environment and writes nothing to disk; `ksecret read <ref>`
  resolves a reference and confirms it exists without printing it (exit 1 if it
  does not); only `ksecret read --print <ref>` prints the value — printing a secret
  is always an explicit, visible choice (an agent that types `read` by habit
  gets a confirmation, not a leak).
- Resolution happens where the credentials are: on the host, by `ksecret`, using the
  user's own `op` grant, `az login`, or Vault token. A service started through
  `ksecret run` receives values as environment variables and never talks to a vault
  itself.
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
- Obtaining or rotating a *machine* credential for a provider — an AppRole login
  flow for OpenBao, service-principal secret handling for Azure, issuing a 1Password
  service-account token. Providers *use* whatever credential the environment already
  holds (see Discovered context), so a container that has `ksecret` and a
  platform-injected credential can resolve at startup; getting that credential into
  the container is the platform's job (or a later feature), not this one's.
- Instance-named schemes (`homelab://` mapped per user): the grammar leaves room; no
  alias layer ships.
- Python/JS/Rust client libraries: the CLI is the contract; libraries come later.
- Secret rotation, listing, deletion, or any vault administration.
- agent-memory's migration itself — that is a feature in the agent-memory repo whose
  contract is `ksecret run --env-file` accepting its existing `.env.prod` unchanged.

## Discovered context

- All current secret handling is `src/devops_ai/provision.py` (223 lines, about
  half of it secrets, the rest file provisioning): three forms, two callers (`cli/impl.py`, `cli/sandbox_cmd.py`), output `.env.secrets`
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
- Every provider takes its credential from the environment: `op read` honors
  `OP_SERVICE_ACCOUNT_TOKEN`, the OpenBao provider reads `BAO_TOKEN` / `VAULT_TOKEN`
  (an AppRole-issued token works as-is), and the Azure provider uses whatever `az`
  session exists (`az login --identity` on a VM or Container App with a managed
  identity). In-container resolution therefore works with this feature's providers
  wherever the platform supplies such a credential.
- On the Lux VM, services already receive secrets as env files rendered by
  vault-agent from `kv/homelab/lux/*` — there, `dotenv://` and `$VAR` are the right
  references, not `bao://`.
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
| M1 — ksecret with env, dotenv, 1Password | briefs/M1-ksecret-core.md | J1, J2, J3, J4, J5 | — | delivered | [c40452a](https://github.com/kpiteira/devops-ai/commit/c40452a) · [#32](https://github.com/kpiteira/devops-ai/pull/32) · [divergence](divergences/M1-2026-09-12.md) (resolved by #30) |
| M2 — OpenBao provider | briefs/M2-openbao.md | J6 | M1 | in progress | — |
| M3 — Azure Key Vault provider | briefs/M3-azure-key-vault.md | J7 | M1 | pending | — |
| M4 — write (optional) | briefs/M4-write.md | J8 | M2, M3 | pending | — |

M2 and M3 are independent and may run in parallel. M4 is optional: it may be dropped
at feature close without amendment if it proves heavy.

## Decisions

<!-- Drafted as Assumptions; each confirmed by Karl on 2026-09-08. IDs kept — the
briefs and tests reference them. -->

- A1 — `ksecret` ships as a second console script of the existing `devops_ai` package
  (installed by the same `uv tool install`), not a new repo or package.
- A2 — The Azure Key Vault acceptance test runs against a real Key Vault in Karl's
  tenant, named by `KSECRET_ACCEPTANCE_AKV_VAULT`, and skips when `az` is not logged
  in or the variable is unset. **Prerequisite for M3 — met 2026-09-12:** the vault
  is `kv-devops-ai-accept` in `devops-ai-test-rg` (facts in the M3 brief); Karl
  exports the variable in his shell. M3 cannot be declared delivered on skips alone.
- A3 — The 1Password acceptance tests skip when access is not granted. There is no
  scriptable sign-in: `op` prompts Karl per access and he grants it, so the tests
  simply attempt access and wait long enough for a touch. No service account.
- A4 — The `.env` fallback applies to `$VAR` / `env://VAR` references only; an
  exported variable wins over the file.
- A5 — For kinfra sandboxes, `dotenv://` relative paths and the `.env` fallback
  resolve against the main repo root (where gitignored files live), matching
  `[sandbox.files]`. For `ksecret`, relative paths resolve against the working directory.
- A6 — Provider modules live one-per-scheme under `src/devops_ai/secrets/providers/`;
  the resolver discovers them without naming any. The architecture test enforces
  exactly this.
- A7 — Write (M4) covers 1Password, OpenBao, Azure Key Vault, and `.env` files; the
  host environment is read-only. *Corrected by the 2026-09-12 amendment:* the draft
  said 1Password was create-only because `op item edit` took values only via argv;
  `op item edit --template <file>` exists precisely for sensitive values, so update
  is in scope and the no-values-in-argv invariant holds for every provider.
  **Open, cross-project:** agent-memory's own `op item create` call passes the value
  in argv today — a migration item for that repo, not a conflict in this design.
- A8 — An unregistered `word://` value passes through as a literal (so
  `postgres://…` connection strings in `[sandbox.secrets]` keep working);
  `ksecret check` labels it so typos are visible.

## Assumptions

<!-- Empty: all eight promoted above on 2026-09-08. -->

## Amendments

- [x] 2026-09-12 (M4) fact-correction: `op item edit` accepts a JSON `--template`
  file for sensitive values (verified against `op item edit --help`), so updating a
  1Password item needs no argv. M4's `op://` write is create-or-update; the
  "create-only" non-goal and the related A7 tension are removed. No milestone had
  started. Acknowledged by Karl 2026-09-12.
- [x] 2026-09-12 (M1) fact-correction: the planner's 1Password fixture gated on
  `op whoami` (exits 1 on Karl's machine while `op` works) and defaulted to a vault
  named `Private` (does not exist), so J1's `op://` test could only skip. Raised by the
  M1 executor (divergence `M1-2026-09-12`). Fixed on the spec branch: access is proven
  by querying the acceptance vault `devops-ai-secrets-test`. No decision changed.
- [x] 2026-09-12 (M1) fact-correction: the M1 brief's Surface says `kinfra init
  --check` "and the interactive prompt" name `dotenv://`; `init` has no interactive
  secrets prompt (verified on main: the only place a scheme is named is the
  `--check`/dry-run hint text). Raised by the M1 executor in PR #32; the hint now
  names `dotenv://`. Nothing built changed.
- [x] 2026-09-12 (M1) decision change: a bare `read` of a **literal** prints
  `ok (literal)`, not `ok <ref>` as the M1 Surface (J1) and the printing decision
  state, because a literal reference *is* its value and echoing it back leaks it.
  Real references and dotenv keys still confirm as themselves; `check` shows
  `literal` in the key column for the same reason. Raised by the M1 executor in
  PR #32 (Copilot round 1). Supersedes the `ok <ref>` wording for the literal case.
  Acknowledged by Karl 2026-09-12.
- [x] 2026-09-12 (M1) decision change: `kinfra` layers declared literal
  `[sandbox.secrets]` entries into the resolver context before resolving sibling
  references, matching `ksecret run`'s documented literals-first semantics, through a
  single shared `secrets.layered_env()` used by every mapping resolver. This refines
  the invariant "every existing `infra.toml` keeps resolving identically": resolution
  differs from before only where a declared literal entry's name collides with a
  variable a provider reads (e.g. a declared `OP_ACCOUNT` now reaches a sibling
  `op://` reference). For the collision the feature exists to serve this is the fix;
  `ksecret run` has carried the same exposure since M1 by design. Raised by the M1
  executor in PR #32. Acknowledged by Karl 2026-09-12.
- Deferred to feature close (M1): the `$NAME` shorthand claims any `$`-prefixed value
  as an environment reference (unchanged from the pre-feature resolver), so a literal
  like a bcrypt hash `$2b$...` in `[sandbox.secrets]` errors rather than passing
  through per A8; restricting the claim to valid variable-name syntax would instead
  turn typos like `$MY-VAR` into silent self-resolving literals. Karl chose to keep
  the current broad behaviour for M1 and revisit the grammar at feature close
  (2026-09-12). No change in this milestone.
