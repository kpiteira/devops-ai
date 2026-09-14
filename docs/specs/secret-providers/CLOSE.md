# Feature close - secret-providers

**Intent spec:** `docs/specs/secret-providers/SPEC.md`  
**Feature diff:** `887dfa8...6edc786` — spec PRs #29, #30, #76, #78; milestone PRs #32 (M1),
#51 (M2), #49 (M3), #70 (M4); class fixes #62 (#58, child-environment encoding) and #67
(#60, `akv://` name validation)  
**Pass:** first  
**Verdict:** CONFORMS

Fresh Fable session, 2026-09-14; no part of the feature was planned or built here.

## Intent assessment

The intent paragraph makes five promises, and the merged code keeps each one:

- **devops-ai stops requiring 1Password.** Five providers ship (`env://`/`$VAR`,
  `dotenv://`, `op://`, `bao://`, `akv://`); nothing in `src/`, `install.sh` or the
  README requires `op`. `kinfra init` auto-detects a newcomer's variables as `$VAR`
  references and its `--check` hint names `dotenv://`.
- **One resolver for `ksecret` and kinfra.** `provision.py` imports the resolver and
  names no scheme; the architecture gate (47 tests, green at `6edc786`) pins that a
  provider is one module nothing else names.
- **A newcomer adopts with only a `.env`.** Measured below: `$VAR` falls back to the main
  repo's gitignored `.env`, `dotenv://` reads it, `kinfra impl` writes a 0600
  `.env.secrets`.
- **Outgrowing plain text changes a reference string, not tooling.** Measured below: the
  same project's `.env.secrets` is byte-identical after its references move to OpenBao
  and then to Azure Key Vault, with no other edit.
- **Any project that installs devops-ai gets the client.** `ksecret` is a second console
  script of the package. The README's claim that re-running `./install.sh` (a plain
  `uv tool install -e`, no `--reinstall`) picks it up was measured in an isolated
  `UV_TOOL_DIR`: base commit installs `kinfra` only; after overlaying `HEAD` on the same
  path the same command reports `Installed 2 executables: kinfra, ksecret` (uv 0.12.13).

Every listed outcome and invariant was already checked per milestone (observer runs:
M1 15 passed / 0 skipped with the `op://` row live; M4 9 passed with `op://` and
`akv://` live). No new runtime dependency: `pyproject.toml` still declares typer, rich,
ruamel.yaml.

## Adversarial angle

**Angle:** the blocking tests prove each provider in isolation. None drives one
project's secrets through the *migration* the intent is named for, and none runs the
lifecycle past first provisioning into rotation and revocation. This review did, in the
executor's runtime (macOS host, Docker 29.7.2, `openbao/openbao:2.5.4` dev container,
the real `kv-devops-ai-accept` vault), through the shipped console script and the
in-process `impl_command` / `sandbox_start_command`, with a stub `agent-deck` on PATH.
One run, 17 s, every step measured (drive script kept out of the repository):

