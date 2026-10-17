# CentrAlign AI — Autonomous Task Worker (v6.2, Gemma 4 E2B)

A local, inspectable AI task worker that executes **two real sandbox business workflows**. Give it one natural-language goal and watch it search source records, read information, operate an internal company application, handle errors/approvals, and verify the result.

The decision model is **Google Gemma 4 E2B**, running **locally with Ollama**. There is **no OpenAI/Google cloud API key**, no custom tiny transformer, and no hosted inference. The model's weights are obtained once using `ollama pull gemma4:e2b`; the ZIP does **not** contain those weights. The UI and documents are synthetic and stay on your computer.

## 1. What the app automates

| User's instruction | Actions the worker carries out |
|---|---|
| `Find the latest invoice from Northstar Labs and record it in accounts payable.` | Search invoice inbox → open invoice → extract amount, ID, due date → check ledger → fill and submit accounting form → read back and verify |
| `Record the latest invoice from Acme Services.` | Follow the same workflow but **pause for human approval** before the high-value write |
| `Check whether invoice HO-88 from Harbor Office was recorded.` | Search and verify only; **never** record a new entry |
| `Triage ticket TKT-402 and assign it to the right team.` | Search support inbox → read ticket → ask local Gemma for category/priority → validate business rules → create routed support case → verify |
| `Triage the latest support ticket.` | Check incident details and enforce high priority for production outages |

The worker is **not** a general desktop assistant. It supports two sandbox workflows.

**New in v6:** Gemma generates a structured, per-task action plan and proposes actions after observing live task state. A validator rejects incomplete/unsafe plans and the runtime rechecks prerequisites before acting. Failures can trigger alternative source searches, source refreshes, form reopening, persisted-record checks, bounded retries or clarification. These are **real alternative tool operations**, not just retry labels. All model decisions and fallbacks appear in the task trace.


### v6.2: Real Gemma output compatibility fixes

Earlier v6 builds could show `validated_fallback` for all decisions even when
Ollama was available: Gemma 4 E2B sometimes omits an explanation field,
returns JSON inside a code fence, or violates Ollama's strict JSON-schema
formatting. V6.2 makes `reason` optional, validates simple structured aliases,
and retries malformed output **once** using Ollama JSON mode. The same strict
tool allowlist applies to both attempts; a model cannot authorize unsupported
operations. Unsafe or repeatedly invalid decisions still use a clearly labelled
`validated_fallback` plan/action. Syntactically valid plans that omit required
milestones get one repair attempt before fallback.

The task trace records `model_diagnostic` for action choices, including whether
Gemma was accepted on the first schema request or the second JSON-mode request.
The dashboard also refreshes invoice/support-case counts when execution ends.
Browser-closure recovery from the earlier diagnostic patch is included.

After installing v6.2, run this real inference test on your Mac:

```bash
source .venv/bin/activate
OLLAMA_TIMEOUT=240 python scripts/diagnose_gemma.py --full
```

A healthy output reports `PASS invoice_operation`, `PASS plan`, and `PASS action`.
During an actual task, `gemma_task_decomposition.source` should read
`gemma_validated`, and model-backed adaptive choices should show
`decision_mode: gemma4_e2b`. If the model still produces unusable proposals,
the trace will explicitly disclose fallback. **The included automated tests
use simulated Ollama responses; actual Gemma inference must be tested on
your Mac.**

## 2. Install on MacBook Pro M4

**Requirements:** macOS 14+, native ARM64 terminal, Python 3.12 recommended (3.10–3.14 supported by installer), Ollama installed, and disk space for `gemma4:e2b` (the download is several GB). An internet connection is needed **once** to install Python packages, Chromium, Ollama and the model. Inference and tasks run offline thereafter.

1. Install Ollama from <https://ollama.com/download> and **open the Ollama application**. If the service isn't already running, you can run `ollama serve` in a separate Terminal.
2. Extract this ZIP and open Terminal in `centralign-autonomous-worker`.
3. Run:

```bash
bash scripts/setup_mac_m4.sh
source .venv/bin/activate
```

The installer creates the virtual environment, installs dependencies, downloads Playwright Chromium, downloads **Gemma 4 E2B** with `ollama pull gemma4:e2b`, then checks browser launch and real Gemma inference.

If you prefer a manual setup:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m playwright install chromium
ollama pull gemma4:e2b
python scripts/check_mac_m4.py
```

**No environment variables or API keys need to be set for the default installation.** The only LLM endpoint is `http://127.0.0.1:11434`.

The installer also installs Jinja2, which is required for the FastAPI HTML dashboard. If you installed an earlier v6 ZIP and see `ModuleNotFoundError: No module named 'jinja2'`, run `python -m pip install Jinja2` in the active virtual environment, or reinstall this corrected package with `python -m pip install -e '.[test]'`.

## 3. Start the application

In the project directory with `.venv` activated:

```bash
HEADLESS=false make run-browser
```

Open **http://127.0.0.1:8000**. The dashboard shows whether `gemma4:e2b` is installed and accessible. `HEADLESS=false` displays Chromium moving and operating the internal forms. To run without a visible Chromium window, use `make run-browser`.

