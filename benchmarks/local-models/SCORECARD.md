# Local model scorecard

_2026-08-10T00:08:08 · NVIDIA GeForce GTX 1660 Ti with Max-Q Design · 6.0 GB VRAM_

Every result is machine-verified: code is executed, JSON is parsed, tool calls are
inspected. No model grades another, so nothing here can be talked into a pass.

| Model | Overall | coding | debugging | instruction following | reasoning | structured output | tool calling | tok out | time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `qwen2.5:1.5b` | **70%** | n/a | n/a | n/a | 70% | n/a | n/a | 159 | 11s |

## Reading this

`n/a` means the model could not be graded on that skill at all - for tool calling it
means Ollama returned HTTP 400, because coder-tuned models ship without a tools
template. That is a real capability gap, not a low score, and it is why the coding
leader cannot hold a seat that has to call tools.

Pick per skill, not by the overall column. The best coder here is usually not the best
instruction-follower, and a squad wants the right specialist in each seat.

