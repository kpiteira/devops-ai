# Vertical Slicing

Structure milestones as vertical slices, not horizontal layers. Each milestone should be E2E-testable and deliver user-visible value (or prove a critical architectural path).

## Vertical vs horizontal

Horizontal (problematic): "Phase 1: all database tables, Phase 2: all service layer, Phase 3: all API endpoints." Nothing is testable until everything is done. Integration bugs hide until the end.

Vertical (better): "Milestone 1: user can trigger one action end-to-end." Each milestone touches all necessary layers (DB, service, API) but only for the slice it delivers. Integration bugs surface early.

## Principles

- Each milestone builds on the previous one
- Each milestone has a concrete E2E test: given initial state, when user does X, then observable result Y
- Milestone 1 is the smallest thing that proves the architecture works — it doesn't need to be useful, just testable
- Later milestones add capabilities incrementally

## Why this matters

Vertical slices force integration testing at every milestone boundary. Horizontal layers defer integration to the end, where bugs are expensive to fix and hard to diagnose.
