---
feature: secret-providers
milestone: M3
spec: ../SPEC.md
blocking: uv run pytest tests/acceptance/secret_providers/test_m3_azure_key_vault.py tests/architecture/test_secret_providers.py -q
---

# Brief 3 — Azure Key Vault provider

## Jobs

- **J7** — When a secret lives in an Azure Key Vault, a developer logged in with `az`
  can reference it as `akv://<vault-name>/<secret-name>` anywhere a reference is
  accepted, so that cloud-deployed projects (khealth) share one secret source between
  deployment scripts and local sandboxes.

## Surface

- Reference: `akv://<vault-name>/<secret-name>` → the current version's value;
  `akv://<vault-name>/<secret-name>/<version>` → that version.
- Auth: whatever `az` is logged in as. A missing secret → exit 1, stderr names the
  reference and says not found. (Distinguishing not-logged-in and forbidden with
  tailored guidance is advisory: those states cannot be produced by an acceptance
  test without logging the developer out.)
- Works with `ksecret read|run|check` and `[sandbox.secrets]` through the shared
  resolver.
- README documents the scheme and that `az login` is the only prerequisite.

## Blocking

| Job | Planner-authored test | Observable proof |
|-----|-----------------------|------------------|
| J7 | `test_m3_azure_key_vault.py::test_read_secret_from_real_vault` | A secret the test sets with `az keyvault secret set` reads back via `ksecret read akv://…`; the test deletes it afterwards. Skips unless `az account show` succeeds and `KSECRET_ACCEPTANCE_AKV_VAULT` is set |
| J7 | `test_m3_azure_key_vault.py::test_versioned_reference_reads_that_version` | Two versions written; the bare reference reads the newest, `…/<version>` reads the pinned one |
| J7 | `test_m3_azure_key_vault.py::test_missing_secret_names_ref_not_value` | Unknown secret name → exit 1, stderr names the reference and says not found |
| J7 | `test_m3_azure_key_vault.py::test_run_and_check_accept_akv_refs` | `run` injects the value; `check` reports `ok` without it |
| J7 | `test_m3_azure_key_vault.py::test_readme_documents_akv` | README names `akv://` and `az login` |
| J7 | `test_m3_azure_key_vault.py::test_akv_is_a_provider_module` | Exactly one provider module owns the `akv://` literal |
| — | `tests/architecture/test_secret_providers.py` | One new module; nothing else names it |

Plus the standing gates: `make check` exits 0.

## Advisory

- Tailored guidance for `az` not logged in (`az login`) and for access denied,
  classified from `az` stderr — worth doing, not testable without logging out.
- Reading via the REST API with a token from `az account get-access-token` instead of
  one `az keyvault secret show` per secret — faster for many secrets, worth it only if
  it stays dependency-free.

## Invariants

- No new `[project.dependencies]` entry — no Azure SDK.
- Secret values never appear in argv, logs, or errors (`az … --query value -o tsv`
  returns the value on stdout; it must not be echoed).
- M1 and M2 behavior unchanged.

## Non-goals

- Service-principal or managed-identity auth configured by ksecret itself — `az login`
  in any mode is the user's job.
- Other clouds.

## Context

- khealth's `infra/scripts/seed-secrets.sh` already uses `az keyvault secret
  show --vault-name <v> --name <n> --query value -o tsv` and `secret set`; that is the
  known-working invocation shape on Karl's machine.
- `az` exit codes: not logged in and not found both exit 1 — the failure class must
  come from stderr text (e.g. `SecretNotFound`, `Forbidden`, `Please run 'az login'`).
- The acceptance vault: **directive — human:** Karl provisions a Key Vault in his
  tenant for this purpose (a separate task, not part of this milestone) and sets
  `KSECRET_ACCEPTANCE_AKV_VAULT=<name>` in the environment before M3 runs; the test
  creates and deletes secrets prefixed `ksecret-acceptance-` and touches nothing
  else. Until the variable is set the vault tests skip, and a milestone whose only
  evidence is skips is not delivered (A2).
- Soft-delete: a deleted AKV secret name stays reserved until purged; the test uses a
  fresh random suffix per run, so purging is not needed.

## Decisions

- Shell out to `az` (like `op`), rather than REST + `az account get-access-token`:
  one code path, no token handling, ~1–2 s per secret is acceptable for sandbox
  provisioning.

---

**If a stated fact is false, a decision conflicts with what's actually in the codebase,
or an acceptance test contradicts a job: stop and describe what you found. Don't comply,
and don't classify the problem yourself.**
