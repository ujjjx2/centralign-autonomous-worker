# CentrAlign AI v6.2 — Final submission checklist

**Repository:** https://github.com/ujjjx2/centralign-autonomous-worker

**Submission readiness:** Core invoice+Gemma+Chromium run verified in a user-provided execution trace. A separate source-only pytest run passed 56 tests, with 2 media tests skipped. Real Gemma and Chromium approval/retry/support demonstrations are **not yet confirmed on the Mac** and require the live preflight below. No public demo-video link has been supplied yet.

## Perform these checks on the Apple M4

1. In the existing project folder, activate `.venv`; launch Ollama and ensure `gemma4:e2b` is installed. Install Chromium and FFmpeg if needed.
2. Close any running CentrAlign server. Run `OLLAMA_TIMEOUT=240 bash scripts/final_submission_check.sh`.
3. Require all checks to finish successfully. Inspect the full MP4 at `docs/CentrAlign_v6_REAL_BROWSER_DEMO.mp4` and the generated `data/submission_checks/` evidence logs.
4. Confirm the isolated video includes a standard invoice, injected HTTP 503 recovery, support-ticket triage and a human approval pause/resumption; check the `run_summary.json` for matching flags.
5. Host the genuine video on a shareable service, and **insert the actual URL** into the root README; verify viewer permissions without an authenticated session.
6. `git add` only the source/docs/scripts and commit/push to the **same** existing GitHub repository. Do not upload `.venv`, model weights, `.env`, SQLite databases or generated video unless a platform explicitly requires it.
7. Submit the repository URL and real video URL via the employer's indicated channel before the deadline specified in the assignment.

## Honest technical disclosures

- The model is Google's pretrained Gemma 4 E2B running locally through Ollama. It is not self-trained and is not a hosted API.
- The project is a bounded agent for two simulated enterprise workflows; arbitrary computer or external-site tasks are not supported.
- Decisions are suggested by Gemma within Python-enforced allowlists, prerequisites, approval policy, idempotency and independent verification. The system discloses deterministic fallbacks in traces.
- Automated tests use deterministic model stubs/fake Ollama; only the Mac live checks exercise the actual locally installed Gemma.
- The sandbox is not a production deployment and does not process real money, customer accounts or private business documents.

**Do not claim the video is published until it has been recorded, watched, uploaded and the public link verified.**
