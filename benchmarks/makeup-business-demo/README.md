# Benchmark: Glow Studio — with Synapse vs. without Synapse

**Question:** does building through Synapse (a real Agent Squad / workbench-launched Claude worker, inside a real Synapse project) produce a measurably different result than a single, memory-less, one-shot AI coding session — for the same spec, same model family, same machine?

This is a small, single-run benchmark on a deliberately small app. Treat it as one honest, reproducible data point, not a universal claim. See [`methodology.md`](./methodology.md) for exactly how it was run, including a bug we hit along the way.

## Layout

```
apps/
  with-synapse/       The app built via a real Synapse project + Claude worker
  without-synapse/    The identical spec, built by a single fresh AI session, no Synapse
results/
  tokens/              Real token/time/tool-call counts per side
  quality/              One file per scored dimension + a summary
screenshots/           Real screenshots of both running apps, desktop + mobile widths
raw-logs/               Run logs: timestamps, prompts sent, what happened
methodology.md          Exactly how this benchmark was run (read this first)
```

## Results at a glance

See [`results/quality/summary.md`](./results/quality/summary.md) for the full scored breakdown and [`results/tokens/`](./results/tokens/) for the raw token/time numbers.
