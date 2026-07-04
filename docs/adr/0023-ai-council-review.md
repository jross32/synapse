# ADR-0023: AI Council Review — a pre/post multi-perspective review gate for any AI working in Synapse

- **Status:** accepted
- **Date:** 2026-07-04
- **Deciders:** Justin (owner), Claude
- **Related contracts:** #11 (audit log), #12 (confirm-before-destructive); relates to ADR-0013 (autonomous boss), ADR-0018 (roles + personalities), ADR-0020 (case engine).

## Context

A single AI working alone is one voice checking its own work — it ships plausible-but-wrong plans and unreviewed bugs (the Synapse-vs-baseline benchmark demonstrated this: the single-pass build lost the "backend correctness" and "bug hunt" dimensions to two defects a reviewer would have caught). Synapse already has the *ingredients* for multi-perspective review — roles + personalities (ADR-0018), squads with handoffs, and the case-engine's "challenge" (minority-path) mode (ADR-0020) — but no **named, reusable workflow** that makes "consult a panel before and after meaningful work" the default way any AI operates in Synapse.

The owner asked for exactly this: before starting and after finishing meaningful work, the primary AI should present its plan / result to 2–10 relevant expert reviewers, get prioritized feedback, and revise before proceeding — like a conference-room review — whether or not a full squad is spun up.

## Decision

Ship **AI Council Review** as a first-class, launchable Synapse workflow plus a documented discipline binding on every AI coder:

- **`templates/quick-actions/ai-council-review.json`** — a launchable quick-action whose prompt runs the loop **Plan → Council → Build → Council → Verify**: a **pre-work council** (reviewers critique the plan) before implementing, and a **post-work council** (reviewers hunt bugs/gaps/regressions) before claiming done, with revise-and-repeat until the proof gate passes.
- **Adaptive reviewer count** (don't waste tokens): **2** tiny/simple · **3–5** normal feature/fix/doc · **6–10** only complex/risky/architectural/benchmark/security/automation/multi-system.
- **Reviewer lenses** (pick relevant ones): Architect, Skeptic, Tester/QA, Security/Safety, UX/UI, Performance/Token-Efficiency, Product Manager, DevOps/Release, MCP/Tooling, Documentation.
- **Token discipline:** bounded, prioritized findings only (**critical / important / optional**); no rambling; no duplicate criticisms; the primary AI **synthesizes**, it does not blindly follow every comment.
- **Mechanism-agnostic:** run it via a real Synapse squad (role + personality reviewers, handoffs) when available and appropriate; otherwise via the closest method (parallel reviewer sub-agents / separate reviewer prompts / a connected coder). The value is *independent expert perspectives + synthesis*, not a specific engine. (On Windows, squad launch depends on the multi-arg PTY fix tracked alongside this work; the fallback path makes the workflow usable regardless.)
- **Docs:** codified as a canonical pattern in `docs/MULTI-AI-WORKFLOW.md`, referenced from `AGENTS.md`, and surfaced on the roadmap (`docs/roadmap.json`).

This is **distinct from** the case-engine "challenge" mode of ADR-0020 (which spawns one minority-path *build* child): AI Council Review is a *review* gate wrapping any work, with multiple diverse lenses, applied pre- and post-work.

**Maturity (be honest):** v1 ships as a **launchable quick-action prompt + a workflow discipline** — the same class of artifact as the flagship `autonomous-boss` quick-action (a prompt + `default_argv`, no dedicated daemon engine). It is **not** a daemon endpoint or a bespoke "council engine," and it does not claim to be. This ADR file was **hand-authored for bootstrap** (rather than created via the `POST /projects/{id}/adrs` → promote REST lifecycle the workflows themselves use) because it defines that lifecycle's review discipline.

## Consequences

### Positive
- Multi-perspective review becomes the default, catching plan flaws and shipped bugs a single voice misses — dogfooded during this very session (real councils caught that a decision-audit grep would have missed ~66% of decisions, and that a commit was about to violate the repo's version-bump rule).
- Reusable + launchable by a human (Sessions quick-action) or an AI (`GET /api/v1/quick-actions` → launch), and mechanism-agnostic so it works even when squads can't launch.
- Token-disciplined by design (adaptive count + prioritized findings + synthesis).

### Negative / trade-offs
- A council costs extra tokens/time; mitigated by the adaptive count (2 for tiny tasks) and prioritized-findings-only output.
- v1 ships as a launchable prompt + discipline + squad/fallback mechanism, **not** a bespoke daemon "council engine." A native endpoint that orchestrates + persists councils is a possible future step (see follow-ups) — this ADR does not claim that exists yet.

### Follow-ups
- Code changes required: none for v1 (quick-action + docs). A native `POST /api/v1/council` orchestrator + persisted council records + reviewer-squad orchestration is a candidate future enhancement, **deferred until the Phase 2 squad-launch bug (Windows multi-arg `.CMD` spawn) is fixed** — until then the workflow runs reviewers as prompt passes rather than squad-workers.
- Docs to update: `docs/MULTI-AI-WORKFLOW.md` (canonical pattern), `AGENTS.md` (pointer), `docs/roadmap.json` (item), this ADR's index line in `docs/adr/README.md`.
- Migration plan: none (no contract broken).
