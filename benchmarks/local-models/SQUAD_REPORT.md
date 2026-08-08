# Local-model squads: how many agents actually help?

Every seat costs a full model turn, and every handoff is a chance for a small model
to garble the previous one's work. These runs test whether the extra seats buy
correctness. Scoring is machine-checked: the produced file is executed against
assertions the agents never see.

Agent seat: `qwen2.5:1.5b` · Reviewer seat: `llama3.2:3b` (both chosen from the measurements in REPORT.md).

| Topology | Seats | Pass rate | Avg time | Avg tokens |
|---|---:|---:|---:|---:|
| `pipeline_repair` | 4 | **100%** | 44.7s | 0 |
| `coder_reviewer` | 2 | **67%** | 102.7s | 353 |
| `planner_coder_reviewer` | 3 | **67%** | 120.5s | 448 |
| `verify_then_review` | 2 | **67%** | 100.3s | 481 |
| `solo` | 1 | **33%** | 22.1s | 237 |
| `self_verify` | 1 | **33%** | 19.4s | 178 |

## Per task

| Topology | fizzbuzz | roman | wordcount |
|---|---|---|---|
| `pipeline_repair` | 100% (62.3s) | 100% (34.8s) | 100% (37.0s) |
| `coder_reviewer` | 100% (85.0s) | 100% (144.8s) | 0% (78.4s) |
| `planner_coder_reviewer` | 100% (127.9s) | 100% (155.1s) | 0% (78.4s) |
| `verify_then_review` | 100% (93.3s) | 100% (121.2s) | 0% (86.5s) |
| `solo` | 0% (23.0s) | 100% (23.9s) | 0% (19.5s) |
| `self_verify` | 0% (16.4s) | 100% (27.2s) | 0% (14.5s) |

