# CentrAlign AI — Autonomous Task Worker

CentrAlign AI is a local AI worker that accepts a natural-language business task, operates a simulated company application, and verifies that the requested outcome was achieved. It combines **Gemma 4 E2B** running locally through **Ollama**, **Playwright** browser automation, a **FastAPI** web interface, and **SQLite** for task and business records.

The prototype supports two workflows: **invoice processing** and **support-ticket triage**. Its applications and records are simulated; it does not access real company systems.

## What the worker does

| Example request | Expected behavior |
| --- | --- |
| `Record the latest invoice from Northstar Labs.` | Find the latest matching invoice, extract its details, check for duplicates, record it, and verify the saved ledger entry. |
| `Record the latest invoice from Acme Services.` | Follow the invoice workflow and request human approval if the amount exceeds the configured threshold. |
| `Check whether invoice HO-88 from Harbor Office was recorded.` | Check the ledger without creating a new entry. |
| `Triage ticket TKT-402 and assign it to the appropriate team.` | Read the ticket, determine its category and priority, create a support case, and verify the result. |

## How it works

```text
Natural-language request
          |
          v
Interpret the goal with local Gemma
          |
          v
Generate and validate an action plan
          |
          v
Observe the company application's current state
          |
          v
Choose an allowed action and operate Chromium
          |
          v
Read the result, adapt if necessary, and continue
          |
          v
Verify the saved outcome and produce an audit trail
```

1. **Understand:** The worker interprets the request and identifies the supported business operation and relevant records.
2. **Plan:** Gemma proposes a structured sequence of steps. The application validates the plan against required workflow and safety rules.
3. **Act and observe:** Playwright navigates the simulated invoice or helpdesk application, finds records, reads documents, and fills forms. The worker observes the state after actions instead of assuming they succeeded.
4. **Handle exceptions:** The worker can retry bounded failures, use permitted alternative searches, recheck for an existing record, or request clarification. High-value invoice writes require human approval.
5. **Verify:** After a write, the worker reads the persisted record and compares it with the source information. The task trace records actions, model decisions, errors, and verification evidence.

Gemma suggests plans and actions, but **Python-enforced business rules** restrict available tools, require approval where applicable, and prevent unchecked duplicate writes. If a model response is invalid, the worker can use a clearly labeled, validated fallback.

## Requirements

- macOS on Apple Silicon (the provided setup script targets MacBook M4), with Python 3.12 recommended.
- [Ollama](https://ollama.com/download) for local Gemma inference.
- Internet access for the initial dependency, browser, and model downloads.

No cloud AI API key is required. The Gemma model is downloaded separately and is not stored in the repository.

## Installation

From the repository directory, open Ollama and run the setup script:

```bash
open -a Ollama
bash scripts/setup_mac_m4.sh
source .venv/bin/activate
```

The script prepares the Python environment, installs dependencies and Playwright Chromium, downloads `gemma4:e2b` if necessary, and checks the local setup.

To install manually instead:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python -m playwright install chromium
ollama pull gemma4:e2b
```

## Run the application

Ensure Ollama is running, activate the virtual environment, then launch:

```bash
source .venv/bin/activate
OLLAMA_TIMEOUT=240 HEADLESS=false make run-browser
```

Open **http://127.0.0.1:8000** in your browser. `HEADLESS=false` makes the automated Chromium window visible. For background browser execution, omit that setting.

In the dashboard:

1. Enter a natural-language instruction under **Assign a task**, or select an example scenario.
2. Click **Run autonomous task**.
3. Follow the **Action plan** and **Agent execution trace** to see the chosen steps and browser actions.
4. Respond to approval or clarification requests, if prompted.
5. Open **Verification evidence** or the browser recording to review the outcome.

To explore recovery, the dashboard can inject a one-time failure for an invoice or support-case write. Run the scenario using a record not already saved, then inspect the recovery and verification events.

## Tests

Run the automated suite from the activated virtual environment:

```bash
python -m pytest -q
```

To check the actual local Gemma model and browser installation:

```bash
OLLAMA_TIMEOUT=240 python scripts/diagnose_gemma.py --full
python scripts/check_mac_m4.py
```

The unit/integration suite uses isolated test data and simulated model replies; the diagnostic commands contact the locally installed model.

## Project structure

```text
app/                 FastAPI app, simulated business UIs, database, and agent
app/agent/           Goal interpretation, Gemma client, planning, policies, browser tools
scripts/             Local setup, diagnostics, evaluation, and demo tools
tests/               Workflow, safety, and integration tests
docs/                Architecture and additional technical documentation
pyproject.toml        Python dependencies and project configuration
```

## Scope and limitations

CentrAlign AI is a **bounded prototype**, not a general-purpose desktop agent. It operates only the included invoice and support applications. It does not send emails, execute payments, access production accounts, or browse arbitrary third-party sites. Model output can be incorrect or slow, and browser automation may require maintenance if the application interface changes.

All business records used in the prototype are synthetic. For implementation details, see [Architecture](docs/ARCHITECTURE.md).
