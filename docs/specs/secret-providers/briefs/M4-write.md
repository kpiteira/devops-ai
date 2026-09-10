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
  when `ksecret read <ref>` would now return that value. Provider behavior:
  - `dotenv://<path>#<KEY>` — sets or replaces `KEY` in the file; creates the file
    with mode 0600 if absent; other lines preserved byte-for-byte.
  - `bao://<mount>/<path>#<key>` — KV v2 write that sets `key` and preserves the
    secret's other keys (patch semantics).
  - `akv://<vault>/<secret>` — `az keyvault secret set`; a new version if the secret
    exists.
  - `op://<vault>/<item>/<field>` — creates the item with that field when the item
    does not exist; when it exists, exits 1 with a message stating that updating an
    existing 1Password item is not supported (see Non-goals).
  - `$VAR` / `env://` — exit 1: the host environment is read-only.
- `ksecret write` prints nothing on success; errors name the reference, never the
  value.

## Blocking

| Job | Planner-authored test | Observable proof |
|-----|-----------------------|------------------|
| J8 | `test_m4_write.py::test_write_then_read_dotenv` | Round-trip via a fresh dotenv file, mode 0600, existing lines preserved |
| J8 | `test_m4_write.py::test_write_then_read_openbao` | Round-trip against the dev container; a sibling key in the same secret survives |
| J8 | `test_m4_write.py::test_write_then_read_akv` | Round-trip against the real vault (same skip rules as M3); the test deletes what it wrote |
| J8 | `test_m4_write.py::test_write_op_creates_item` | A fresh 1Password item is created and reads back; the test deletes it (skips when `op` access is not granted — A3) |
| J8 | `test_m4_write.py::test_write_env_is_refused_and_value_never_in_argv` | `env://` write exits 1; while writing to dotenv, no process in the tree carries the value in its command line |
| — | `tests/architecture/test_secret_providers.py` | Shape unchanged |

Plus the standing gates: `make check` exits 0.

## Advisory

- `ksecret write --if-absent` (no-op when the secret exists) — what `agent create`
  actually wants on re-run.

## Invariants

- Secret values reach providers via stdin, environment, or 0600 temp files only —
  never argv (`op item create` accepts a JSON template file; `az keyvault secret set`
  accepts `--file`; OpenBao is HTTP).
- Read behavior of M1–M3 unchanged.

## Non-goals

- Updating an existing 1Password item: `op item edit` takes field values only through
  argv, which the invariant forbids; agent-memory references items by ID after
  creation, so create-only covers its use. Karl has flagged this argv-rule vs
  update-capability tension as an open cross-project question (spec A7); this
  milestone does not resolve it.
- Deleting or listing secrets.

## Context

- agent-memory's create flow: `op item create --vault <v> --category login --title
  <t> 'auth-token[password]=<value>' --format=json`, then stores
  `op://<vault>/<item-id>/auth-token` — note it uses the item *ID*, not the title,
  because titles collide with archived items. `ksecret write op://…` returning
  success is enough for it to store the reference it wrote.
- KV v2 patch: `PATCH /v1/<mount>/data/<path>` with header
  `Content-Type: application/merge-patch+json`; a plain `POST` replaces all keys.

## Decisions

- Value on stdin, not `--value` — the invariant, and Karl's standing rule that a
  token must never be materialized into argv.
- This milestone is optional: if it is not built, the feature closes without it and
  the spec records the omission — no amendment needed.

---

**If a stated fact is false, a decision conflicts with what's actually in the codebase,
or an acceptance test contradicts a job: stop and describe what you found. Don't comply,
and don't classify the problem yourself.**
