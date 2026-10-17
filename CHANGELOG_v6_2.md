# v6.2 — Gemma response and browser reliability fixes

## Fixed

- Gemma 4 E2B responses lacking a `reason` are now accepted when the **decision itself** passes the strict allowlist.
- Accept JSON responses in Markdown fences, exact authorized action labels, safe `action`/`tool_choice` aliases, and initial plan arrays. No arbitrary prose can become a tool command.
- If Ollama ignores the JSON schema, retry **once** with the JSON output mode; never execute a label absent from the selected allowlist.
- If a syntactically valid task plan omits a mandatory prerequisite, prompt Gemma for one corrected plan and validate it again; otherwise label the safe fallback.
- Action audit events now include sanitized `model_diagnostic` metadata showing schema vs JSON retry acceptance/rejection.
- Include the v6.1 browser-closure recovery patch: preserve the original exception and restart a closed browser session; check a potentially committed record before retrying a write.
- The dashboard refreshes invoice and support-case counts after task completion rather than showing only the initial server render.
- Jinja2 is a declared installation dependency.

## Verification included

- `python -m pytest -q`: 56 passing tests, 2 Playwright-media skips in the current Linux environment.
- `OLLAMA_TIMEOUT=240 python scripts/diagnose_gemma.py --full`: **must be run on the user's Mac** to test actual Gemma inference and bounded decisions.
- `python scripts/check_task_artifacts.py TASK_ID`: checks real task status, verification evidence, video and trace artifacts.

## Unverified here

Actual Gemma 4 E2B weight-based inference and full local M4 Chromium execution were not available to this runtime. The source tests use local fake Ollama responses; a successful real-model run must be confirmed on the Mac. The browser-video checker verifies file presence, not subjective playback quality.
