.PHONY: install model browser run run-browser run-http check-mac test demo demo-live clean

install:
	python -m pip install -e '.[test]'

model:
	ollama pull gemma4:e2b

browser:
	python -m playwright install chromium

run:
	MODEL_BACKEND=gemma EXECUTION_MODE=browser python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

run-browser:
	MODEL_BACKEND=gemma EXECUTION_MODE=browser python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

run-http:
	MODEL_BACKEND=gemma EXECUTION_MODE=http python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

check-mac:
	python scripts/check_mac_m4.py

test:
	python -m pytest -q

demo:
	python scripts/demo.py --scenario all

demo-live:
	python scripts/record_live_demo.py --headful

clean:
	rm -rf .pytest_cache build dist *.egg-info
