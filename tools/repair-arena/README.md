# Repair Arena

Repair Arena is the Synapse-native bridge between App Doctor and Agent Arcade.

It gives every AI connected to Synapse one stable workflow:

1. Resolve a registered Synapse project to its real repository path.
2. Run App Doctor's read-only repository scan.
3. Discover bounded test plans without executing project-controlled code.
4. Package findings/evidence into a repair challenge.
5. Run competing Repair Architect, Test-First Builder, and Failure Critic strategies in Agent Arcade.
6. Persist the tournament in Agent Arcade history and return the winner, scoreboard, and winning plan.

## Safety contract

The default Repair Arena pass is planning-only. It does not modify the target repository, execute target project tests, run target project code, or auto-merge a candidate. The returned promotion gate requires isolated implementation plus tests/browser evidence and a post-fix App Doctor re-scan before promotion.

`demo` mode is deterministic/local strategy simulation. `gemini` mode may call the external Gemini runtime through Agent Arcade and therefore depends on runtime availability/quota.

## CLI

```powershell
python tools/repair-arena/controller.py check
python tools/repair-arena/controller.py run --project app-doctor --rounds 2 --mode demo
```

The controller writes one JSON object to stdout so Synapse UI actions and AI clients can consume it reliably.

## AI surface

Repair Arena is also exposed directly by the Synapse MCP connector as `synapse_repair_arena`, so connected AI clients do not need to know the controller path, App Doctor port, Agent Arcade port, or either app's internal API.
