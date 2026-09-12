# Product Glossary

This is a record of concepts the human has been taught and an agenda for future walkthroughs. It is
not an enforced vocabulary law.

| Concept | Working explanation | Where it appears | Last refreshed |
|---------|---------------------|------------------|----------------|
| Secret reference | A string like `op://vault/item/field` that names *where* a secret lives, safe to commit; the value is fetched at use time. | secret-providers SPEC, `[sandbox.secrets]` | 2026-09-07 |
| Provider | The pluggable piece that turns one reference scheme (`op://`, `bao://`, `akv://`, `dotenv://`, `env://`) into a value. One module each. | secret-providers SPEC, architecture test | 2026-09-07 |
| Type-named vs instance-named scheme | Type-named: the scheme says which *kind* of backend (`bao://`). Instance-named: the scheme is a user alias (`homelab://`) mapped per machine. Karl chose type-named; instance aliases are a non-goal. | secret-providers SPEC decision | 2026-09-07 |
| Dotenv fallback | A `$VAR` reference that is not exported is looked up in the project's `.env` file, the way docker compose does. Exported wins. | M1 brief | 2026-09-07 |
| Host-side resolution | Secrets are resolved on the developer's machine with their own credentials and injected into the process being started; the service never contacts a vault. The alternative, in-container resolution with a bootstrap credential, is a separate feature. | secret-providers SPEC outcome + non-goal | 2026-09-12 |
| Run semantics | `ksecret run … -- cmd`: resolve references into the child's environment and exec; nothing touches disk. Same shape as `op run`. | M1 brief, agent-memory | 2026-09-07 |
| Residency | Where resolved values live. kinfra sandboxes keep a 0600 `.env.secrets` in the slot dir (accepted trade-off: short-lived test environments); `ksecret run` keeps them in memory. | secret-providers SPEC invariants | 2026-09-07 |
