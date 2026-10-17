# v6 Live demonstration walkthrough

1. Start local Ollama with `gemma4:e2b` installed and run `python scripts/check_mac_m4.py`.
2. Start `HEADLESS=false make run-browser`; visit `http://127.0.0.1:8000`.
3. **Task decomposition:** Record the latest Northstar Labs invoice. Point out the `Action plan` panel, `gemma_validated` vs `validated_fallback` marker and observation-conditioned `adaptive_decision` records.
4. **Invoice error recovery:** On a fresh task/invoice, click `Fail next ledger write once`. The server returns one real HTTP 503. Show target recheck, chosen recovery, actual form resubmission and readback. Avoid a previously recorded invoice because idempotency correctly skips duplicate writes.
5. **Support recovery:** Click `Fail next support write once`, triage an unprocessed ticket and observe the same verified recovery mechanics across a different application.
6. **Safety:** Submit the high-value Acme Services invoice. Confirm it pauses for approval and cannot autonomously approve itself.
7. **Evidence:** Inspect task JSON and persisted record, then run a live recorder on the actual M4 (`python scripts/record_live_demo.py --headful`). The recorder should not fabricate success if Chromium cannot execute.

The original sandbox documents are synthetic. The record creation, forms, model calls, recovery choices and verification are real local operations when the required runtimes are available.
