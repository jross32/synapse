# Live Studio event contract

The Game Studio UI must be driven by durable events produced by real work. The renderer may summarize, group, animate, or visualize these records, but must not claim a tool/action/result that did not happen.

Default project event log: `.synapse/game-dev-events.jsonl`.

Each line is one JSON object:

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "timestamp": "2026-08-27T20:58:12.123456-05:00",
  "project": "C:/path/to/project",
  "phase": "compile",
  "kind": "activity",
  "message": "Compiling player controller changes",
  "progress": 62.5,
  "detail": {},
  "source": "whatif-game-dev-studio"
}
```

## Rules

- `timestamp` is UTC-offset-aware ISO 8601.
- `phase` describes the current production stage, not a fake animation stage.
- `kind` is one of `started`, `activity`, `artifact`, `milestone`, `warning`, `error`, `completed`, `heartbeat`.
- `progress` is optional. Only provide it when the denominator is known from real tasks/milestones. Omit it when progress cannot be defended.
- `detail` can include command summaries, file paths, artifact paths, test counts, build identifiers, engine info, frame timings, or screenshot references. Do not put passwords/tokens/secrets in events.
- A `milestone` means an outcome has evidence, not merely that work began.
- A `completed` event must include enough detail to identify the verification that completed.

## Simple View mapping

Use the newest event as the plain-English current activity. Show the most recent visual artifact (gameplay screenshot/video frame, scene capture, Blender render) as the hero surface when available. Show real milestone events as a compact timeline.

During nonvisual work, use a tasteful animated status surface, but label only the real phase/message. Never synthesize percentages from elapsed time.

## Developer View mapping

Expose timestamp, phase, kind, message, selected detail, related changed files/artifacts, build/test output, performance evidence, and provenance entries. Allow filtering errors/warnings/milestones.

## Heartbeats

Long-running operations may emit heartbeat events to prove the worker is alive. A heartbeat is not progress and must not advance a progress bar unless real completed-work evidence also changed.
