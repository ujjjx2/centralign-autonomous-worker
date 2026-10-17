# CentrAlign AI — Submission guide

**Project:** Local Gemma 4 E2B autonomous task worker (v6).

The submission includes FastAPI sandbox applications, a Gemma-generated validated task planner with observation-based decision and alternative recovery, Playwright DOM control, SQLite task memory, an Ollama Gemma 4 E2B adapter, constrained JSON decisions, authorization rules, automated tests, and README/architecture/evaluation documents.

## Before submitting

1. Install the project and Ollama `gemma4:e2b` on your MacBook Pro M4 using `README.md`.
2. Run `python scripts/check_mac_m4.py` and confirm real model inference and Chromium startup.
3. Run `python -m pytest -q` and `python -m scripts.evaluate`.
4. Record **live** browser automation: `python scripts/record_live_demo.py --headful`.
5. Inspect recorded video for real cursor clicks, browser navigation and verification.
6. Push source to GitHub; do not commit downloaded model weights or `.env` secrets.
7. Host the demo video and submit GitHub/video links.

## Disclosures

- **Model:** Google's pretrained Gemma 4 E2B, downloaded and run locally with Ollama; no self-trained model or cloud API key.
- **Scope:** Two simulated enterprise workflows, not unrestricted operating-system control.
- **Tests:** Automated CI-style integration tests use a fake Ollama interface, not genuine Gemma outputs. Live model performance and browser automation require verification on the target Mac.
- **External dependencies:** Python, FastAPI, Playwright Chromium, SQLite, httpx and Ollama with Gemma 4 E2B weights.
- **Known limitations:** Small model, sandbox data only, two workflows, no production authentication or scalable task queue.
- **Future work:** Broader workflow discovery, more evaluation cases, recovery from unknown UI redesigns, and production authorization.
