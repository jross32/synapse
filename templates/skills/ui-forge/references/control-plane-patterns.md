# Control-Plane Patterns Behind Strong AI UI Builders

This is a vendor-neutral implementation note derived from public product documentation and observations. It records principles to reproduce, not proprietary internals.

## High-value patterns

1. **Optimize the finished app, not the text response.** A convincing explanation is irrelevant if the running application is broken or visually wrong.
2. **Plan before broad edits.** Convert intent into a bounded design/implementation plan, then execute in slices.
3. **Model-independent, not model-indifferent.** Different models have different strengths. Adapt instructions, tools, context size, and role to the model and task.
4. **Use a control plane.** Watch progress, detect circling/stalls, and change the failing variable: plan, context, tool, reviewer, or model.
5. **Preserve context across model switches.** Carry discoveries, failed attempts, screenshots, constraints, and current state forward.
6. **Run the app and inspect it.** Self-verification in a browser is a first-class behavior, not an optional final step.
7. **Use a code-native design system.** Components, semantic tokens, constraints, and setup rules should be machine-readable and enforced throughout generation.
8. **Prefer precise visual edits.** Map a rendered element back to the smallest owning component/style/token and mutate the minimum necessary surface.
9. **Use instant feedback.** Hot-reload or fast preview changes shorten the taste/verification loop and reduce large blind edits.
10. **Evaluate repeatedly.** Run the same class of build more than once in benchmark work so a lucky result is not mistaken for a reliable workflow.
11. **Independent review lenses.** Separate discovery of issues from triage/fixing; use focused reviewers for visual design, UX/a11y, correctness, performance/reuse when scale justifies it.
12. **Turn repeated failures into durable knowledge.** Improve skill instructions, project knowledge, component rules, and regression checks rather than fighting the same failure every run.

## Synapse mapping

- project context / AI memory -> durable product context
- Web Scraper -> public reference structure/screenshots/interactions
- Playwright / Reflex -> browser and desktop proof
- Quality OS -> evidence, gates, failing contracts
- AI Council / squads -> multi-lens reviewers and specialist workers
- skill packs -> reusable model instructions and durable workflow knowledge
- quick actions -> one-click invocation from the Synapse UI
- runtime status/routing -> choose available high-powered workers intentionally

## UI Forge target loop

`inspect -> brief -> reference harvest -> design grammar -> plan -> implement slice -> run -> browser inspect -> score -> repair -> persist learning`

This loop should remain useful even as the underlying frontier models change.
