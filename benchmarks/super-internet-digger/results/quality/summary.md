# Quality and speed summary

Measured scope: **deterministic offline project inspection only**. Repeats: **15**.

## Result

- Warm inspection engine: **5.08x faster** (passes the 4x gate).
- Cold command-line invocation: **1.45x faster** (does not pass the 4x gate).
- Deterministic quality rubric: **46.92/100 -> 100.0/100** (**+53.08 points**).
- Warm quality-adjusted throughput: **10.82x** (passes the 4x time-efficiency gate).
- Cold CLI quality-adjusted throughput: **3.08x** (does not pass the 4x time-efficiency gate).
- Critical safety regressions: **none observed** in this offline slice.
- Full internet-research skill: **not yet proven 4x**; the model/tool benchmark remains a release gate.

The warm and cold results are reported separately because Python process startup is real user-visible cost. The 4x claim applies only to the warm inspection engine when `passes_4x` is true; it must not be generalized to the whole skill.
