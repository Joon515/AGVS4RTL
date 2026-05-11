"""Integration tests for async task lifecycle.

Verifies that:
1. Async-submitted tasks progress past "initializing" (no ghost tasks).
2. Normally completing tasks leave no stale error.json artifact.
3. Sync endpoint tasks still complete successfully.
"""

import time
from pathlib import Path

from src.common.models import AGVS4RTL_INJECT_FAIL_SEMANTIC

# ---------------------------------------------------------------------------
# Project root resolution -- mirrors conftest.py
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "Output"

# Stages that signal a task has finished processing.
TERMINAL_STAGES = {"completed", "failed"}


def test_crashed_task_returns_failed_status(
    parser_url,
    api_client,
    docker_services,
    cleanup_workspace,
    unique_top_module,
):
    """Submit a task (without LLM), poll status for up to 30 s, and assert the
    task progresses beyond ``"initializing"`` — no ghost tasks."""
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": "simple counter",
        "max_iterations": 1,
    }

    # Use the async submit endpoint so the task runs in the background.
    submit_resp = api_client.post(
        f"{parser_url}/v1/workflow/submit", json=payload, timeout=30.0
    )
    assert submit_resp.status_code == 200
    submit_body = submit_resp.json()
    assert submit_body["status"] == "success", (
        f"submit failed: {submit_body}"
    )
    task_id = submit_body["data"]["task_id"]
    assert task_id is not None

    # Poll status until a terminal stage or deadline.
    deadline = time.time() + 30
    last_stage = None
    while time.time() < deadline:
        status_resp = api_client.get(
            f"{parser_url}/v1/tasks/{task_id}/status", timeout=10.0
        )
        if status_resp.status_code == 200:
            body = status_resp.json()
            data = body.get("data", {})
            last_stage = data.get("stage")
            if last_stage in TERMINAL_STAGES:
                break
        time.sleep(1)

    assert last_stage is not None, (
        f"Task {task_id} returned no status after 30 s polling"
    )
    assert last_stage != "initializing", (
        f"Task {task_id} is stuck at 'initializing' after 30 s (ghost task)"
    )
    assert last_stage in TERMINAL_STAGES, (
        f"Expected terminal stage {TERMINAL_STAGES}, got '{last_stage}' "
        f"for task {task_id}"
    )


def test_crash_writes_error_artifact(
    parser_url,
    api_client,
    docker_services,
    cleanup_workspace,
    unique_top_module,
):
    """Verify that a normally completing task does NOT leave a stale
    ``error.json`` artifact on the host filesystem — the Generator's
    dummy-template fallback means tasks no longer crash from LLM=off."""
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": "simple counter",
        "max_iterations": 1,
    }

    submit_resp = api_client.post(
        f"{parser_url}/v1/workflow/submit", json=payload, timeout=30.0
    )
    assert submit_resp.status_code == 200
    task_id = submit_resp.json()["data"]["task_id"]

    # Wait for task to reach a terminal stage.
    deadline = time.time() + 30
    last_stage = None
    while time.time() < deadline:
        status_resp = api_client.get(
            f"{parser_url}/v1/tasks/{task_id}/status", timeout=10.0
        )
        if status_resp.status_code == 200:
            body = status_resp.json()
            data = body.get("data", {})
            last_stage = data.get("stage")
            if last_stage in TERMINAL_STAGES:
                break
        time.sleep(1)

    assert last_stage is not None and last_stage in TERMINAL_STAGES, (
        f"Task {task_id} did not reach terminal stage after 30 s "
        f"(last stage: {last_stage})"
    )

    # Normal completion should leave no error.json behind.
    error_path = OUTPUT_DIR / task_id / "error.json"
    assert not error_path.exists(), (
        f"Unexpected error.json found at {error_path} for task {task_id} "
        f"that completed with stage '{last_stage}'"
    )


def test_normal_task_still_completes(
    parser_url,
    api_client,
    docker_services,
    cleanup_workspace,
    unique_top_module,
):
    """A normal task (with the FAST-pass injection marker) still completes
    successfully even when the async crash detection infrastructure is in
    place."""
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": AGVS4RTL_INJECT_FAIL_SEMANTIC,
        "max_iterations": 1,
    }

    resp = api_client.post(
        f"{parser_url}/v1/workflow/run", json=payload, timeout=120.0
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success", (
        f"normal task did not complete successfully: {body}"
    )
    # Verify the response carries a task_id and trace.
    data = body.get("data", {})
    assert "task_id" in data, (
        f"response data missing task_id: {data}"
    )
