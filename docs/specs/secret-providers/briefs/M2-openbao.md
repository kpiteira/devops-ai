---
feature: secret-providers
milestone: M2
spec: ../SPEC.md
blocking: uv run pytest tests/acceptance/secret_providers/test_m2_openbao.py tests/architecture/test_secret_providers.py -q
---

# Brief 2 — OpenBao provider

## Jobs

- **J6** — When a secret lives in an OpenBao or Vault KV v2 mount, a developer can
  reference it as `bao://<mount>/<path>#<key>` anywhere a reference is accepted
  (`ksecret read|run|check`, `[sandbox.secrets]`), so that Karl's homelab vault
  replaces 1Password for every project that runs there.

## Surface

- Reference: `bao://<mount>/<path…>#<key>` → the value of `key` in the KV v2 secret at
  `<mount>/<path>` (API path `/v1/<mount>/data/<path>`, current version). Missing
  `#key` → error naming the reference; key absent from the secret → error naming the
  key, never listing other values.
- Server address: `BAO_ADDR`, else `VAULT_ADDR`; absent → error telling the user to
  export one.
- Token: `BAO_TOKEN`, else `VAULT_TOKEN`, else the contents of `~/.vault-token`;
  absent → error telling the user how to log in (`bao login`). A 403 → the same
  guidance; a connection failure → an error naming the address.
- No `bao` binary is required: with only an address and a token exported, `ksecret
  read bao://…` works on a machine without the CLI.
- The README's Secrets section documents the scheme, the two env vars, and the token
  file.

## Blocking

| Job | Planner-authored test | Observable proof |
|-----|-----------------------|------------------|
| J6 | `test_m2_openbao.py::test_read_kv2_secret_from_dev_server` | Against a dev-mode `openbao/openbao` container started by the test, a secret written via HTTP reads back through `ksecret read bao://secret/<path>#<key>` |
| J6 | `test_m2_openbao.py::test_token_file_fallback_and_missing_key` | With the token only in a `HOME/.vault-token`, `read` succeeds; a wrong `#key` → exit 1, stderr names the key, no other value leaks; a reference with no `#key` → exit 1, nothing leaks; no token anywhere → exit 1 with login guidance |
| J6 | `test_m2_openbao.py::test_run_and_check_accept_bao_refs` | `run` injects the value; `check` reports `ok` without the value |
| J6 | `test_m2_openbao.py::test_readme_documents_bao` | README names `bao://`, `BAO_ADDR`, `BAO_TOKEN`, and the `.vault-token` file |
| — | `tests/architecture/test_secret_providers.py` | The provider is one new module; no other module names it |

Plus the standing gates: `make check` exits 0.

## Advisory

- A `bao://…` reference in `[sandbox.secrets]` of a kinfra project — covered by M1's
  shared-resolver contract; a smoke run against the dev server is worth a minute, not
  a session.
- KV v1 mounts: out of scope unless trivial.

## Invariants

- No new `[project.dependencies]` entry — HTTP via the standard library.
- Secret values never appear in argv, logs, or errors.
- M1 behavior unchanged.

## Non-goals

- Vault auth methods other than a token (AppRole, OIDC, `bao login` itself).
- Namespaces (enterprise Vault).

## Context

- OpenBao dev mode: `docker run -e BAO_DEV_ROOT_TOKEN_ID=<token> -p <port>:8200
  openbao/openbao` serves HTTP on 8200 with KV v2 at `secret/`; `GET /v1/sys/health`
  returns 200 when ready. The acceptance test uses exactly this.
- KV v2 read: `GET /v1/<mount>/data/<path>` with header `X-Vault-Token`, response
  `{"data": {"data": {<key>: <value>}, "metadata": …}}`.
- Karl's production instance: `BAO_ADDR=https://vault.home.mynerd.place`, token file
  `~/.vault-token` (mode 0600), KV v2 at `kv/`, paths `kv/homelab/<host>/<item>`.
  Unreachable off the homelab network — the acceptance tests do not touch it.
- OpenBao's own CLI honors `BAO_*` first, then `VAULT_*`; the provider mirrors that
  precedence so `bao` and `ksecret` agree on which server they talk to.

## Decisions

- Token precedence `BAO_TOKEN` > `VAULT_TOKEN` > `~/.vault-token` (the file is what
  `bao login` writes).
- HTTP with `urllib` rather than the `bao` CLI: consumers in containers (agent-memory)
  should not need a second binary to read one value.

---

**If a stated fact is false, a decision conflicts with what's actually in the codebase,
or an acceptance test contradicts a job: stop and describe what you found. Don't comply,
and don't classify the problem yourself.**
