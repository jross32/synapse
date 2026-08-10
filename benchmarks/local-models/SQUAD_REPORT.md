# Local-model squads: how many agents actually help?

Every seat costs a full model turn, and every handoff is a chance for a small model
to garble the previous one's work. These runs test whether the extra seats buy
correctness. Scoring is machine-checked: the produced file is executed against
assertions the agents never see.

Agent seat: `qwen2.5:7b` · Reviewer seat: `llama3.2:3b` (both chosen from the measurements in REPORT.md).

| Topology | Seats | Pass rate | Avg time | Avg tokens |
|---|---:|---:|---:|---:|
| `solo` | 1 | **100%** | 86.7s | 252 |
| `coder_reviewer` | 2 | **100%** | 171.4s | 423 |

## Per task

| Topology | fizzbuzz | roman | wordcount |
|---|---|---|---|
| `solo` | 100% (105.5s) | 100% (71.5s) | 100% (83.0s) |
| `coder_reviewer` | 100% (158.7s) | 100% (220.3s) | 100% (135.2s) |

