"""Integration tests verifying Generator falls back to dummy template when LLM is unavailable."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "Output"


def test_llm_disabled_task_completes_pipeline(
    parser_url, api_client, docker_services, cleanup_workspace, unique_top_module
):
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": "simple counter",
        "max_iterations": 1,
    }

    resp = api_client.post(f"{parser_url}/v1/workflow/run", json=payload, timeout=120.0)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success", f"API call failed: {body}"

    data = body["data"]
    assert data["success"] is True, f"Workflow did not succeed: {data}"
    assert data["final_stage"] == "archive_success", (
        f"Unexpected final stage: {data.get('final_stage')}"
    )

    task_id = data["task_id"]
    spec_path = (
        OUTPUT_DIR
        / task_id
        / "Result"
        / "shared_workspace"
        / "specs"
        / "SpecReg_iter0.json"
    )
    rtl_path = (
        OUTPUT_DIR
        / task_id
        / "Result"
        / "shared_workspace"
        / "rtl"
        / f"{unique_top_module}.v"
    )

    assert spec_path.exists(), f"SpecReg not found at {spec_path}"
    assert rtl_path.exists(), f"RTL file not found at {rtl_path}"


def test_llm_disabled_complex_task_completes(
    parser_url, api_client, docker_services, cleanup_workspace, unique_top_module
):
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": "rv32i processor",
        "max_iterations": 1,
    }

    resp = api_client.post(f"{parser_url}/v1/workflow/run", json=payload, timeout=120.0)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success", f"API call failed: {body}"

    data = body["data"]
    final_stage = data.get("final_stage")
    assert final_stage is not None, (
        f"Task did not reach a final stage; data={data}"
    )
    assert final_stage in ("archive_success", "archive_failed"), (
        f"Task stuck or in unexpected stage: {final_stage}"
    )

    task_id = data["task_id"]
    rtl_path = (
        OUTPUT_DIR
        / task_id
        / "Result"
        / "shared_workspace"
        / "rtl"
        / f"{unique_top_module}.v"
    )
    assert rtl_path.exists(), f"RTL file not found at {rtl_path}"


def test_llm_fallback_marker_in_transcript(
    parser_url, api_client, docker_services, cleanup_workspace, unique_top_module
):
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": "simple counter",
        "max_iterations": 1,
    }

    resp = api_client.post(f"{parser_url}/v1/workflow/run", json=payload, timeout=120.0)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"

    task_id = body["data"]["task_id"]

    detail_resp = api_client.get(f"{parser_url}/v1/tasks/{task_id}", timeout=30.0)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["status"] == "success"

    data = detail["data"]
    trace_summary = data.get("trace_summary", [])

    assert len(trace_summary) > 0, (
        "trace_summary is empty -- pipeline likely did not complete"
    )
    any_verdict = any("verdict=" in entry for entry in trace_summary)
    assert any_verdict, (
        f"No verdict entries found in trace_summary: {trace_summary}"
    )

    trace = body["data"].get("trace", [])
    parser_init_steps = [s for s in trace if s.get("node") == "parser_initialize"]
    assert len(parser_init_steps) > 0, "parser_initialize not found in trace"

    detail_text = parser_init_steps[0].get("detail", "")
    assert "disabled" in detail_text.lower() or "skipped" in detail_text.lower(), (
        f"parser_initialize detail does not indicate LLM was disabled; "
        f"got: {detail_text!r}"
    )
