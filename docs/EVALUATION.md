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

## Most recent verification available in this package

On 17 October 2026, the v6.2 archive was tested in an independent Linux container. **56 tests passed, 2 were skipped, 0 assertions failed**, according to pytest's completed summary (`56 passed, 2 skipped in 34.59s`). Skips were the browser-video tests because the container lacked Playwright's FFmpeg and Chromium bundles. This verifies the isolated test suite, **not** the Apple M4 runtime, real model behavior, or all four live browser scenarios.

The user's prior M4 trace separately showed an actual successful Chromium task with `gemma_validated` decomposition, `gemma4_e2b` accepted action choices and a `fresh_browser_readback` verification match for Northstar Labs. The high-value approval, injected-failure recovery and support-ticket browser flows still require fresh Mac evidence; run `scripts/final_submission_check.sh` and inspect its logs and the MP4 before claiming these are validated on the physical computer.

## What these results **do not** mean

- Mock-Ollama responses validate wiring and policy restrictions; they do not establish real Gemma 4 E2B reasoning quality.
- A successful HTML-over-HTTP test is not evidence of Chromium navigation.
- Unfamiliar workflows and arbitrary operating-system tasks remain out of scope.
- This is not a production-grade identity, security or scheduling system.

## On the MacBook Pro M4

Run `python scripts/check_mac_m4.py`, `python -m pytest -q`, then `HEADLESS=false make run-browser` and a real task through the dashboard. Inspect the displayed action plan, adaptive decisions, recovery events, and verified data. Finally run `python scripts/record_live_demo.py --headful` with FFmpeg available.
