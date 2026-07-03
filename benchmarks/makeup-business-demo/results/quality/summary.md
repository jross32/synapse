# Quality summary — Glow Studio benchmark

Six independent judge agents, one per dimension, each reading every file of both apps (and live-testing both in a real browser for the functional dimensions). No single "quality score" — see [`methodology.md`](../../methodology.md) for why.

| Dimension | With Synapse | Without Synapse | Winner |
|---|---|---|---|
| [UI/UX](./ui-ux.md) | 78 | 68 | With Synapse |
| [Visual design](./design.md) | 90 | 46 | With Synapse |
| [Code quality / architecture](./code-quality.md) | 85 | 75 | With Synapse |
| [Backend / functional correctness](./backend-correctness.md) | 78 | **94** | **Without Synapse** |
| [Usability & accessibility](./usability-accessibility.md) | 65 | 42 | With Synapse |
| [Adversarial bug hunt](./bug-hunt.md) | 42 | **96** | **Without Synapse** |
| **Average (unweighted)** | **73.0** | **70.2** | With Synapse, narrowly |

## What this actually shows

This is not a clean sweep, and reporting it as one would be dishonest. The with-Synapse build is the more ambitious, better-designed, better-architected result — real custom typography vs. system fonts, a 10-token color system vs. 5 flat colors, a working (if buggy) mobile menu vs. none, a fuller design-token system in the CSS. On four of six dimensions it's a clear win.

But it also shipped two real, live-reproduced defects that the simpler build didn't: a contact form that silently accepts and "succeeds" on a completely empty submission (`novalidate` with no JS fallback — a real business would receive blank leads and never know), and a mobile navigation menu that visibly overlaps the header and is largely unclickable at ≤768px on every load. Those two bugs are why "adversarial bug hunt" and "backend correctness" — the two dimensions that actually try to break things rather than assess quality — both favor the simpler, less ambitious build.

**The honest read:** more scope and more polish (a squad-built, more capable session working inside a real Synapse project) bought better design and architecture, but also more surface area for defects in a single, unreviewed pass — and this benchmark ran without a Synapse reviewer role or a review pass, which is exactly the mechanism [Synapse's squads](../../README.md#what-can-i-do-with-it-and-why-is-it-better-than-just-using-an-ai-chatbot) exist to add. A second pass — either a squad's reviewer role, or simply asking a second AI to test the first one's work — would very plausibly have caught both bugs before they shipped. That's the gap this benchmark actually measures: not "does Synapse write better code," but "what happens when nothing double-checks a single AI's output," which is true with or without Synapse in the loop.

## Tokens & time

| | With Synapse | Without Synapse |
|---|---|---|
| Tokens | ~16.1k (CLI's own live counter) | 51,314 (harness self-report) |
| Time | 3m 8s active / 5m 29s wall | 1m 47s |

Read this alongside the quality table, not instead of it — the with-Synapse run used noticeably fewer tokens for a larger, more polished, more complex result (more sections, a design-token system, a mobile nav implementation, more copy), while the without-Synapse run spent more tokens on a smaller, simpler scope. Token efficiency and output scope aren't separable in a single-run benchmark like this one; see `../../results/tokens/` for the raw per-side numbers and `../../methodology.md` for exactly how each was captured.

## Bottom line

Treat this as one honest, reproducible data point: Synapse produced the more capable single-shot result on design, architecture, and UX — and the exact kind of unreviewed-single-pass bugs that argue for actually using Synapse's multi-role squads (a reviewer role, a second pass) rather than a single worker, which is the setup this specific run didn't exercise. Re-run this benchmark with a reviewer role in the squad (Synapse's own benchmark engine at `/api/v1/benchmarks/*` supports exactly this, with repeats and confidence labels) and we'd expect the bug-hunt and correctness gap to close or reverse.
