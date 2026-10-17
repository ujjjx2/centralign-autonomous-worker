# Apple Silicon setup

Install Ollama (<https://ollama.com/download>) and start the app. In the extracted project directory run:

```bash
bash scripts/setup_mac_m4.sh
source .venv/bin/activate
HEADLESS=false make run-browser
```

The installer downloads the public `gemma4:e2b` weights once with `ollama pull gemma4:e2b`. The model runs on your device through Ollama; no cloud API key is used. `python scripts/check_mac_m4.py` validates local inference and Chromium. Details and troubleshooting are in the root README.
