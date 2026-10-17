# CentrAlign AI v6 — Evaluation and test claims

## Requirements addressed

| Internship criterion | v6 behavior | Evidence |
|---|---|---|
| Break objective into actions | Local Gemma proposes structured `steps`; validator keeps mandatory safe milestones | `test_v6_autonomy.py`, `gemma_task_decomposition` events |
| Decide next action from observation | State-dependent candidate actions, model chooses from current allowlist | `test_v6_autonomy.py`, `adaptive_decision` events |
| Try alternatives and recover | Alternate search, refresh source, target readback, reopen form, bounded retry, second verification | `test_v6_autonomy.py`, HTTP failure injection in both business systems |
| Human approval | Invoice approval cannot be skipped by model | Existing invoice end-to-end tests |
| Actual execution | Local HTML forms and SQLite persistent writes, browser automation adapter | End-to-end HTTP integration; browser component tests |
| Verified completion | Fresh target readback with exact field comparisons | End-to-end tests and evidence artifacts |

## What these results **do not** mean

- Mock-Ollama responses validate wiring and policy restrictions; they do not establish real Gemma 4 E2B reasoning quality.
- A successful HTML-over-HTTP test is not evidence of Chromium navigation.
- Unfamiliar workflows and arbitrary operating-system tasks remain out of scope.
- This is not a production-grade identity, security or scheduling system.

## On the MacBook Pro M4

Run `python scripts/check_mac_m4.py`, `python -m pytest -q`, then `HEADLESS=false make run-browser` and a real task through the dashboard. Inspect the displayed action plan, adaptive decisions, recovery events, and verified data. Finally run `python scripts/record_live_demo.py --headful` with FFmpeg available.
