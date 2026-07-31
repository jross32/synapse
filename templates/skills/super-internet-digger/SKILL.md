---
name: super-internet-digger
description: Find, compare, verify, and - only when permitted - acquire public or user-authorized source code, releases, builds, documentation, and playable equivalents. Use for current-release research, GitHub or authenticated-repository discovery, mirror/provenance checks, source-vs-build distinctions, local run preparation, or evidence-backed acquisition plans. Use direct Synapse tools by default; Warden is an optional router and never a requirement. Never retrieve leaked material, bypass access controls, or treat an unverified mirror as authoritative.
---

# Super Internet Digger

Turn a vague "find the best/current source and make it usable" request into a fast, evidence-backed workflow. Optimize for verified primary sources, parallel discovery, early stopping, and a reproducible handoff.

## Start Here

1. Read `references/safety-and-sourcing.md` before researching proprietary, paid, private, or ambiguous material.
2. Run `python scripts/digger_pipeline.py plan --target "<target>" --goal both --tools "<available tool ids>"` to produce bounded parallel lanes.
3. Search primary sources first. Use direct GitHub, web, browser, and Web Scraper tools when available. Use Warden only as an optional tool router.
4. Store every candidate in the schema from `references/candidate-schema.md`.
5. Run `python scripts/digger_pipeline.py rank candidates.json` before selecting anything.
6. Separate permission to discover from permission to download and permission to execute.
7. Acquire only a candidate marked `acquisition_allowed: true`; stop for confirmation when `confirmation_required: true`.
8. After acquisition, run `python scripts/digger_pipeline.py inspect <project-dir>` and follow only the proposed commands the user has authorized.
9. Return the compact evidence ledger and exact reproduction steps.

## Fast Research Loop

### 1. Bound the request

Resolve these facts without inventing them:

- target name and publisher/owner
- desired artifact: source, build, playable web version, docs, SDK, or equivalent
- latest/current cutoff date
- public-only versus user-authorized private access
- destination and whether download or execution is authorized

If access is private, require a usable authorized path such as a private Git URL, signed-in browser session, or artifact portal. A statement like "I have access" is not itself a retrieval path.

### 2. Search in parallel, then stop early

Use three small lanes unless the target needs fewer:

- **Official lane:** owner site, official organization, release API, tags, changelog, store, docs.
- **Code lane:** canonical repository, release archives, package registry, authorized private source.
- **Alternative lane:** official SDK/modding surface, licensed community implementation, public playable equivalent.

Run lanes concurrently when tools allow. Stop expanding once all of these are true:

- one high-confidence primary candidate exists for each requested artifact kind
- version/tag and date are verified by a second independent signal
- license or access basis is explicit
- no unresolved safety blocker remains

Do not spend tool calls collecting many low-value mirrors after a primary source is proven.

### 3. Build an evidence ledger

Every material claim needs a source URL and observed fact. Keep separate records for:

- source code
- binary release
- web-playable build
- documentation or SDK
- authorized private source
- blocked or suspicious mention

Never merge "official game exists" into "official source exists." A useful outcome can be "no public source found; official build exists; here is the best allowed alternative."

### 4. Rank deterministically

Use the bundled ranker so provenance and safety outweigh convenience. Its output includes:

- policy blockers and confirmation gates
- duplicate collapse
- provenance, freshness, version, license, playability, and reproducibility scores
- one selected candidate per artifact kind

An unauthorized or leaked candidate remains metadata-only even if it would otherwise rank highly.

### 5. Acquire with a separate gate

Before any download, clone, extraction, dependency install, or launch:

- confirm `acquisition_allowed`
- obtain user confirmation where required
- pin a tag, release, commit, checksum, or immutable artifact identifier
- choose a deterministic destination
- record the exact command and result

Prefer official archives or a tagged checkout. Do not scrape rendered repository pages as a substitute for Git. Never bypass DRM, paywalls, authentication, or repository permissions.

### 6. Inspect before executing

Run the inspector after acquisition. It performs one bounded inventory pass and reports detected runtimes, confidence, evidence, lockfiles, and proposed install/run commands. It does not execute them.

Treat generated commands as a plan requiring normal approval. Prefer locked installs (`npm ci`, frozen lockfiles, pinned Python environments) and inspect project instructions before running third-party code.

## Tool Routing

Read `references/tool-routing.md` when several MCPs or browser tools overlap.

Default order:

1. purpose-built connector or official API
2. direct Git tooling for repositories
3. Web Scraper for site discovery, evidence capture, and docs
4. authenticated browser for a user-owned session
5. ordinary web search for discovery and cross-checks
6. Warden, if installed, to help locate a tool - not to hide or replace direct tools

If one route fails, record the failure and switch routes. Do not repeat the same failing call without changing the input or access path.

## Benchmark Discipline

Read `references/benchmark-contract.md` before claiming the Synapse workflow is faster or better.

- Compare against the current Codex skill using the same model, tools, network conditions, task prompt, and destination policy.
- Use at least five repeats per scenario and report medians plus variability.
- Score source correctness, freshness, provenance, licensing, safety, completeness, reproducibility, run readiness, elapsed time, tokens, tool calls, and cost.
- A candidate cannot win with a safety/provenance regression.
- Claim "4x faster" only when median elapsed time is at least four times lower.
- Claim "4x more efficient" only when quality per minute or quality per 1,000 tokens is at least four times higher while absolute quality does not decline.
- Never describe quality itself as "4x" unless the rubric defines a meaningful ratio with a nonzero baseline.

Use `python scripts/digger_pipeline.py compare baseline.json synapse.json` to calculate allowed claims from measured summaries.

## Output Contract

Return:

1. **Current status** - what exists as of a concrete date.
2. **Best candidate(s)** - separate source/build/web/docs records.
3. **Why selected** - primary evidence, version pin, license/access basis, and confidence.
4. **Safety state** - allowed, blocked, or awaiting confirmation.
5. **Local handoff** - path, commands proposed/executed, result, and remaining blocker.
6. **Evidence ledger** - source URL -> observed fact.
7. **Benchmark result** - only if a comparable measured run exists.

Keep the final answer compact; preserve full structured records as an artifact when the task is large.
