# Handoff — M2: kinfra-onboard skill

## Task 2.1 Complete: Create kinfra-onboard SKILL.md

**Approach:** Followed kworktree SKILL.md pattern (YAML frontmatter, sections, tables). Structured as 4 phases matching DESIGN.md and ARCHITECTURE.md specs. Error handling covers all SCENARIOS.md cases plus rollback on verification failure.

**Key patterns:** The skill tracks changed files through Phase 3 and only stages those explicitly in Phase 4 (never `git add -A`). OTEL endpoint for app config is `http://localhost:44317`; sandbox containers get the Docker-network endpoint via env var automatically.

**Next Task Notes:** Task 2.2 is VALIDATION — run `/kinfra-onboard` on khealth (`../khealth`). Ensure khealth has clean git state first. The skill calls `kinfra init --dry-run --auto` and `kinfra init --auto`, which were implemented in M1. Check that config.yaml OTEL endpoint gets rewritten and project.md gets Infrastructure section.
