# CentrAlign AI — live demonstration and evidence (v6.2)

## Before the demonstration

Use the **existing project folder** on your Mac. Open the Ollama app and make sure `ollama list` contains `gemma4:e2b`. Install runtime dependencies and Chromium per the root README. Install FFmpeg with `brew install ffmpeg`. Close any running CentrAlign server if you will use the isolated recorder.

From the project root:

```bash
source .venv/bin/activate
OLLAMA_TIMEOUT=240 bash scripts/final_submission_check.sh
```

The script **does not claim it has succeeded until the actual Mac checks complete**. It runs pytest; contacts your real local Gemma model; checks Chromium; then opens a dashboard and real Chromium browser and records four independent scenarios in a **fresh synthetic database**. Original sandbox data is not reused. Each task's report, traces and recording are preserved under `data/recorded_demos/<run_id>/`.

## Four live scenarios

| Order | Natural-language instruction | What the strict script checks |
|---|---|---|
| 1: Normal invoice | `Find the latest invoice from Northstar Labs and record it in accounts payable.` | Accepted Gemma plan/action, DOM operations, ledger write and fresh readback matching |
| 2: Recover 503 | `Record the latest invoice from Harbor Office.` | Inject a one-shot accounting HTTP 503 first; model-backed action and visible `retry` event; verify saved record |
| 3: Helpdesk | `Triage ticket TKT-402 and assign it to the appropriate team.` | Accepted Gemma plan/action, support case saved and verified |
| 4: Approval | `Record the latest invoice from Acme Services.` | Agent pauses at `awaiting_approval`; dashboard human approval button is clicked; only then writes and verifies |

The demo runner enforces the claimed capabilities using execution events. `gemma_validated` and `gemma4_e2b` mean model decisions passed a Python allowlist; they do not grant arbitrary OS capabilities. Unexpected `validated_fallback` events fail the **strict** demonstration rather than masquerading as AI decisions. Model runs may take several minutes on M4.

## Video, logs and evidence

- **Resulting MP4:** `docs/CentrAlign_v6_REAL_BROWSER_DEMO.mp4` after a fully successful run with FFmpeg.
- **Separate raw recordings:** `data/recorded_demos/<run_id>/artifacts/<task_uuid>/browser-recording.webm` and `dashboard-recording.webm`.
- **Run summary:** `data/recorded_demos/<run_id>/run_summary.json` with task IDs, verified outcomes, accepted Gemma choices, retry and approval evidence.
- **One-command logs:** `data/submission_checks/<timestamp>/` — `pytest.txt`, `gemma_diagnostic.txt`, `mac_diagnostic.txt`, `live_demo.txt`, `run_summary.json`.

**Manually watch the entire resulting MP4 before publication.** Confirm screen contents are readable, source and target applications are visible and the video shows real browser actions. Check that no personal credentials or unrelated windows appear. This check cannot be automated reliably from a textual run summary.

## Publish and share

Upload the **actual** MP4 to a video hosting location with appropriate viewer access. Verify its URL using a logged-out or incognito browser; paste the real URL into the README `Demo recording` line. Do not commit model weights, secrets, SQLite databases, generated videos or environment directories to GitHub. Commit just source/documentation updates in your existing repository:

```bash
git add README.md SUBMISSION.md docs/DEMO_WALKTHROUGH.md docs/EVALUATION.md scripts/record_live_demo.py scripts/final_submission_check.sh .gitignore
git commit -m "Add final submission validation and verified demo workflow"
git push
```

If a particular task fails, collect `data/recorded_demos/<run_id>/server.log` and the related task trace, address the issue, then rerun the isolated recorder. Do not label failing or fallback runs as completed demonstrations.
