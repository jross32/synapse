# Local model benchmark results

Measured on this machine, not estimated. Code tasks are scored by executing the
generated code against assertions; tool-calling is scored by validating the shape
of the emitted call; throughput comes from Ollama's own eval counters.

## Machine

| | |
|---|---|
| GPU | NVIDIA GeForce GTX 1660 Ti with Max-Q Design |
| VRAM | 6.0 GB |
| RAM | 15.8 GB |
| CPU | AMD Ryzen 7 3750H |

## Efficiency ranking

Ranked by **useful work per unit time** (pass rate x median tokens/sec). Two models
with the same accuracy are not equally useful if one is four times faster.

| # | Model | Efficiency | Pass rate | Speed (tok/s) | Fits in VRAM |
|---|-------|-----------:|----------:|--------------:|--------------|
| 1 | `qwen2.5:1.5b` | **21.3** | 85.7% | 24.8 | yes |
| 2 | `llama3.2:1b` | **15.4** | 71.4% | 21.5 | yes |
| 3 | `llama3.2:3b` | **12.6** | 85.7% | 14.7 | yes |
| 4 | `qwen2.5-coder:3b` | **8.5** | 57.1% | 14.8 | yes |
| 5 | `qwen2.5:7b` | **5.1** | 85.7% | 6.0 | **no - spills to CPU** |
| 6 | `qwen2.5-coder:7b` | **4.4** | 71.4% | 6.1 | **no - spills to CPU** |
| 7 | `dolphin-llama3:latest` | **2.6** | 57.1% | 4.6 | **no - spills to CPU** |

## Accuracy by category

| Model | Overall | Tool-calling | Coding | Structured | Control | Review |
|-------|--------:|-------------:|-------:|-----------:|--------:|-------:|
| `qwen2.5:1.5b` | **85.7%** | 100% | 100% | 100% | 100% | 0% |
| `llama3.2:3b` | **85.7%** | 100% | 50% | 100% | 100% | 100% |
| `qwen2.5:7b` | **85.7%** | 100% | 100% | 100% | 100% | 0% |
| `llama3.2:1b` | **71.4%** | 100% | 50% | 100% | 100% | 0% |
| `qwen2.5-coder:7b` | **71.4%** | 0% | 100% | 100% | 100% | 100% |
| `qwen2.5-coder:3b` | **57.1%** | 0% | 100% | 100% | 100% | 0% |
| `dolphin-llama3:latest` | **57.1%** | 0% | 50% | 100% | 100% | 100% |

## Resource cost

| Model | On disk | Resident in VRAM | Fully on GPU | Cold load |
|-------|--------:|-----------------:|--------------|----------:|
| `dolphin-llama3:latest` | 5.34 GB | 4.19 GB | NO | 78.0s |
| `qwen2.5-coder:7b` | 5.12 GB | 4.19 GB | NO | 29.3s |
| `qwen2.5:7b` | 5.12 GB | 4.19 GB | NO | 34.0s |
| `llama3.2:3b` | 2.55 GB | 2.55 GB | yes | 20.5s |
| `qwen2.5-coder:3b` | 2.16 GB | 2.16 GB | yes | 21.3s |
| `llama3.2:1b` | 1.51 GB | 1.51 GB | yes | 57.3s |
| `qwen2.5:1.5b` | 1.17 GB | 1.17 GB | yes | 9.0s |

## Per-task detail

| Model | Write working code | Fix broken code | Reason about a diff | Follow exact instructions | Valid JSON on demand | Pick the right tool | Emit a tool call |
|---|---|---|---|---|---|---|---|
| `qwen2.5:1.5b` | PASS | PASS | FAIL | PASS | PASS | PASS | PASS |
| `llama3.2:3b` | FAIL | PASS | PASS | PASS | PASS | PASS | PASS |
| `qwen2.5:7b` | PASS | PASS | FAIL | PASS | PASS | PASS | PASS |
| `llama3.2:1b` | FAIL | PASS | FAIL | PASS | PASS | PASS | PASS |
| `qwen2.5-coder:7b` | PASS | PASS | PASS | PASS | PASS | FAIL | FAIL |
| `qwen2.5-coder:3b` | PASS | PASS | FAIL | PASS | PASS | FAIL | FAIL |
| `dolphin-llama3:latest` | FAIL | PASS | PASS | PASS | PASS | FAIL | FAIL |

