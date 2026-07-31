# Portable Synapse skill packs

Each child folder with a `manifest.json` is a versioned skill pack. The daemon discovers the package, validates its `SKILL.md`, installs it into a versioned data directory, exposes it through REST and MCP, and optionally seeds Synapse's benchmark engine from the declared benchmark spec.

This is intentionally generic. `super-internet-digger` is the first package, not a hard-coded special case. Future Codex skills can use the same path:

1. Snapshot the current skill as the baseline and record its content hash.
2. Scaffold a portable package with `SKILL.md`, `agents/openai.yaml`, focused references/scripts, and `manifest.json`.
3. Add a benchmark spec using `benchmark-template.json` as a checklist.
4. Compare the same model, tools, access, prompts, machine, and repeat count.
5. Score quality, safety, speed, tokens, tool calls, failures, stability, and cost.
6. Reject any headline claim when quality falls or a safety/provenance gate fails.
7. Publish measured claims with scope; leave unmeasured targets labeled as targets.

Package versions are immutable. If package bytes change, bump the package version before reinstalling.

Direct MCP servers and native tools remain available after a skill pack is installed. A skill guides routing; it does not replace or disable the underlying tools.