To inspect model availability directly, open `http://127.0.0.1:8000/api/model`. If it says unavailable, open Ollama and run `ollama pull gemma4:e2b`, then reload.

## 4. Use the prototype

1. Click an example scenario or type an instruction in **Assign a task**.
2. Click **Run autonomous task**.
3. Watch the **Agent execution trace**: source discovery, extraction/classification, candidate action, browser steps, recovery and verified outcome.
4. Read the **Action plan** panel to see the proposed steps and whether Gemma's plan was accepted or the deterministic fallback was used. Under **Agent execution trace**, inspect `adaptive_decision` and `recovery` events to see actual next-action choices.
5. For an invoice requiring approval, click **Approve recording** or **Reject**. The worker never approves its own high-value write.
6. For missing information, read the clarification prompt and submit the corrected instruction.
7. Use **View verification evidence** and the recorded browser-video link (only available after successful Chromium sessions).

To demonstrate invoice recovery, click **Fail next ledger write once**, then run an invoice task that is not yet in the ledger. The accounting app returns HTTP 503 once. The worker *first checks for a potentially committed write*, chooses an allowed recovery action, refreshes the form if selected, retries if necessary, then verifies the record.

To demonstrate recovery in a different application, click **Fail next support write once** and triage a ticket that does not already have a case. This injects a separate one-shot 503 in the helpdesk system and uses the same observation/adaptation/retry mechanism.

To see resilience when form element IDs change, run the application with `UI_VARIANT=shifted HEADLESS=false make run-browser`. The agent locates controls by labels and their observed semantics.

The company app is available under `/workspace/invoices`, `/workspace/ledger`, `/workspace/tickets` and `/workspace/cases`.

## 5. Record an actual browser demonstration

**Stop the existing FastAPI server first**, then run:

```bash
source .venv/bin/activate
python scripts/record_live_demo.py --headful
```

The recorder starts a fresh isolated sandbox, opens a real Chromium dashboard, submits tasks, captures actual agent browser actions and verifies each task. If FFmpeg is installed, it creates `docs/CentrAlign_v6_REAL_BROWSER_DEMO.mp4`. It **fails on an unsuccessful workflow** rather than fabricating successful footage. Install FFmpeg, if needed, with `brew install ffmpeg`.

Do not confuse HTTP-mode test replays with genuine browser footage. Record the real demo on your Mac after the model and browser checks pass.

## 6. Run automated tests

```bash
python -m pytest -q
OLLAMA_TIMEOUT=240 python scripts/diagnose_gemma.py --full
python scripts/check_mac_m4.py
python -m scripts.evaluate
```

The ordinary test suite uses isolated SQLite databases and the local HTML-over-HTTP transport. Its Gemma integration tests use a **fake localhost Ollama API**, testing the real request protocol and end-to-end worker wiring without downloading model weights. **This is not a benchmark of actual Gemma prediction accuracy.** `check_mac_m4.py` performs a live inference check with your downloaded Gemma model and a Chromium launch. `scripts.evaluate` makes Gemma calls to classify the four synthetic tickets.

If Chromium is unavailable during development, start the same application with `make run-http`, which still submits real local HTML forms but is **not a Chromium demo**. For CI-only deterministic runs without the model, set `MODEL_BACKEND=rules` explicitly. The normal Gemma mode reports a failure if Ollama is missing; it never silently pretends the model was used.

### Verify browser-video playback and recovery

After your next Chromium task finishes, copy its **Task UUID** from the task
URL or `GET /api/tasks` and run:

```bash
python scripts/check_task_artifacts.py YOUR_TASK_UUID
```

Expect `task_status: completed`, `verified: true`, and a non-null
`browser_video` path. Open the WebM file in Chrome or inspect
`/api/tasks/YOUR_TASK_UUID/browser-video`. This verifies the artifact was
written, rather than inferring that video exists from a browser action log.
If the video is absent, report the artifact checker output; the application
can complete a browser task even when video capture fails.

To demonstrate actual **failure recovery**, do not re-record an invoice that
already exists. Click **Fail next ledger write once**, and run a *new*
invoice such as `Process invoice BP-774 from BluePeak Cloud`. The simulated
service will return HTTP 503 once, and the worker should check the ledger
before retrying. Confirm the trace contains a `retry`/`recovery` event,
then a matching verification result. The first successful Northstar task
alone does not demonstrate recovery.

## 7. Source code structure