| Step | What was driven | What it showed |
|------|-----------------|----------------|
| A | Throwaway project: gitignored `.env`, `[sandbox.secrets]` with `$API_KEY`, `dotenv://.env#DB_PASSWORD`, a `postgres://` literal and a literal `BAO_ADDR` sibling; `API_KEY` not exported | `ksecret check --infra` → `ok / ok / literal / literal`, exit 0; `kinfra impl` → `.env.secrets` 0600 holding both values and the literal; no value in any output |
| B | Migration with the CLI alone: `ksecret read --print … \| ksecret write bao://secret/<path>#KEY` for both keys; `write --if-absent` again with a different value | Both stored, sibling keys preserved (KV v2 patch); `--if-absent` left the value alone and echoed the reference |
| B | Only the two reference strings in `infra.toml` changed to `bao://`; `sandbox start --refresh-secrets` | `.env.secrets` **byte-identical** to step A |
| C | Rotate `API_KEY` in OpenBao; `sandbox start` without and with `--refresh-secrets` | Without: file unchanged (materialised secrets are reused — the PR #27 semantic, not this feature's); with: the rotated value is in the file |
| D | agent-memory's `.env.prod` shape: `OP_ACCOUNT=…` and `BAO_ADDR=…` as literal lines, the token as a reference; `BAO_ADDR` deliberately **not** exported; `ksecret run --env-file .env.prod -- python3 -c … ; exit 7` | Child saw the resolved token and both literals; exit code 7 propagated; directory listing unchanged; `ksecret check --env-file` → `ok` + literals |
| E | Same value stored with `ksecret write akv://kv-devops-ai-accept/ksecret-close-…`; `--if-absent` again; `infra.toml` swapped to the `akv://` reference; refresh; secret deleted afterwards | `.env.secrets` byte-identical to the OpenBao-backed file |
| F | Token revoked (`BAO_TOKEN` wrong): `ksecret run … -- touch marker`; then `sandbox start --refresh-secrets` | `run`: exit 1, marker absent, stdout empty, stderr names the key (`AGENT_MEMORY_AUTH_TOKEN: The server refused the token for bao://… (HTTP 403)`); sandbox: non-zero, message names both keys, the previous `.env.secrets` intact |

No secret value appeared in any *diagnostic* output across the run — no status line, error
message or log, at the CLI or at the sandbox. The one place a value reached a stdout is the
deliberate `ksecret read --print` of steps B and E, piped straight into `ksecret write`: that
is the opt-in print path the spec makes explicit, and nothing rendered it to a terminal.

Not exercised here: `op://` reads and writes, which need Karl's touch. Their last live
evidence is the observer's runs at the M1 and M4 heads, cited above.

## Material findings

| Finding | Intent / outcome / invariant affected | Evidence | Resolution |
|---------|---------------------------------------|----------|------------|
| None. | — | Drive above; architecture gates; install measurement | — |

## Corrective milestones

None. The `$NAME` grammar change is a decided follow-up (amendment 2026-09-14,
issue #80), not drift; the spec stays `closing` until it lands and the second close
review confirms.

## Decisions deferred to this close

Two items the spec explicitly parked for feature close. Neither is drift; each is
Karl's call and, if changed, a small follow-up PR with a planner-authored test rather
than a corrective milestone.

**1. The `$NAME` shorthand claims any `$`-prefixed string** (M1 amendment, deferred
2026-09-12). Measured at `6edc786`: `$2b$12$…` (a bcrypt hash literal) → `error —
Environment variable 2b$12$… not set`; `$MY-VAR` → `error — Environment variable MY-VAR
not set`. There is no way to spell such a literal in `[sandbox.secrets]` today except by
moving it to a `dotenv://` file.

- (a) Keep as shipped. Every `$…` is a reference; a `$`-leading literal goes in a file.
- (b) Claim only a string that is exactly `$` + a valid name (`[A-Za-z_][A-Za-z0-9_]*`).
  `$2b$12$…` becomes a literal; so does `$MY-VAR`, silently — the reason it was deferred.
- (c) **Recommended.** Claim a string whose character after `$` could start a POSIX
  name (letter or underscore) and refuse it by name when the rest is malformed; a `$`
  followed by anything else (`$2b$…`, `$1`, `$(…)`) is a literal, because no variable
  can begin that way. `$MY-VAR` still errors, now with a message that says why;
  `$2b$12$…` passes through per A8; `check` labels it `literal`. Changes the M1 Surface
  row for `$NAME`; a replan of that row plus one acceptance case, and an executor PR.

Human decision (Karl, 2026-09-14): **(c)**. Recorded as the 2026-09-14 amendment; M1's
`$NAME` row and blocking tests are updated on the close branch (the new test and the
J4 addition both measured failing on main `6edc786` for the right reason).
Implementation is issue #80 — an Opus executor PR gated by M1's blocking command. The
archive waits for it.

**One refinement inside (c) — the planner's, not Karl's.** The option as offered above
begins the claim at a letter or underscore. As amended, `{` is claimed too: `${HOME}`
is refused by name ("braces are not part of the shorthand; write $NAME or env://NAME")
rather than passing through as a literal, because it is the likeliest misspelling of a
real reference. `$HOME/.config` is refused the same way. SPEC.md, the M1 grammar row
and `test_dollar_shorthand_claims_only_names` all carry the three-character claim set
(letter, `_`, `{`); (c) above is left as it was put to Karl. **For Karl on this PR:**
say if you want `${…}` treated as a literal instead — one Surface row and one test line.

**2. A `ksecret write op://…` update loses a passkey on the target item** (M4, #70:
"revisit at feature close"). An update sends the whole fetched item back as the template;
the `op` JSON cannot represent a passkey, so nothing at that seam can detect one.

- (A) **Recommended.** Keep as shipped: the README says to write to items that hold
  machine credentials, not ones a person signs in with. The failure needs an operator to
  point a provisioning tool at their own login item, and the named consumer
  (agent-memory) creates with `--if-absent` and never updates a foreign item.
- (D) A guard that *is* detectable: tag items `ksecret write` creates, and refuse to
  update an untagged item without an explicit flag. Cost: every item created before the
  tag (agent-memory's existing ones) needs the flag or a one-time tagging.

Human decision (Karl, 2026-09-14): **keep as shipped**. Noted on the M4 amendment.

## Outside the outcomes

- Multi-line values (PEM keys) cannot reach a sandbox: `.env.secrets` is `KEY=value`
  with no escapes, and the writer raises a bare traceback — issues #50 and #52. The
  choice (refuse with a message, or materialise such secrets as mounted files) is a
  feature, not a fix.
- A `$` inside a resolved value is interpolated away by compose between `.env.secrets`
  and the container (`HASH=$2b$12$abcdef` reaches the service as `$2b$12`; `p$w` as `p`),
  measured in a running container with Docker 29.7.2 — issue #81. Pre-existing, every provider; the same
  file-format family as #50/#52.
- A NUL byte crashes two paths with a traceback rather than a named refusal: in an
  `op://` reference (#53) and in a resolved value handed to `ksecret run` (#64).
- Text I/O elsewhere in `src/` (`compose.py`, `registry.py`, `sandbox.py`) still uses
  the locale codec and dies under `LC_ALL=C` — #65; the secrets package is clean.
- Two concurrent `ksecret write dotenv://…` to different keys of one file lose one
  update silently — #73; a stated limitation, `flock` is the house pattern if it goes.
- `ksecret read` takes no `--env-file`, so a single read cannot use an `OP_ACCOUNT` line
  from the file beside the reference; a consumer exports it first (agent-memory already
  does). Worth a flag if the migration wants one command.
- The pilot's note "announce before resolving 1Password references and batch the
  approvals" (REVIEW.md, 09-01/08/11) was pointed at this feature's `op://` provider and
  never became an outcome; the provider still resolves one reference per `op` process
  with no announcement. Kinfra-side friction, unchanged.
- `docs/designs/sandbox-provisioning/DESIGN.md` still describes the three-form resolver
  and says "Not replacing 1Password"; it needs a superseded-by header pointing at this
  spec's archive.
- On the machine this ran on, `uv tool list` shows `devops-ai` with `kinfra` only:
  the one-time reinstall the README asks for has not been run there yet.
- agent-memory's migration (its `op run` / `op read` / `op item create` calls, and the
  value-in-argv `op item create` noted in A7) is the next consumer feature, in that repo;
  the `.env.prod` shape it depends on is measured in step D above.

## Acceptance-test disposition

Recommendation per test. **Karl, 2026-09-14: every row as recommended** — said of the table as it
stood that day; the one row added since is marked pending below rather than signed on his behalf.
Suites are promoted by what they need:
nothing but the console script → `integration`; Docker → `integration` (the suite
already skips without a daemon, PR #44); a human grant or a real cloud vault → `e2e`
(manual, skips otherwise); already covered by a standing gate → `drop`.

| Milestone | Scoped test | Promote to (e2e / integration / unit / drop) | Human decision |
|-----------|-------------|----------------------------------------------|----------------|
| M1 | `test_read_env_dotenv_and_literal` | integration | as recommended |
| M1 | `test_read_failure_names_ref_not_value` | integration | as recommended |
| M1 | `test_read_without_print_confirms_only` | integration | as recommended |
| M1 | `test_dollar_shorthand_claims_only_names` | integration | **pending** — the row postdates the 2026-09-14 decision (added with this PR) |
| M1 | `test_read_op_reference` | e2e (needs a 1Password grant) | as recommended |
| M1 | `test_run_injects_resolved_env_without_disk` | integration | as recommended |
| M1 | `test_run_refuses_when_any_ref_fails` | integration | as recommended |
| M1 | `test_check_reports_without_values` | integration | as recommended |
| M1 | `test_kinfra_sandbox_resolves_dotenv_and_env_fallback` | e2e (Docker + slot lifecycle) | as recommended |
| M1 | `test_help_lists_the_three_commands` | integration | as recommended |
| M1 | `test_providers_package_is_in_place` | drop (the architecture gate no longer needs its skip guard) | as recommended |
| M1 | `test_readme_documents_every_scheme` | unit — fold the three README tests into `tests/architecture/test_docs_hygiene.py` | as recommended |
| M2 | `test_read_kv2_secret_from_dev_server` | integration (Docker, skips without it) | as recommended |
| M2 | `test_token_file_fallback_and_missing_key` | integration | as recommended |
| M2 | `test_run_and_check_accept_bao_refs` | integration | as recommended |
| M2 | `test_bao_is_a_provider_module` | drop (architecture gate covers it) | as recommended |
| M2 | `test_readme_documents_bao` | unit (with the M1 README test) | as recommended |
| M3 | `test_read_secret_from_real_vault` | e2e (real Key Vault) | as recommended |
| M3 | `test_versioned_reference_reads_that_version` | e2e | as recommended |
| M3 | `test_missing_secret_names_ref_not_value` | e2e | as recommended |
| M3 | `test_run_and_check_accept_akv_refs` | e2e | as recommended |
| M3 | `test_akv_is_a_provider_module` | drop (architecture gate covers it) | as recommended |
| M3 | `test_readme_documents_akv` | unit (with the M1 README test) | as recommended |
| M4 | `test_write_then_read_dotenv` | integration | as recommended |
| M4 | `test_write_then_read_openbao` | integration (Docker) | as recommended |
| M4 | `test_write_then_read_akv` | e2e | as recommended |
| M4 | `test_write_op_creates_and_updates_item` | e2e (needs a 1Password grant) | as recommended |
| M4 | `test_write_env_is_refused` | integration | as recommended |

The shared `conftest.py` splits with them: `ksecret()`, `clean_env()`, `bao` go with
the integration set; `op_item`, `akv` with the e2e set.

## Archive sweep

`grep -rn "secret-providers\|secret_providers"` outside the spec and acceptance
directories, 2026-09-14. Must follow the move:

- `ROADMAP.md:52` — cites `docs/specs/secret-providers/`; becomes the archive path.
- `ROADMAP.md:66` — "### secret-providers (in flight)" with M2/M3/M4 unchecked; the
  feature is delivered, the machine-credential line stays as backlog.
- `docs/specs/secret-providers/divergences/M1-2026-09-12.md:3-4,10,19` — absolute-style
  paths to the brief and the acceptance conftest; moves with the directory, paths
  updated to the archive and the promoted test locations.
- `tests/integration/conftest.py:7` — names "the secret-providers acceptance conftest";
  stale once the fixtures are promoted.

Name-only mentions that need no change: `docs/specs/GLOSSARY.md` (rows cite
"secret-providers SPEC"), `docs/specs/v2-pilot-synthesis/SPEC.md:74,91`,
`docs/EVOLUTIONS.md:23`, `docs/designs/v2-contract/REVIEW.md:169`,
`skills/kobserve/SKILL.md:41`, `tests/architecture/test_secret_providers.py` (docstring
and a skip reason).
