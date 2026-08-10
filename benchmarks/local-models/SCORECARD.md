# Local model scorecard

_2026-08-10T00:08:43 · NVIDIA GeForce GTX 1660 Ti with Max-Q Design · 6.0 GB VRAM_

Every result is machine-verified: code is executed, JSON is parsed, tool calls are
inspected. No model grades another, so nothing here can be talked into a pass.

| Model | Overall | coding | debugging | instruction following | reasoning | structured output | tool calling | tok out | time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `qwen2.5:7b` | **97%** | 90% | 100% | 100% | 90% | 100% | 100% | 1802 | 467s |
| `llama3.2:3b` | **85%** | 80% | 90% | 90% | 90% | 70% | 90% | 1777 | 200s |
| `dolphin-llama3:latest` | **82%** | 70% | 100% | 70% | 90% | 80% | n/a | 2483 | 671s |
| `qwen2.5-coder:7b` | **78%** | 80% | 100% | 90% | 80% | 100% | 20% | 1719 | 454s |
| `qwen2.5:1.5b` | **78%** | 70% | 80% | 70% | 70% | 80% | 100% | 2024 | 138s |
| `qwen2.5vl:3b` | **74%** | 40% | 80% | 70% | 80% | 100% | n/a | 1713 | 116s |
| `llava:7b` | **74%** | 60% | 70% | 70% | 80% | 90% | n/a | 2135 | 643s |
| `llama3.2:1b` | **73%** | 60% | 80% | 100% | 50% | 70% | 80% | 1819 | 156s |
| `qwen2.5-coder:3b` | **72%** | 80% | 100% | 70% | 60% | 100% | 20% | 2180 | 221s |
| `qwen2.5-coder:1.5b` | **68%** | 70% | 90% | 70% | 70% | 90% | 20% | 2142 | 160s |
| `sim:latest` | **58%** | 40% | 80% | 60% | 70% | 40% | n/a | 3197 | 2813s |
| `deepseek-coder:6.7b` | **54%** | 80% | 90% | 30% | 30% | 40% | n/a | 5619 | 1715s |
| `moondream:latest` | **32%** | 10% | 40% | 50% | 20% | 40% | n/a | 1189 | 99s |

## Reading this

`n/a` means the model could not be graded on that skill at all - for tool calling it
means Ollama returned HTTP 400, because coder-tuned models ship without a tools
template. That is a real capability gap, not a low score, and it is why the coding
leader cannot hold a seat that has to call tools.

Pick per skill, not by the overall column. The best coder here is usually not the best
instruction-follower, and a squad wants the right specialist in each seat.