```text
centralign-autonomous-worker/
├── app/
│   ├── main.py                 FastAPI dashboard, sandbox UIs and task APIs
│   ├── db.py                   SQLite state, invoice and support records
│   ├── config.py               Gemma/Ollama, browser and approval settings
│   ├── agent/
│   │   ├── gemma.py            Local Ollama /api/chat client + strict JSON schema
│   │   ├── policy.py           Gemma decision validation, allowlists and safety
│   │   ├── interpret.py        Invoice goal understanding with Gemma proposal
│   │   ├── tickets.py          Ticket goal parsing
│   │   ├── planner_v6.py       Validated Gemma task decomposition + action/recovery decisions
│   │   ├── reactive.py         Observed state, dynamic tool affordances, safe recovery
│   │   ├── runner.py           Task controller and event history
│   │   ├── browser_v4.py       Playwright semantic DOM control and recording
│   │   └── browser.py          Browser and HTML transport adapters
│   └── templates/, static/     Company web apps and dashboard
├── scripts/
│   ├── setup_mac_m4.sh         Apple Silicon installation
│   ├── check_mac_m4.py         Real Ollama and Chromium checks
│   ├── record_live_demo.py     Real Chromium video recording
│   ├── demo.py                 API-based demo scenario driver
│   └── evaluate.py             Four synthetic ticket classification checks
├── tests/                      Protocol, security and workflow tests
├── docs/                       Architecture, evaluation and walkthrough
└── .env.example                Optional configuration
```

**Model ownership:** `gemma4:e2b` is an existing Google open-weight model running through Ollama. This project does **not** train it. The engineering contribution is the tool-using agent runtime, browser controller, state machine, policy validation, approvals, recovery and verification.

## 8. Architecture and safety

```text
Natural-language instruction
    ↓
Task identification + constrained goal interpreter
    ↓
Gemma 4 E2B via local Ollama → bounded structured suggestion
    ↓
Validated business goal → observable goal-state planner
    ↓
Browser control (Playwright) or explicit HTTP test transport
    ↓
Observe → select permitted action → execute → reobserve
    ↓
Approval/duplicate/urgency checks enforced by Python
    ↓
Independent record read-back → evidence + audit trail
```

Untrusted invoice/ticket text cannot introduce new tools. The local model endpoint is restricted to loopback HTTP. No external credentials are needed. Payments, deletion, third-party browsing and email sends are not supported. In v6, Gemma **also** generates the initial decomposed plan (with an observable `gemma_validated` or fallback marker) and proposes dynamically allowed alternatives based on the latest state and errors. The symbolic planner still computes hard prerequisites. It is an adaptive **bounded** agent, not an unrestricted code-running or arbitrary-site agent. A model-produced plan never removes approvals, target idempotency checks, or completion verification.

## 9. New v6 planning and recovery design

The user supplies **only the objective**, not the implementation steps. Gemma receives the parsed goal, descriptions of allowed skills, and mandatory safety milestones. It returns a structured `steps` array. The validator accepts safe optional refresh actions but refuses a plan that skips source reading, duplicate checking, approval (for invoice writes), or verification.

At execution time the worker observes its actual state (which source was found, which facts were extracted, target lookup, approval, attempt count, previous failures) and computes permitted next actions. Gemma may choose among those actions; **it cannot call any tool outside the allowlist**. A bounded rule fallback is explicitly disclosed in the log rather than falsely attributed to the model.

| Unexpected state | Real fallback operation | Condition to stop |
|---|---|---|
| Source search returns no match | Search the wider inbox, re-filter the right vendor/ticket | Still absent → request clarification |
| Source page fails to open | Refresh inbox and select the source again | Second failure → stop safely |
| Uncertain HTTP 503 during a write | First read target; if absent, choose reobserve or reopen form and retry | Three failed writes → fail or ask human |
| Model requests another view before write | Recheck target for duplicates or reopen submission form | Repeat alternative at most once per stage |
| Verification mismatch | Perform one additional independent readback | Persistent mismatch → stop/escalate (never claim success) |

See `docs/V6_AUTONOMY_DESIGN.md` for the exact policy boundaries, HLD, LLD and the planning algorithm. The dashboard's task trace includes `gemma_task_decomposition`, `adaptive_decision` and `recovery` events.

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `ollama: command not found` | Install and launch Ollama from <https://ollama.com/download>. |
| Model unavailable / `gemma4:e2b` missing | `ollama pull gemma4:e2b`, then `ollama list` and `python scripts/check_mac_m4.py`. |
| Ollama connection refused | Launch the Ollama app or `ollama serve` in another Terminal. |
| Slow first request | Local model loads into unified memory on first inference; wait for the first call, then review the task trace. |
| Browser binary missing | `python -m playwright install chromium`. |
| Rosetta / wrong Python architecture | `uname -m` and `python -c 'import platform; print(platform.machine())'` should both print `arm64`. |
| Port 8000 already occupied | Stop the old application before running the demo recorder. |
| API reports `needs_input` | Specify an existing vendor or ticket number and resubmit the clarification. |
| Run tests without Ollama | `MODEL_BACKEND=rules python -m pytest -q`; this only validates deterministic workflows, not actual Gemma inference. |

## 11. Limitations and submission

Two sandbox workflows only; small local Gemma E2B may make incorrect predictions; model calls can add latency; browser navigation may be sensitive to layout changes; no production authentication, real enterprise integrations or distributed task workers. The model weights are not included in the ZIP. Real local inference and a full browser task **must be verified on the target Mac** before declaring the live demonstration successful.

For submission, provide the repository, this README, `docs/ARCHITECTURE.md`, `docs/EVALUATION.md` and a genuine screen recording captured by `scripts/record_live_demo.py`. See `SUBMISSION.md`.
