#!/usr/bin/env bash
# Install CentrAlign AI using native Apple Silicon Python. Google Gemma 4 E2B via local Ollama (no cloud API key).
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo 'ERROR: This setup script is intended for macOS.' >&2
  exit 1
fi
if [[ "$(uname -m)" != "arm64" ]]; then
  echo 'ERROR: Terminal is not running natively on Apple Silicon (arm64).' >&2
  echo 'Close Rosetta/Intel Terminal and open a native macOS Terminal.' >&2
  exit 1
fi

PYTHON=""
# Prefer known-supported ARM64 builds, while accepting another compatible version.
for candidate in python3.12 python3.13 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" - <<'PY'
import platform, sys
assert (3, 10) <= sys.version_info[:2] < (3, 15)
assert platform.machine() == 'arm64', 'Python is running under Rosetta'
PY
    then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo 'ERROR: No native ARM64 Python 3.10–3.14 found.' >&2
  echo 'Recommended: brew install python@3.12' >&2
  echo 'Then reopen Terminal and run this script again.' >&2
  exit 1
fi

echo "Using $($PYTHON --version) from $(command -v "$PYTHON")"
"$PYTHON" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
python -m playwright install chromium

echo
if ! command -v ollama >/dev/null 2>&1; then
  echo 'ERROR: Install Ollama for Mac from https://ollama.com/download and start it.' >&2
  exit 1
fi
echo 'Pulling Gemma 4 E2B (one-time download)...'
ollama pull gemma4:e2b
echo 'Running Gemma and Chromium diagnostics...' 
python scripts/check_mac_m4.py

echo
echo 'Setup complete. To launch the strict Chromium worker:'
echo '  source .venv/bin/activate'
echo '  make run-browser'
echo 'Then visit: http://127.0.0.1:8000'
