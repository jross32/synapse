# AI routing and reliability

## Preferred tool ladder
1. Blender MCP semantic inspection (`get_*summary*`, object detail, missing files, docs search).
2. Blender MCP purpose-built render/navigation operations.
3. `execute_blender_code` for live `bpy` creation/editing when the live file is intentionally owned by the task.
4. `execute_blender_code_for_cli` or direct background Blender for deterministic saved-file validation and isolated transformations.
5. Reflex GUI input only for interactions that cannot be represented reliably through semantic tools; pair it with screenshots and do not infer hidden state from pixels.

## Reliability rules
- Separate live interactive mutation from independent CLI validation. A success response from the mutating process is not independent proof.
- Prefer idempotent scripts: use deterministic names/collections and check for existing owned objects before creating duplicates.
- Use explicit absolute source/output paths in automation. Never rely on Blender's current working directory for production output.
- Long Blender jobs can legitimately outlive an MCP/Reflex response window. Write durable receipts/artifacts, check the process/output independently, and avoid immediately launching duplicate work after a transport timeout.
- A transport 502/timeout is infrastructure evidence, not proof that Blender failed. Check outputs/processes before retrying.
- Keep an editable `.blend` source beside exported deliverables unless the task explicitly says otherwise.
- Treat Blender version/API drift as real. Query bundled API/manual docs or `bpy.app.version` when operators/enums differ; don't silently assume a prior version's identifier.

## Game asset handoff receipt
Record at minimum: source blend, export path/format, Blender version, asset names, unit/scale convention, applied/unapplied transforms/modifiers, material/texture policy, animations/actions, provenance, structural validation, visual evidence, export re-import result, downstream target, and known limitations.
