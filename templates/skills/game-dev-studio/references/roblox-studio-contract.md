# Roblox Studio Evidence Contract

## Evidence ladder
1. Preserve dirty/concurrent work.
2. Run static/tooling gates.
3. Build with Rojo.
4. Run real Studio server/client behavior.
5. Exercise ordinary player input for human-play claims.
6. Inspect real visuals for scene/UI/mobile claims.
7. Rerun meaningful routes when timing/nondeterminism is plausible.

## Human-input rules
- No teleporting to route checkpoints for a normal-player acceptance claim.
- No direct inventory/currency/progression mutation to satisfy the audit.
- Observe real ProximityPrompt or UI activation where production uses it.
- Record movement/running evidence.
- Use state-aware checkpoints between route legs.
- Corrective movement retries are acceptable and should be logged.

## Mobile rules
A device preset is configuration, not proof. Record actual `CurrentCamera.ViewportSize`. Scripted geometry checks do not replace visual inspection for broad UI-quality claims.

## Timeout classification
- `game-failure`: in-engine audit completed with a failing contract.
- `studio-timeout`: the in-engine audit exceeded its own deadline.
- `executor-timeout`: the outer control channel killed Studio before the in-engine result.
- `launch-failure`: Studio never reached the audit launcher marker.

Never convert an executor timeout into a game pass or product defect. Prefer detached launch plus correlated log polling when needed.

## Multiplayer rules
Use the requested number of real Studio clients and verify server authority plus intended shared-vs-player-specific state.

## Reuse rule
Promote reusable Roblox reliability lessons into Game Dev Studio and/or the Roblox Game Dev Pack.
