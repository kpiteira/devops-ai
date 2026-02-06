# M3 Handoff

## Task 3.1 Complete: Add No-Config Behavior

**Changes were minimal** — M2 already had reasonable no-config paths. Enhancements:
- All 5 skills now have explicit "Would you like me to create a `.devops-ai/project.md`..." suggestion
- ktask, kmilestone, kdesign-impl-plan now note which sections will be skipped (infra/E2E)
- Question counts: kdesign/validate: 2, ktask/impl-plan: 3, kmilestone: 2 (all <=4)

**Next Task Notes (3.2 — config generation):**
- Add project inspection logic (pyproject.toml, package.json, Makefile, etc.)
- Goes in the Configuration Loading section of each skill
- Refer to `templates/project-config.md` for the template structure

## Task 3.2 Complete: Add Config Generation Capability

**Added "Generating Config (if user accepts)" subsection** to all 5 skills' Configuration Loading section. Same 4-step block in each: inspect project root, pre-fill, show draft, write after confirmation.

**Covers:** pyproject.toml (Python), package.json (Node/TS), Makefile, go.mod (Go), Cargo.toml (Rust)

**Next Task Notes (3.3 — partial config):**
- Handle case where `.devops-ai/project.md` exists but has missing/empty sections
- Essential vs optional values differ per skill (see SCENARIOS.md mapping)
- "Not configured" markers in template should be treated same as missing

## Task 3.3 Complete: Handle Partial Config

**Added partial-config handling** to the "file exists" path in all 5 skills:
- kdesign, kdesign-validate: all values essential — ask if missing/Not configured
- kdesign-impl-plan, ktask, kmilestone: essential values asked for, optional values (Infrastructure, E2E) skipped silently with brief note
- All 3 skills with optional values include "Do NOT offer to update the config file unless the user asks"

## Task 3.4 Complete: Verify Degradation Paths

**Traced all 6 scenarios through all 5 skills** (30 traces total):
- Scenarios 1-5 (full config, no config, partial essential, partial optional, no config + decline): All passed without gaps
- Scenario 6 (malformed config): **GAP FOUND** — no skill handled garbled/unrecognizable config files

**Fix applied:** Added malformed config handling line to step 2 of all 5 skills:
`If the file exists but is malformed (no recognizable sections, garbled content): suggest starting from the template at templates/project-config.md and fall back to the no-config path`

All 6 scenarios now pass across all 5 skills.
