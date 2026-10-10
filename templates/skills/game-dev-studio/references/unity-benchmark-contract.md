# Unity benchmark contract

Use benchmark numbers only when the measurement class is explicit and comparable.

## Runtime measurement classes

A `Null Device` run is a **headless simulation benchmark**. It can measure gameplay/simulation throughput and Unity memory counters, but it is not graphics-performance evidence. Never compare its FPS or frame time to a rendered player.

A **rendered benchmark** must report a real graphics device, use a warm-up period before sampling, and use a fixed sample window. For short reference-game checks, use at least 1 second of warm-up and 5 seconds of sampling; prefer 2 seconds + 10 seconds for stable local baselines.

Startup frames, shader initialization, first-scene load, and process creation are not steady-state frame measurements. If they matter, record them separately as startup metrics. Do not mix them into gameplay frame averages.

Counters are capability-scoped. If `ProfilerRecorder` or another adapter does not expose a counter in the current player, record the counter as unavailable. Never coerce an unavailable counter to zero.

## Build comparability

Cold-cache and warm-cache Unity build durations are separate benchmark classes. A first import/build cannot be claimed as slower or faster than a warm incremental build without an intentionally controlled cache state. Build result, warnings, errors, output size, and exact cache class should be recorded together.

## Unity process lifecycle

A shell/tool call returning is not proof that Unity has exited or that a test result exists. Before starting another Editor job for the same project:

1. poll for the expected test/build artifact or process exit;
2. verify no live `Unity.exe` owns the project;
3. distinguish a connector timeout from an engine failure;
4. never launch a duplicate job just because the outer command timed out.

## Source gates

Run whitespace/diff checks on authored source, manifests, benchmark records, and scripts. Unity-generated serialized YAML may contain trailing spaces by design; do not rewrite engine-owned YAML solely to satisfy a generic text-style gate. Validate those files through Unity import/compile and scene/project tests instead.

## Coverage

Coverage is execution evidence, not a quality score. Preserve aggregate and per-class coverage, then use low-covered behavior to choose the next meaningful tests.

## Visual evidence and presentation control

For release-grade rendered benchmarks, prefer engine-native screenshots captured after rendering completes. Store the PNG path, byte count, and SHA-256 in the benchmark JSON and verify the bytes before accepting the run. A screenshot path or hash that cannot be verified is a hard evidence failure when screenshot proof is required.

Rendered benchmark comparisons should explicitly control presentation when max-frame thresholds matter. Record the benchmark VSync count and target frame rate. Do not silently compare a VSync-paced run with an uncapped or differently capped run. If a benchmark is rejected, preserve a compact rejection record containing the frozen threshold, observed value, diagnosis, and corrective action; do not delete the fact that the run failed.

When an isolated max-frame outlier appears while p95 remains healthy, diagnose before changing thresholds. Check startup stabilization, display pacing, target discovery/allocation hotspots, spawning, garbage collection, and OS scheduling. Keep the predeclared acceptance limit unchanged unless a later version explicitly defines a new benchmark class before measuring it.
