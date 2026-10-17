"""Real HTTP integration fixture: launches the actual sandbox app, isolated SQLite."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def sandbox(tmp_path):
    root=Path(__file__).resolve().parents[1]
    folder=tmp_path
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port=sock.getsockname()[1]
    env=os.environ.copy()
    env.update({"DATABASE_PATH":str(folder/"company.sqlite3"),
                "ARTIFACTS_DIR":str(folder/"evidence"),
                "EXECUTION_MODE":"http", # deterministic CI; real browser mode runs locally
                "APP_PORT":str(port),"MODEL_BACKEND":"rules"})
    process=subprocess.Popen([sys.executable,"-m","uvicorn","app.main:app","--port",str(port),
                              "--host","127.0.0.1","--log-level","warning"],
                             cwd=str(root),env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    base=f"http://127.0.0.1:{port}"
    client=httpx.Client(base_url=base,timeout=15)
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Server startup failed: "+process.stderr.read().decode())
            try:
                if client.get("/health").status_code==200:
                    break
            except httpx.RequestError:
                pass
            time.sleep(.1)
        else:
            raise RuntimeError("Server did not start")
        yield client
    finally:
        client.close()
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill()
        process.stderr.close()


def until_status(client,task_id,expected,timeout=18):
    finish=time.monotonic()+timeout
    while time.monotonic()<finish:
        record=client.get(f"/api/tasks/{task_id}").json()
        if record["status"] in expected:
            return record
        time.sleep(.09)
    raise AssertionError(f"Task did not reach {expected}: {record['status']} ({record.get('error')})")


@pytest.fixture
def run_task(sandbox):
    def run(text,expected=("completed","failed","needs_input","awaiting_approval")):
        response=sandbox.post("/api/tasks",json={"instruction":text})
        assert response.status_code==202,response.text
        return until_status(sandbox,response.json()["task_id"],expected)
    return run
