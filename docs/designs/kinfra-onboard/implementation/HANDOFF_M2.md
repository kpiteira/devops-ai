# Handoff — M2: kinfra-onboard skill

## Task 2.1 Complete: Create kinfra-onboard SKILL.md

**Approach:** Followed kworktree SKILL.md pattern (YAML frontmatter, sections, tables). Structured as 4 phases matching DESIGN.md and ARCHITECTURE.md specs. Error handling covers all SCENARIOS.md cases plus rollback on verification failure.

**Key patterns:** The skill tracks changed files through Phase 3 and only stages those explicitly in Phase 4 (never `git add -A`). OTEL endpoint for app config is `http://localhost:44317`; sandbox containers get the Docker-network endpoint via env var automatically.

**Next Task Notes:** Task 2.2 is VALIDATION — run `/kinfra-onboard` on khealth (`../khealth`). Ensure khealth has clean git state first. The skill calls `kinfra init --dry-run --auto` and `kinfra init --auto`, which were implemented in M1. Check that config.yaml OTEL endpoint gets rewritten and project.md gets Infrastructure section.

## Task 2.2 Complete: E2E validation on khealth

**E2E test: kinfra-onboard/khealth-validation — 5 steps — PASSED**

**Bug found and fixed:** `remove_depends_on()` in `compose.py` only handled short-form depends_on (`- service`). khealth uses long-form (`service: {condition: ..., required: ...}`), causing `docker compose config` to fail with "depends on undefined service 'jaeger'". Fixed by parsing both list-item and dictionary-key formats with child line grouping. Two new unit tests added.

**Gotcha:** khealth's `config.yaml` is gitignored (contains chat_id). The skill should detect gitignored files and report that OTEL config changes won't be committed — the user manages config.yaml locally.

**Gotcha:** khealth's project.md E2E Testing section references old local Jaeger ports (16686, 4317). The skill correctly identifies and updates these to shared stack ports (46686, 44317).
