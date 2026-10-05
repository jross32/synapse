# UI Forge benchmark contract

UI Forge is only useful if it measurably improves a model's end-to-end app-building result. This benchmark compares a **baseline model with ordinary project/tool access** against the **same model, same tools, same machine, same task, plus UI Forge's control loop**.

The benchmark does not claim to reproduce Lovable's private benchmark, prompts, training data, or infrastructure. Lovable is a public product reference for workflow ideas; UI Forge must earn its own measured results.

## Comparison policy

For each scenario keep constant:
- model + version
- machine / network / credentials
- starting repository commit or fixture bytes
- enabled MCP/tool inventory
- user request and acceptance criteria
- time budget
- browser viewport set
- evaluator version

The only intended independent variable is whether UI Forge instructions/scripts/control-loop artifacts are supplied.

Run at least five repeats per candidate/scenario before calling a result stable. Keep failures in the denominator. Randomize candidate order where practical.

## Scenario families

1. **Greenfield visual build** — turn a product brief into a distinctive, usable responsive UI.
2. **Existing-app improvement** — materially improve hierarchy/UX without breaking working behavior.
3. **Mobile recovery** — repair a desktop-biased surface for a narrow mobile viewport and keyboard/focus use.
4. **Precision visual edit** — make a small requested change to one rendered element without broad unrelated churn.
5. **Design-system drift** — remove one-off visual values/components and restore semantic token/component consistency.
6. **Failure-state quality** — loading, empty, error, success, disabled, and recovery states must be coherent rather than only the happy path.
7. **Stuck-agent recovery** — introduce a failed first approach; challenger should preserve context, change strategy, and finish without identical retry loops.

## Quality rubric (100)

Use the same eight UI Forge dimensions as the runtime scorer:
- Request fidelity: 15
- Visual design: 18
- UX: 15
- Responsive behavior: 10
- Accessibility: 9
- Runtime correctness: 15
- Browser proof: 10
- Originality / product fit: 8

Critical failures make the attempt ineligible regardless of weighted score:
- primary user path broken
- runtime/build failure
- fabricated product data used to visually fill gaps
- critical accessibility failure that blocks the main task
- missing required desktop/mobile browser proof
- destructive/unrequested behavior regression

## Objective evidence

Every run should preserve:
- starting commit / fixture hash
- exact prompt and candidate mode
- elapsed time
- model/runtime identity
- tool calls and failures
- changed-file list and diff size
- build/test output
- desktop screenshot(s)
- mobile screenshot(s)
- accessibility snapshot or equivalent structural proof
- console/runtime error output
- UI Forge evidence JSON
- deterministic scorer output
- design-system audit output where applicable
- element probe + source-locator output for precision-edit scenarios

## Efficiency metrics

Track:
- elapsed seconds
- time to first runnable preview
- time to passing evidence gate
- model tokens/cost when trustworthy
- failed/repeated tool calls
- number of repair loops
- files/lines changed for precision edits
- quality per minute
- quality per 1,000 tokens when token provenance matches

## Stability and honesty

Report median, p90, range, failure rate, and coefficient of variation where sample size allows.

Labels:
- 1–2 comparable runs: `single-sample`
- 3–4: `directional`
- 5+: `stable` only if variability is acceptable

Do not hide failed attempts, evaluator disagreements, or browser failures. Do not claim parity/superiority to Lovable from this benchmark alone because the execution environments differ.


## Workflow-treatment comparability

For baseline-versus-UI-Forge tests, the **benchmark task** must be byte-for-byte identical. The candidate treatment is declared separately:

- baseline candidate key: `workflow:baseline`
- challenger candidate key: `workflow:ui-forge`
- treatment metadata field: `candidate_instruction_md`
- base task artifact: `TASK.md`
- effective treatment + task artifact: `PROMPT.md`

The workflow treatment is the independent variable; runtime, provider/model version, tool inventory, machine, fixture/reset procedure, task, and time budget are controlled variables. Use `scripts/benchmark_matrix.py` to generate this matrix. Do not let Synapse collapse both treatments into one runtime/model candidate group.

## Allowed claims

- **Higher UI quality:** challenger median weighted score is higher; state the point delta.
- **Fewer regressions:** challenger critical/runtime regression rate is lower; give both rates.
- **Faster to verified quality:** baseline median time-to-pass / challenger median time-to-pass; only use a multiplier if >= 1.25x and quality is not lower.
- **More precise edits:** challenger median unrelated-diff size is lower while request fidelity/runtime correctness are not lower.
- **Better design consistency:** challenger median design-adherence score is higher without a visual-design regression.

If the measurement does not support a desired claim, report the bottleneck rather than changing the rubric after the run.
