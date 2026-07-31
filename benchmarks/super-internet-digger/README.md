# Benchmark: Super Internet Digger v1 vs. Synapse v2

This benchmark tests one deliberately narrow, reproducible part of the skill: inspecting an acquired project and proposing an accurate run plan without executing it.

It compares the locally installed Codex v1 helper against the portable Synapse v2 helper with the same machine, fixtures, Python runtime, and repeat count. It reports warm engine time and cold command-line time separately, plus a 100-point deterministic quality rubric.

The result does **not** prove that the complete internet-research workflow is 4x faster. That claim requires the seven-scenario, same-model, same-tool, at-least-five-repeat protocol in the skill's `references/benchmark-contract.md`.

Run:

```powershell
python benchmarks/super-internet-digger/run_benchmark.py
```

Artifacts:

- `results/quality/latest.json`: full measured data.
- `results/quality/summary.md`: concise result and allowed claims.
- `results/tokens/README.md`: why tokens are not applicable to this offline slice.
- `raw-logs/latest.json`: immutable copy of the raw result, including input hashes and environment.
- `methodology.md`: rubric and limitations.
