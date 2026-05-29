# L1 Build & Validation — Live Findings Log

**Started:** 2026-05-15
**Mode:** Iterative build → run on agent-memory → grade → iterate

---

## Iteration 0 — Initial Build (results)

L1 artifact mixed description with analysis (surprises, ADR stubs). Karl pushed back: L1 should be pure description; findings are a separate cognitive act. Spec was wrong; iteration 0 was a learning artifact.

Strong findings raised in iteration 0 surprises section:
- `MemoryService` god object
- No `MemoryStore` — writes scattered across ~40 files
- Architectural tests defend LLM seam but not memory seam
- Docker-on-docker blast radius (security relevance)
- Dialogue prompt embeds duplicated `AgentHome` layout

---

## Iteration 1 — L1 as pure description (results)

### Build changes from iteration 0

- L1 redefined as pure description (prose + 2 diagrams + table)
- Surprises section removed from L1 output
- ADR stubs removed from L1 output
- Findings moved to parallel `FINDINGS.md` catalog
- Modeler prompt: explicit altitude rules for the environment diagram (no implementation specifics)
- Conceptual Structure diagram added as required peer to the Environment diagram

### Run notes

- 3 modelers ran in parallel (~120–170s each). All passed rejection criteria.
- Synthesizer ran cleanly, 0 rejections, 6 disagreements flagged.
- **Bug:** subagents could not write to side-file paths. Side-files for findings were blocked by auto-mode classifier even though paths are inside this repo. Modelers inlined findings in their final messages instead. The orchestrator (me) had to write findings-modeler-N.md and FINDINGS.md manually. **This is an L1 spec/orchestration issue to fix in iteration 2.**

### Validation gate results

| Gate | Pass/Fail | Notes |
|---|---|---|
| 1. Karl-readable | **Deferred** | Awaiting Karl's read |
| 2. Altitude discipline | **Pass** | Environment diagram has no implementation specifics. Conceptual structure uses CamelCase, no package names. |
| 3. Reproducibility | **Deferred** | Single run; would need a second run on same SHA |
| 4. Honest uncertainty | **Pass** | 6 disagreements flagged, including high-value framing question (memory-with-dialogue-attached vs co-equal halves) |

### Regression observed (worth flagging to Karl)

Iteration 1's findings catalog has 11 entries, mostly **structural smells visible from file sizes**: god-class services.py, oversized scheduler.py, agent_home.py mixing concerns, undocumented HTTP surfaces, deprecated config path. All legitimate but obvious.

**What was lost from iteration 0:**
- "No `MemoryStore` — writes scattered across ~40 files" — iteration 0's strongest finding, missed entirely in iteration 1.
- Architectural tests defend LLM seam but not memory seam — missed.
- Docker-on-docker blast radius — missed.
- Dialogue prompt duplicates `AgentHome` layout — missed.

**Why?** Iteration 1's modeler prompts told modelers to *describe what is*, not *hunt for missing abstractions*. The findings side-file was framed as "if you notice something problematic, append". That's too passive — modelers found what they were looking at (big files) instead of looking for what's not there.

The discipline of pure description helped the description artifact (it's now clean and at the right altitude). But it weakened the findings catalog.

### What to do

Three options:

1. **Tighten the findings-side-file instructions in the modeler prompt.** Direct the hunt: "Look explicitly for: missing abstractions (concepts named in code or docs that don't actually have a single seam), god objects, doc/code drift, layering violations, security blast radius. File size alone is not a finding."
2. **Add a separate quick "missing-abstractions sweep" step in L1.** A modeler does pure description; a separate subagent (or step) explicitly grep-hunts for canonical violations.
3. **Accept that L1's findings will be surface-level; the deeper hunt is L4's job.** Trade-off: Karl waits longer to see his known pain in findings.

My lean: **option (1)**. Active hunt during L1 is cheap (modelers are reading code anyway). The L4 layer can refine severity and dimension tags. Iteration 2 would update the findings instructions and re-run.

### Iteration 1 — also worth noting

- 10 conceptual components in the final artifact (4–7 was the target). Synthesizer flagged this openly and kept the split because two modelers independently surfaced `BriefingComposer`, `ActionGate`, `Sentinel` as distinct. Probably right but at the edge of readable.
- All three modelers converged on the system being "durable mind + autonomous dialogue + safety observer". That's a sharper system-purpose framing than iteration 0 produced.
- The Conceptual Structure Diagram (new in iteration 1) is genuinely the artifact Karl was missing. Mermaid renders it cleanly.

### Side-file write bug

Subagents reported "harness blocked" the Write tool to `findings-modeler-N.md` paths. The parent agent (me) can write to those paths. Two hypotheses:
- Auto-mode classifier treats subagent writes differently from parent writes
- Subagents tried to use Bash to mkdir/touch and got blocked, then misread the failure

Workaround in this run: parent wrote the files. Fix in iteration 2: have modelers return findings inline as part of their final message (per the modeler prompt), and the orchestrator persists them. This is more reliable than relying on subagent writes.
