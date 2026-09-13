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
| Round packet | Everything a triage needs for one review round, in one `kreview round` call: findings (threads and suppressed comments) with provenance, reviewers' summaries, issue comments, and the mechanical signals. The model reads it; it never fetches. | review-loop-runtime SPEC, M1 brief | 2026-09-13 |
| Suppressed comment | A finding Copilot folds into its review body under `Suppressed comments (N)` instead of opening a thread. It carries a `path:line`, so it is line-anchored and counts for the second-order stop; on #49 8 of 9 late-phase findings were suppressed. | kreview 0.4.0, M1 brief | 2026-09-13 |
| Provenance boundary | The commit of the earliest submitted review still in the PR's history. A finding whose line blames to an ancestor of it is *original*; to a descendant, *review-fix*; anything else is *unknown* and never ends a loop. A rebase resets it. | kreview 0.4.0, M1 brief | 2026-09-13 |
| Second-order round | A round with **at least one** line-anchored finding, every one of them on a review-fix commit: the reviewer is reviewing the previous round, not the PR. The loop's last paid round. A round with no findings at all is *no-new-findings* instead — "every" on its own would make an empty round vacuously second-order. Counting suppressed comments changes where it fires (#27's sixth review is not one). | kbabysit 0.4.0, M1 brief | 2026-09-13 |
| Dispositions file | The model's decisions for one round, as JSON handed to `kreview apply`: per finding a verdict, isolated/systemic with root cause, and the reply or issue text. The tool posts, files, records, and decides from it. | M2 brief | 2026-09-13 |
| State block | The loop's ledger — rounds, findings, dispositions, stop — as JSON inside an HTML comment at the end of the PR's babysit report comment. Durable in the PR, readable by any seat; nothing on local disk. | M2 brief, decision D4 | 2026-09-13 |
| Re-entry | Any further round on a PR whose report is posted. Goes through `/kbabysit <n>` → `kreview status`, which says whether it is a `kselfreview` pass (only unreviewed commits) or a paid round, and `apply --reenter` starts a new run with a fresh budget and the inherited ledger. | kbabysit 0.4.0 §4, M2 brief | 2026-09-13 |
| Replay window | `--since`/`--until` on `round` and `apply --dry-run`: a past PR's history as a fixture, so a stop rule is measured on real data without buying a review. | M1/M2 briefs, decision D7 | 2026-09-13 |
