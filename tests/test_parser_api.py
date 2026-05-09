"""Integration tests for new Parser API endpoints (Tasks 1-2)."""

import httpx
from src.common.models import (
    AGVS4RTL_INJECT_FAIL_SEMANTIC,
)


def test_list_tasks_returns_array(parser_url, api_client, docker_services, unique_top_module):
    """GET /v1/tasks returns paginated task array."""
    # First, create a task so we have at least one
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": "simple counter",
        "max_iterations": 1,
    }
    resp = api_client.post(f"{parser_url}/v1/workflow/run", json=payload, timeout=120.0)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    
    # Now list tasks
    resp2 = api_client.get(f"{parser_url}/v1/tasks", timeout=30.0)
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["status"] == "success"
    assert "tasks" in body2["data"]
    tasks = body2["data"]["tasks"]
    assert isinstance(tasks, list)
    assert len(tasks) >= 1
    # Check first task has required fields
    first = tasks[0]
    assert "task_id" in first
    assert "top_module" in first
    assert "created_at" in first


def test_list_tasks_pagination(parser_url, api_client, docker_services):
    """GET /v1/tasks respects page and per_page params."""
    resp = api_client.get(f"{parser_url}/v1/tasks?page=1&per_page=3", timeout=30.0)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    data = body["data"]
    tasks = data["tasks"]
    assert len(tasks) <= 3
    assert data["page"] == 1
    assert data["per_page"] == 3
    assert data["total"] >= len(tasks)


def test_get_task_detail_valid(parser_url, api_client, docker_services, unique_top_module):
    """GET /v1/tasks/{task_id} returns detail for existing task."""
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": "simple adder",
        "max_iterations": 1,
    }
    resp = api_client.post(f"{parser_url}/v1/workflow/run", json=payload, timeout=120.0)
    body = resp.json()
    task_id = body["data"]["task_id"]
    
    resp2 = api_client.get(f"{parser_url}/v1/tasks/{task_id}", timeout=30.0)
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["status"] == "success"
    data = body2["data"]
    assert data["task_id"] == task_id
    assert data["top_module"] == unique_top_module
    assert "artifact_paths" in data
    assert "trace_summary" in data


def test_get_task_detail_not_found(parser_url, api_client):
    """GET /v1/tasks/{nonexistent} returns error."""
    resp = api_client.get(f"{parser_url}/v1/tasks/TASK_NONEXISTENT_12345", timeout=10.0)
    body = resp.json()
    # Should return error, not 500 crash
    assert body["status"] == "error" or resp.status_code == 404 or body["data"] is None


def test_get_task_status(parser_url, api_client, docker_services, unique_top_module):
    """GET /v1/tasks/{task_id}/status returns stage and iteration."""
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": "simple mux",
        "max_iterations": 1,
    }
    resp = api_client.post(f"{parser_url}/v1/workflow/run", json=payload, timeout=120.0)
    task_id = resp.json()["data"]["task_id"]
    
    resp2 = api_client.get(f"{parser_url}/v1/tasks/{task_id}/status", timeout=10.0)
    assert resp2.status_code == 200
    body2 = resp2.json()
    data = body2["data"]
    assert "stage" in data
    assert "iteration" in data
    assert data["iteration"] >= 0
    assert data["stage"] in ("initializing", "generating", "verifying", "retrying", "completed", "failed")


def test_get_services_health(parser_url, api_client, docker_services):
    """GET /v1/services/health returns all 3 services."""
    resp = api_client.get(f"{parser_url}/v1/services/health", timeout=30.0)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    services = body["data"]["services"]
    assert len(services) >= 3
    service_names = [s["service"] for s in services]
    assert "parser" in service_names
    assert any("gen" in name.lower() for name in service_names)
    assert any("verify" in name.lower() for name in service_names)
    # All should be reachable when Docker is running
    assert all(s["reachable"] for s in services)


def test_regression_existing_workflow(parser_url, api_client, docker_services, unique_top_module):
    """POST /v1/workflow/run response format unchanged."""
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": AGVS4RTL_INJECT_FAIL_SEMANTIC,
        "max_iterations": 1,
    }
    resp = api_client.post(f"{parser_url}/v1/workflow/run", json=payload, timeout=120.0)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    data = body["data"]
    assert "task_id" in data
    assert "final_stage" in data
    assert "success" in data
    assert "trace" in data
    assert isinstance(data["trace"], list)
