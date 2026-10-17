#!/usr/bin/env bash
# Run from ANY working directory; builds evidence in data/ (gitignored).
# Requires local Ollama + model, macOS ARM64, Chromium and ffmpeg installed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -f .venv/bin/activate ]]; then
  echo 'ERROR: .venv missing. Run: python3.12 -m venv .venv && source .venv/bin/activate && python -m pip install -e '''.[test]'''' >&2
  exit 1
fi
source .venv/bin/activate
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo 'ERROR: ffmpeg unavailable. Install on Mac: brew install ffmpeg' >&2
  exit 1
fi
if ! command -v ollama >/dev/null 2>&1; then
  echo 'ERROR: Ollama unavailable. Install and start the Ollama app.' >&2
  exit 1
fi
OUT="data/submission_checks/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"
export OLLAMA_TIMEOUT="${OLLAMA_TIMEOUT:-240}"
echo "Evidence directory: $ROOT/$OUT"
echo '1/4 Automated pytest suite (isolated data; mocked Ollama)'
python -m pytest -q 2>&1 | tee "$OUT/pytest.txt"
echo '2/4 Real local Gemma 4 E2B inference diagnostic'
python scripts/diagnose_gemma.py --full 2>&1 | tee "$OUT/gemma_diagnostic.txt"
echo '3/4 Mac ARM64, model + Chromium diagnostics'
python scripts/check_mac_m4.py 2>&1 | tee "$OUT/mac_diagnostic.txt"
echo '4/4 Four true Chromium runs: invoice, 503 recovery, support, human approval'
python scripts/record_live_demo.py --headful --strict --task-timeout 360 2>&1 | tee "$OUT/live_demo.txt"
if [[ ! -s docs/CentrAlign_v6_REAL_BROWSER_DEMO.mp4 ]]; then
  echo 'ERROR: Live MP4 not created' >&2
  exit 1
fi
# Extract the latest isolated demo's run summary into the validation bundle
python - "$OUT" <<'PY_COPY_SUMMARY'
from pathlib import Path
import shutil, sys
summaries=list(Path('data/recorded_demos').glob('*/run_summary.json'))
if not summaries:
    raise SystemExit('ERROR: no run_summary.json produced by the live recorder')
latest=max(summaries,key=lambda p:p.stat().st_mtime)
shutil.copy2(latest,Path(sys.argv[1])/'run_summary.json')
PY_COPY_SUMMARY
printf '\nALL CHECKS PASSED. Review actual video: %s\n' "$ROOT/docs/CentrAlign_v6_REAL_BROWSER_DEMO.mp4"
printf 'Validation logs: %s\n' "$ROOT/$OUT"
printf 'Do not commit the generated video or sandbox databases. Upload the video externally and add its public link to README.md.\n'
