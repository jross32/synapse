# Methodology

## Speed

The benchmark creates a 5,001-file fixture with one relevant CMake marker and 5,000 irrelevant files. It warms each engine, alternates candidate order across fifteen runs, and reports median, p90, min, max, and coefficient of variation.

- **Warm engine** measures the imported detection function and isolates scanning/design performance.
- **Cold CLI** launches a fresh Python process for every attempt and includes real startup overhead.

A 4x result is allowed only when baseline median / challenger median is at least 4.0, challenger quality is not lower, and no critical safety regression occurs.

Quality-adjusted throughput is also reported as `(quality / median milliseconds)` for challenger divided by baseline. This is the predeclared time-efficiency measure from the skill benchmark contract; it is never mislabeled as raw speed.

## Quality (100 points)

Seven fixtures cover polyglot and single-runtime Node, Python, .NET, CMake, Rust, static web, Unity, Godot, and Unreal projects.

- Detection recall: 40
- Precision: 10
- Complete polyglot reporting: 15
- Lockfile-aware reproducible Node install command: 15
- Evidence coverage: 10
- No execution during inspection: 10

The suite repeats every fixture for both candidates. Results are deterministic, but all repeats remain in the raw artifact.

## Limits

This suite does not use a model or network, judge research freshness, download anything, or execute acquired code. Therefore it cannot support a 4x claim for the full skill. Those dimensions remain governed by the separate seven-scenario research benchmark contract.
