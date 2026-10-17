# CentrAlign AI v6 — Architecture

For the complete high- and low-level design, see [V6_AUTONOMY_DESIGN.md](V6_AUTONOMY_DESIGN.md).

The system consists of a local Gemma 4 E2B service (Ollama), a structured planning and validation layer, an observation-driven runtime, a Playwright browser adapter (plus HTML-over-HTTP CI transport), two local company applications, SQLite state storage, server-enforced approval restrictions and readback verification.

**v6 changes compared with v5:** `planner_v6.py` requests a model-authored step list and rejects plans that omit mandatory milestones. `reactive.py` presents the model with valid next-action choices derived from actual state, then executes only allowed actions. Recovery now includes broad search, source refresh, target recheck, form refresh, retry and independent re-verification, plus a one-shot failure injector for the helpdesk application.

**Trade-off:** Gemma offers flexible local proposals but cannot run arbitrary operations or override safety. The runtime retains a bounded two-workflow state machine. The model weights are downloaded from Ollama and not distributed inside the source ZIP. The default browser mode requires Chromium, and full Mac verification remains a separate acceptance task.
