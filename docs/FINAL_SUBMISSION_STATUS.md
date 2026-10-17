# CentrAlign AI v6.2 — Submission verification status

Checked on **17 October 2026**.

## What has been completed

| Deliverable | Evidence | Status |
|---|---|---|
| Source code on GitHub | User provided a successful `git push` output for `https://github.com/ujjjx2/centralign-autonomous-worker` | Pushed before this submission patch; patch itself still requires a commit and push |
| Python automated tests | In this environment: `56 passed, 2 skipped in 34.58s`, exit code `0`; skips were Playwright video/Chromium binary tests | Passed in independent container (not rerun on Mac) |
| Normal invoice automation with real Gemma and Chromium | User-provided task trace: accepted `gemma_validated` plan, `gemma4_e2b` actions, browser submission, `fresh_browser_readback` matched | Verified on user's M4 for one invoice |
| Human approval | `tests/test_e2e.py::test_03_high_value_requires_actual_approval` and rejection safety tests | Passed in CI-style sandbox; **Mac live run pending** |
| Injected failure and retry | `tests/test_e2e.py::test_04_retry_once_after_real_http_503` and autonomy recovery tests | Passed in CI-style sandbox; **Mac live run pending** |
| Support-ticket triage | `tests/test_support_e2e.py::test_support_ticket_classified_saved_and_verified` and classification tests | Passed in CI-style sandbox; **Mac live run pending** |
| Real four-scenario video | `scripts/record_live_demo.py --headful --strict` plus `scripts/final_submission_check.sh` | Recorder prepared; **not executed on user's M4 in this chat** |
| Hosted demo URL | Video must be recorded, watched, uploaded and shared by the user | **Pending** |
| GitHub README | Updated local README with setup, workflow, safety, evaluation, demo instructions and clear placeholder for video | Patch prepared; **not pushed remotely** |

## Live Mac one-command acceptance test

```bash
cd ~/Downloads/centralign-autonomous-worker
open -a Ollama
OLLAMA_TIMEOUT=240 bash scripts/final_submission_check.sh
```

Results go into `data/submission_checks/` and the generated MP4 goes to `docs/CentrAlign_v6_REAL_BROWSER_DEMO.mp4`. The command requires FFmpeg and locally installed Ollama and Playwright Chromium, and it may take several minutes. It stops on failures instead of fabricating successful evidence. Check all files before submitting and don't commit recordings, virtual environments or secrets.
