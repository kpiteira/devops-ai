# Quality Gates

Before completing any coding task, all of these should pass:

- **Unit tests** — run the configured test command; all tests pass
- **Quality checks** — run the configured quality command (if configured); no issues
- **Committed** — all changes committed with clear messages
- **No security vulnerabilities** — no credentials in code, no injection vectors, no OWASP top 10 issues
- **Handoff updated** — document learnings for the next task (see handoffs rule)

If quality gates fail, fix the issues before marking the task complete. A task with failing tests or quality warnings is not done.
