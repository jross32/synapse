# Safety and sourcing rules

## Allowed

- Official public repositories, release archives, docs, SDKs, and intentionally public builds.
- Private repositories, portals, and artifact stores the user or their team is authorized to access.
- Licensed community implementations and compatibility layers.
- Metadata about suspicious candidates when needed to explain why they were rejected.

## Blocked

- Leaked or stolen source/assets.
- Private mirrors or credential dumps.
- Crack/torrent/DRM-bypass acquisition.
- Access-control, paywall, license, or authentication circumvention.
- Executing newly acquired code without the user authorizing execution.

## Three independent gates

1. **Discovery:** may inspect public metadata and user-authorized private metadata.
2. **Acquisition:** requires explicit provenance/license/access basis and any required confirmation.
3. **Execution:** requires separate authorization plus local inspection of commands and dependencies.

Never silently advance from one gate to the next.

## Supply-chain checks

- Prefer primary sources and immutable pins.
- Record repository owner, tag/commit, release date, license, and checksum when present.
- Compare the claimed latest version with official tags/releases rather than the default branch alone.
- Treat install scripts, binary releases, and dependency hooks as untrusted until inspected.
- Keep credentials in the user's existing connector, Git credential store, browser session, or Synapse secret store; never copy them into research artifacts or logs.
- If provenance remains ambiguous, retain the candidate as metadata, explain the blocker, and offer the safest useful alternative.
