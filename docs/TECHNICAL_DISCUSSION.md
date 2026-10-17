# Technical discussion — questions to prepare

**What was built?** A bounded agent using Gemma 4 E2B as a local decision engine, a goal-state planner, Playwright/HTTP form automation, SQLite audit memory, approvals, retries and read-back verification.

**Did you train the model?** No. The primary model is Google Gemma 4 E2B downloaded through Ollama. The earlier small self-trained transformer has been removed in v5.

**What does Gemma actually control?** It proposes invoice intent, ticket category/priority and an action from a restricted allowlist at decision points. The goal-state workflow graph, business validation, browser execution and evidence remain in Python. This is constrained agentic planning, not an unrestricted autonomous desktop operator.

**How is tool misuse prevented?** Each action is selected from a stage-specific allowlist; untrusted documents are passed as data; mandatory approvals and business rules are outside the model; no payments, deletions or external browsing are offered.

**How do you handle failures?** Verify whether uncertain writes were already committed, retry bounded temporary failures, prompt for missing information, and never mark completion without target-system read-back.

**How is actual AI inference demonstrated?** Run `python scripts/check_mac_m4.py`, inspect `/api/model`, and use `/api/model/predict`. Unit tests use a fake Ollama server and do not establish live model accuracy.

**What would you build next?** Additional skills, structured observation compression, a larger evaluation set with real Gemma inferences, crash-safe task queues, per-tool permission scopes, layout-shift benchmarks and authentication.
