---
feature: secret-providers
milestone: M4
spec: ../SPEC.md
blocking: uv run pytest tests/acceptance/secret_providers/test_m4_write.py tests/architecture/test_secret_providers.py -q
---

# Brief 4 — write (optional)

## Jobs

- **J8** — When a tool generates a secret (agent-memory's `agent create` mints an
  auth token), it can pipe the value to `ksecret write <ref>` and later read it back
  with the same reference, so that provisioning code stores secrets without knowing
  the backend and without ever placing the value in argv.

## Surface

- `ksecret write <ref>` — value read from stdin (trailing newline stripped); exit 0
  when `ksecret read <ref>` would now return that value. On success stdout carries
  exactly one line: the **canonical reference** — identical to the input for
  `dotenv://`, `bao://`, `akv://`; for `op://` the item-ID form
  (`op://<vault>/<item-id>/<field>`), which is what a caller should store, since
  title references can collide with archived items. Never a value. Provider behavior:
  - `dotenv://<path>#<KEY>` — sets or replaces `KEY` in the file; creates the file
    with mode 0600 if absent; other lines preserved byte-for-byte.
  - `bao://<mount>/<path>#<key>` — KV v2 write that sets `key` and preserves the
    secret's other keys (patch semantics).
  - `akv://<vault>/<secret>` — `az keyvault secret set`; a new version if the secret
    exists.
  - `op://<vault>/<item>/<field>` — creates the item with that field when the item
    does not exist; sets the field when it does. Either way the value travels in a
    JSON template file (mode 0600, removed afterwards), never in argv.
  - `$VAR` / `env://` — exit 1: the host environment is read-only.
- Errors name the reference, never the value.

## Blocking

| Job | Planner-authored test | Observable proof |
|-----|-----------------------|------------------|
| J8 | `test_m4_write.py::test_write_then_read_dotenv` | Round-trip via a dotenv file whose full content afterwards is exactly the original lines with the one target replaced; a new file is created 0600; the canonical ref is echoed |
| J8 | `test_m4_write.py::test_write_then_read_openbao` | Round-trip against the dev container; the canonical ref is echoed; a sibling key in the same secret survives |
| J8 | `test_m4_write.py::test_write_then_read_akv` | Round-trip against the real vault (same skip rules as M3); the canonical ref is echoed; the test deletes what it wrote |
| J8 | `test_m4_write.py::test_write_op_creates_and_updates_item` | A fresh 1Password item is created; stdout is the item-ID reference; both the ID and title references read back; a second write updates in place; the test deletes the item (skips when `op` access is not granted — A3) |
| J8 | `test_m4_write.py::test_write_env_is_refused` | `env://` write exits 1 with a read-only message; nothing is printed |
| — | `tests/architecture/test_secret_providers.py` | Shape unchanged |

Plus the standing gates: `make check` exits 0.

## Advisory

- `ksecret write --if-absent` (no-op when the secret exists) — what `agent create`
  actually wants on re-run.

## Invariants

- Secret values reach providers via stdin, environment, or 0600 temp files only —
  never argv (`op item create` and `op item edit` accept `--template <json file>`;
  `az keyvault secret set` accepts `--file`; OpenBao is HTTP). This invariant is
  reviewed, not machine-checked: no acceptance test can observe another process's
  argv reliably.
- Read behavior of M1–M3 unchanged.

## Non-goals

- Deleting or listing secrets.

## Context

- agent-memory's create flow: `op item create --vault <v> --category login --title
  <t> 'auth-token[password]=<value>' --format=json`, then stores
  `op://<vault>/<item-id>/auth-token` — note it uses the item *ID*, not the title,
  because titles collide with archived items. `ksecret write op://…` returning
  success is enough for it to store the reference it wrote.
- The 1Password acceptance vault is `devops-ai-secrets-test` (Karl created it
  2026-09-12; override with `KSECRET_ACCEPTANCE_OP_VAULT`). The tests create and
  delete items titled `ksecret-acceptance-*` there and touch nothing else. Access is
  proven by querying the vault (`op item list --vault …`), which is also the access
  prompt Karl grants; `op whoami` is never used — it exits 1 on Karl's machine while
  `op` works (M1 divergence 2026-09-12). A skip is legitimate only when Karl declines
  the grant; a milestone whose only `op://` evidence is a skip is not delivered.
- KV v2 patch: `PATCH /v1/<mount>/data/<path>` with header
  `Content-Type: application/merge-patch+json` (verified against the dev image:
  sibling keys survive); a plain `POST` replaces all keys.
- `op`'s own help says "for sensitive values, use a template instead" of assignment
  arguments — for both `item create` and `item edit`. Editing by template means:
  `op item get <item> --format json` → modify the field in the JSON → `op item edit
  <item> --template <file>`; agent-memory references items by ID after creation.

## Decisions

- Value on stdin, not `--value` — the invariant, and Karl's standing rule that a
  token must never be materialized into argv.
- This milestone is optional: if it is not built, the feature closes without it and
  the spec records the omission — no amendment needed.

---

**If a stated fact is false, a decision conflicts with what's actually in the codebase,
or an acceptance test contradicts a job: stop and describe what you found. Don't comply,
and don't classify the problem yourself.**
