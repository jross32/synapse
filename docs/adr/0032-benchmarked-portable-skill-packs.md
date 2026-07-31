# ADR-0032: Benchmarked portable AI skill packs

- **Status:** accepted — shipped in v0.1.92
- **Date:** 2026-07-31
- **Deciders:** Justin (owner), Codex
- **Related:** ADR-0021 (AI Bundles), ADR-0023 (AI Council), ADR-0027 (AI-drivable Synapse), ADR-0029 (Warden), Contracts #4, #7, #8, #11, #13, #15, #25

## Context

Codex skills can provide strong reusable workflows, but a machine-local instruction folder is not a Synapse product: other runtimes cannot discover it through the daemon, users cannot install it from the Marketplace, and quality/performance claims have no shared evidence contract. Copying a skill into prompts would also waste tokens and drift from the installed version.

Justin wants Synapse to improve useful Codex workflows, beginning with Super Internet Digger, and to demand measured improvements across quality, safety, speed, tokens, tool calls, stability, and cost. The target is at least 4x where evidence supports it, without turning the target into an unearned claim.

## Decision

1. **Add a generic portable skill-package contract.** A child of `templates/skills/` carries `manifest.json`, `SKILL.md`, optional agent metadata, references, scripts, and an optional Synapse benchmark spec. The mechanism is not hard-coded to Super Internet Digger.
2. **Install immutable versions.** The daemon copies a package into `data/skill-packs/<id>/versions/<version>`, records its package SHA-256, and rejects changed bytes under an existing version. Updating package content requires a version bump.
3. **Keep packages declarative and non-executing.** Synapse validates and serves package files but never imports or runs their code. AIs may read a script as a resource or execute it only through their normal authorized runtime and permission gates.
4. **Make skills AI-discoverable.** REST and the local Synapse MCP list installed skill packs and read instructions/resources on demand. Spawned role prompts tell an AI where to discover skills. Direct MCPs and native tools remain available; a skill guides routing rather than replacing tools.
5. **Install through AI Bundles.** Bundles may own skill-pack assets, install their benchmark specs into the existing benchmark engine, and remove only their package files on uninstall. Benchmark definitions/results remain as durable evidence.
6. **Require benchmark contracts.** Same model, tools, access, prompt, machine/network, and at least five repeats are the default controls. Results score correctness, completeness, evidence, reproducibility, failure recovery, review burden, elapsed time, tokens, calls, retries, bytes/pages, cost, stability, and quality-adjusted efficiency.
7. **Gate claims.** Raw 4x speed, 4x time efficiency, and 4x token efficiency are separate claims. Each needs its own formula, non-inferior absolute quality, and zero critical permission/security/provenance regressions. Higher quality is reported as a point delta. Unfinished suites remain targets, not marketing claims.
8. **Ship Super Internet Digger v2 as the reference pack.** It separates discovery, acquisition, and execution permissions; searches primary/code/alternative lanes in parallel; ranks structured candidates deterministically; blocks leaked provenance; keeps Warden optional; and proposes polyglot run plans without executing them.

## Consequences

- Claude, Codex, Copilot, and connector-driven AIs can discover the same installed workflow without copying it into every session.
- Marketplace skill installs are reversible, versioned, hash-verifiable, and additive to the existing tool surface.
- A reusable benchmark template makes later Codex-skill improvements comparable instead of anecdotal.
- The first deterministic inspection benchmark can publish its narrow measured result while explicitly withholding a 4x claim for the uncompleted full internet/model workflow.
- Package authors must maintain versions and evidence artifacts when behavior changes; that overhead is intentional.
