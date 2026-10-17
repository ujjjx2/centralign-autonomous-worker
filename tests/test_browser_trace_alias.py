"""Trace naming contract for the UI, API and media smoke test.

Uses an in-memory fake Playwright tracer because the naming regression must
be catchable even when Chromium is not installed on a CI machine.
"""
from pathlib import Path
from types import SimpleNamespace
import zipfile

from app.agent.browser_v4 import VisualBrowserTools


class FakeTracing:
    def stop(self, path):
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("trace.trace", "a" * 800)


class FakeContext:
    tracing = FakeTracing()

    def close(self):
        pass


def test_trace_alias_matches_test_and_api_filename(tmp_path):
    tool = VisualBrowserTools(
        "http://127.0.0.1:8000",
        SimpleNamespace(artifacts_dir=tmp_path),
        task_id="test",
    )
    tool.artifacts.mkdir(parents=True)
    tool.ctx = FakeContext()
    tool._shutdown()
    canonical = tool.artifacts / "playwright-trace.zip"
    numbered = tool.artifacts / "playwright-trace-0.zip"
    assert canonical.is_file() and numbered.is_file()
    assert canonical.read_bytes() == numbered.read_bytes()
    assert zipfile.is_zipfile(canonical)


def test_latest_restarted_session_becomes_canonical(tmp_path):
    tool = VisualBrowserTools(
        "http://127.0.0.1:8000",
        SimpleNamespace(artifacts_dir=tmp_path),
        task_id="test",
    )
    tool.artifacts.mkdir(parents=True)
    tool.ctx = FakeContext()
    tool._shutdown()
    tool.restarts = 1
    tool.ctx = FakeContext()
    tool._shutdown()
    assert (tool.artifacts / "playwright-trace-0.zip").exists()
    assert (tool.artifacts / "playwright-trace-1.zip").exists()
    assert (tool.artifacts / "playwright-trace.zip").read_bytes() == (
        tool.artifacts / "playwright-trace-1.zip"
    ).read_bytes()
