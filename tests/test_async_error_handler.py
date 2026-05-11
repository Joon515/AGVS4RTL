"""Integration tests for async crash detection feature.

Verifies that tasks that crash asynchronously:
1. Report "failed" stage on the status endpoint (not stuck at "initializing").
2. Produce an error.json artifact on the host filesystem.
3. Normal (non-crashing) tasks still complete successfully.
"""

import json
import time
from pathlib import Path

import httpx

from src.common.models import AGVS4RTL_INJECT_FAIL_SEMANTIC

# ---------------------------------------------------------------------------
# Project root resolution -- mirrors conftest.py
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "Output"


def test_crashed_task_returns_failed_status(
    parser_url,
    api_client,
    docker_services,
    cleanup_workspace,
    unique_top_module,
):
    """Submit a task that will crash (non-existent module), poll status for
    up to 30 s, and assert the reported stage is ``"failed"`` (not stuck at
    ``"initializing"``)."""
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": "non-existent module crash test",
        "max_iterations": 1,
    }

    # Use the async submit endpoint so the task runs in the background via
    # _run_workflow_with_error_handler.
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

    # Poll status until "failed" or deadline.
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
            if last_stage == "failed":
                break
        time.sleep(1)

    assert last_stage == "failed", (
        f"Expected stage 'failed', got '{last_stage}' "
        f"after 30 s polling (task_id={task_id})"
    )


def test_crash_writes_error_artifact(
    parser_url,
    api_client,
    docker_services,
    cleanup_workspace,
    unique_top_module,
):
    """After a crashed task, verify ``error.json`` exists on the host
    filesystem and contains the ``"error"`` and ``"stage"`` keys."""
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": "another crash to produce error.json",
        "max_iterations": 1,
    }

    submit_resp = api_client.post(
        f"{parser_url}/v1/workflow/submit", json=payload, timeout=30.0
    )
    assert submit_resp.status_code == 200
    task_id = submit_resp.json()["data"]["task_id"]

    # Wait up to 30 s for error.json to appear on the host filesystem.
    error_path = OUTPUT_DIR / task_id / "error.json"
    deadline = time.time() + 30
    while time.time() < deadline:
        if error_path.exists():
            break
        time.sleep(1)

    assert error_path.exists(), (
        f"error.json not found at {error_path} "
        f"(task_id={task_id})"
    )

    error_data = json.loads(error_path.read_text(encoding="utf-8"))
    assert "error" in error_data, (
        f"error.json missing 'error' key: {error_data}"
    )
    assert "stage" in error_data, (
        f"error.json missing 'stage' key: {error_data}"
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
