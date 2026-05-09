"""HTTP tests for frontend Web UI routes."""

import httpx

FRONTEND_URL = "http://localhost:8002"


def test_frontend_health():
    """GET /health returns 200 with status=success."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{FRONTEND_URL}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["service"] == "frontend"


def test_frontend_index_returns_html():
    """GET / returns HTML page."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(FRONTEND_URL)
    assert resp.status_code == 200
    # Should be HTML with form
    html = resp.text.lower()
    assert "<form" in html
    assert "top_module" in html or "submit" in html


def test_frontend_tasks_page():
    """GET /tasks returns HTML."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{FRONTEND_URL}/tasks")
    assert resp.status_code == 200
    html = resp.text.lower()
    assert "task" in html or "history" in html


def test_frontend_services_page():
    """GET /services returns HTML with service info."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{FRONTEND_URL}/services")
    assert resp.status_code == 200
    html = resp.text.lower()
    assert "parser" in html


def test_frontend_config_page():
    """GET /config returns HTML config form."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{FRONTEND_URL}/config")
    assert resp.status_code == 200
    html = resp.text.lower()
    assert "config" in html or "llm" in html or "timeout" in html


def test_frontend_task_detail_not_found():
    """GET /tasks/nonexistent returns page with error message."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{FRONTEND_URL}/tasks/TASK_NONEXISTENT_XYZ")
    assert resp.status_code == 200  # Should render page, not crash
    html = resp.text.lower()
    assert "not found" in html or "error" in html or "no data" in html


def test_frontend_submit_task_form():
    """POST /tasks/submit with valid form data triggers workflow."""
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{FRONTEND_URL}/tasks/submit",
            data={
                "top_module": "test_frontend_submit",
                "raw_input_text": "simple buffer module",
                "max_iterations": "1",
                "intent": "",
                "llm_enabled": "false",
                "llm_model": "",
            },
        )
    assert resp.status_code == 200
    html = resp.text.lower()
    # Should contain task_id or success indicator
    assert "task_" in html or "submitted" in html or "success" in html


def test_config_save_persists():
    """POST /config/save updates configuration."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(
            f"{FRONTEND_URL}/config/save",
            data={
                "agvs4rtl_llm_enabled": "false",
                "agvs4rtl_llm_base_url": "",
                "agvs4rtl_llm_api_key": "",
                "agvs4rtl_llm_model": "",
                "agvs4rtl_llm_profile": "default",
                "verify_service_timeout_seconds": "240",
                "gen_service_timeout_seconds": "600",
                "agvs4rtl_llm_timeout_seconds": "300",
            },
        )
    assert resp.status_code == 200
    html = resp.text.lower()
    assert "success" in html or "saved" in html or "updated" in html or "config" in html
