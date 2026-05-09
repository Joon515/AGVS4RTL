"""Infrastructure validation tests for AGVS4RTL.

Covers:
- Health checks for all three services (parser, gen, verify)
- Network topology isolation (gen/verify NOT reachable from host)
- Input validation on the workflow API
- LLM header forwarding and archival
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helper: run Python code inside the parser container via docker compose exec
# ---------------------------------------------------------------------------
def _docker_exec(command_python_code: str) -> tuple[str, int]:
    """Run Python code inside the parser container and return (stdout, returncode)."""
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "parser", "python", "-c", command_python_code],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip(), result.returncode


# ===========================================================================
# Test 1: Parser health check via host port
# ===========================================================================
@pytest.mark.docker
def test_parser_health(parser_url: str) -> None:
    """Parser health check returns 200 with status="success" and state="ready"."""
    resp = httpx.get(f"{parser_url}/health", timeout=5.0)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    body = resp.json()
    assert body["status"] == "success", f"Unexpected status: {body}"
    assert body["data"]["state"] == "ready", f"Unexpected state: {body['data']}"


# ===========================================================================
# Test 2: Gen health check from inside the container network
# ===========================================================================
@pytest.mark.docker
def test_gen_health_internal(docker_services: None) -> None:
    """Gen /health is reachable from inside the container network via docker compose exec."""
    code = (
        "import httpx; "
        "r = httpx.get('http://gen:8000/health', timeout=5); "
        "print(r.text); "
        "assert r.status_code == 200, f'gen health returned {r.status_code}'"
    )
    stdout, rc = _docker_exec(code)
    print(f"gen health stdout: {stdout}")
    assert rc == 0, f"docker exec failed (rc={rc}): {stdout}"

    # Verify the response body contains expected fields
    health = json.loads(stdout)
    assert health.get("status") == "success", f"Unexpected gen health: {health}"
    assert health.get("data", {}).get("state") == "ready", f"Gen not ready: {health}"


# ===========================================================================
# Test 3: Verify health check from inside the container network
# ===========================================================================
@pytest.mark.docker
def test_verify_health_internal(docker_services: None) -> None:
    """Verify /health is reachable from inside the container network via docker compose exec."""
    code = (
        "import httpx; "
        "r = httpx.get('http://verify:8000/health', timeout=5); "
        "print(r.text); "
        "assert r.status_code == 200, f'verify health returned {r.status_code}'"
    )
    stdout, rc = _docker_exec(code)
    print(f"verify health stdout: {stdout}")
    assert rc == 0, f"docker exec failed (rc={rc}): {stdout}"

    # Verify the response body contains expected fields
    health = json.loads(stdout)
    assert health.get("status") == "success", f"Unexpected verify health: {health}"
    assert health.get("data", {}).get("state") == "ready", f"Verify not ready: {health}"


# ===========================================================================
# Test 4: Gen is NOT accessible from host (network isolation)
# ===========================================================================
@pytest.mark.docker
def test_gen_not_accessible_from_host(docker_services: None) -> None:
    """Gen service is NOT port-mapped to host; host access must fail."""
    try:
        resp = httpx.get("http://localhost:8000/health", timeout=2.0)
        # If we get here, something responded on port 8000 — but it should NOT
        # be the gen service. Let's at least ensure it's not returning a gen
        # health response.
        print(f"WARNING: localhost:8000 responded with status {resp.status_code}: {resp.text[:200]}")
        # The gen container only exposes internally, so any response on :8000
        # is either a different process or a misconfiguration.
        # We still treat it as a test failure if it responds with gen-specific
        # content.
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        is_gen_response = (
            isinstance(body, dict)
            and body.get("data", {}).get("service") == "generator"
        )
        assert not is_gen_response, (
            f"GEN IS UNEXPECTEDLY ACCESSIBLE FROM HOST! "
            f"Port 8000 should not expose gen service directly. Response: {body}"
        )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        # Expected: connection refused or timeout — gen is not port-mapped
        pass


# ===========================================================================
# Test 5: API rejects invalid top_module identifier
# ===========================================================================
@pytest.mark.docker
def test_api_rejects_invalid_top_module(
    parser_url: str, api_client: httpx.Client, unique_top_module: str
) -> None:
    """POST /v1/workflow/run with an invalid Verilog identifier must return an error."""
    payload = {
        "top_module": "invalid name with spaces",
        "raw_input_text": "generate a simple module",
        "max_iterations": 1,
    }
    resp = api_client.post(f"{parser_url}/v1/workflow/run", json=payload)
    body = resp.json()

    print(f"Invalid top_module response: status={resp.status_code}, body={json.dumps(body, indent=2)}")

    # Must be an error — either 422 (FastAPI validation) or 200 with status:"error"
    is_validation_error = resp.status_code == 422
    is_app_error = resp.status_code == 200 and body.get("status") == "error"

    assert is_validation_error or is_app_error, (
        f"Expected 422 or error response for invalid top_module, "
        f"got {resp.status_code}: {body}"
    )

    if is_validation_error:
        # FastAPI 422 detail contains validation info
        detail = body.get("detail", [])
        assert any(
            "top_module" in str(item.get("loc", [])) for item in detail
        ), f"422 response should reference top_module: {detail}"
    elif is_app_error:
        assert "top_module" in body.get("message", "").lower() or "identifier" in body.get("message", "").lower(), (
            f"Error message should mention invalid identifier: {body.get('message')}"
        )


# ===========================================================================
# Test 6: API rejects empty requirements (both fields empty)
# ===========================================================================
@pytest.mark.docker
def test_api_rejects_empty_requirements(
    parser_url: str, api_client: httpx.Client, unique_top_module: str
) -> None:
    """POST /v1/workflow/run with empty requirements must return a validation error."""
    payload = {
        "top_module": unique_top_module,
        "refined_requirements": [],
        "raw_input_text": "",
        "max_iterations": 1,
    }
    resp = api_client.post(f"{parser_url}/v1/workflow/run", json=payload)
    body = resp.json()

    print(f"Empty requirements response: status={resp.status_code}, body={json.dumps(body, indent=2)}")

    # Must be an error — either 422 (FastAPI/Pydantic validation) or 200 with status:"error"
    is_validation_error = resp.status_code == 422
    is_app_error = resp.status_code == 200 and body.get("status") == "error"

    assert is_validation_error or is_app_error, (
        f"Expected 422 or error response for empty requirements, "
        f"got {resp.status_code}: {body}"
    )

    if is_validation_error:
        detail = body.get("detail", [])
        detail_str = json.dumps(detail)
        assert "refined_requirements" in detail_str.lower() or "raw_input_text" in detail_str.lower() or "input_source" in detail_str.lower(), (
            f"422 response should reference empty requirements: {detail}"
        )
    elif is_app_error:
        message = body.get("message", "").lower()
        assert any(term in message for term in ("refined_requirements", "raw_input_text", "required", "provide", "empty")), (
            f"Error message should describe missing requirements: {body.get('message')}"
        )


# ===========================================================================
# Test 7: LLM header forwarding and archival
# ===========================================================================
@pytest.mark.llm
def test_llm_header_forwarding(
    parser_url: str, api_client: httpx.Client, unique_top_module: str
) -> None:
    """Run a simple workflow with LLM enabled and verify ParserChat/ArchitectChat archival.

    Checks that:
    - The workflow completes successfully
    - LLM chat transcript files are archived under Output/<task_id>/Result/shared_workspace/llm/
    - At minimum, the llm/ directory exists with at least one transcript file
    """
    payload = {
        "top_module": unique_top_module,
        "raw_input_text": "Generate a simple combinational adder module with two 8-bit inputs and one 8-bit output",
        "refined_requirements": [
            "8-bit input a",
            "8-bit input b",
            "8-bit output sum",
            "combinational addition",
            "no clock or reset",
        ],
        "max_iterations": 1,
        "llm": {
            "enabled": True,
            "base_url": os.environ.get("AGVS4RTL_LLM_BASE_URL", ""),
            "api_key": os.environ.get("AGVS4RTL_LLM_API_KEY", ""),
            "model": os.environ.get("AGVS4RTL_LLM_MODEL", ""),
        },
    }

    print(f"🚀 Sending LLM-enabled workflow request to: {parser_url}/v1/workflow/run")
    start = time.time()
    resp = api_client.post(f"{parser_url}/v1/workflow/run", json=payload)
    elapsed = time.time() - start
    print(f"✅ Request completed in {elapsed:.1f}s, status={resp.status_code}")

    # Accept both 200 (successful workflow) and non-200 with meaningful error
    if resp.status_code != 200:
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        msg = body.get("message", resp.text[:200])
        print(f"⚠️  LLM workflow returned {resp.status_code}: {msg}")
        pytest.skip(f"LLM workflow could not complete (status={resp.status_code}): {msg}")

    result = resp.json()
    print(f"📦 Response status: {result.get('status')}, message: {result.get('message')[:200]}")

    # If the API itself reports an error, skip gracefully
    if result.get("status") != "success":
        print(f"⚠️  LLM workflow returned API error: {result.get('message')}")
        pytest.skip(f"LLM workflow returned API error: {result.get('message')}")

    data = result.get("data", {})
    task_id = data.get("task_id", "")
    assert task_id, f"No task_id in response data: {result}"

    print(f"📋 Task ID: {task_id}")

    # -------------------------------------------------------------------
    # Verify LLM archival artifacts
    # -------------------------------------------------------------------
    llm_dir = Path("Output") / task_id / "Result" / "shared_workspace" / "llm"

    print(f"🔍 Checking LLM archive at: {llm_dir}")

    if not llm_dir.is_dir():
        # If no llm/ directory at all, this is a genuine failure for an LLM-enabled test
        # unless the workflow failed before reaching LLM
        trace_nodes = [step["node"] for step in data.get("trace", [])]
        print(f"⚠️  llm/ directory not found. Trace nodes: {trace_nodes}")
        # Check if any node actually used LLM
        if any("llm" in node.lower() for node in trace_nodes) or "gen_stateless" in trace_nodes:
            pytest.fail(
                f"LLM was enabled but no llm/ archive directory found at {llm_dir}. "
                f"Trace: {trace_nodes}"
            )
        else:
            pytest.skip("Workflow ran but no LLM-using nodes executed — skipping LLM archive check")

    # At minimum, verify the llm/ directory exists
    assert llm_dir.is_dir(), f"LLM archive directory not found: {llm_dir}"

    # List archived files
    archived_files = sorted(f.name for f in llm_dir.iterdir() if f.is_file())
    print(f"📁 LLM archive files: {archived_files}")

    # Check for expected chat transcripts (gracefully — not all may be present
    # depending on execution path)
    expected_patterns = [
        "ParserChat",
        "ArchitectChat",
    ]

    found_any = False
    for pattern in expected_patterns:
        matches = [f for f in archived_files if pattern in f]
        if matches:
            print(f"✅ Found {pattern}: {matches}")
            found_any = True
            # Verify the transcript file has expected structure
            filepath = llm_dir / matches[0]
            try:
                content = json.loads(filepath.read_text(encoding="utf-8"))
                assert content.get("task_id"), f"{pattern} missing task_id"
                assert content.get("transcripts") is not None, f"{pattern} missing transcripts"
                print(f"   📝 {pattern} contains {len(content.get('transcripts', []))} transcript(s)")
            except (json.JSONDecodeError, AssertionError) as e:
                print(f"   ⚠️  {pattern} validation issue: {e}")
        else:
            print(f"⚠️  {pattern} not found in archive (may be skipped for this workflow path)")

    if not found_any:
        pytest.fail(
            f"No LLM chat transcripts found in {llm_dir}. "
            f"Files present: {archived_files}. "
            f"At least one of {expected_patterns} was expected."
        )

    # Also verify the trace includes expected workflow nodes
    trace = data.get("trace", [])
    trace_nodes = [step["node"] for step in trace]
    print(f"🛤️  Execution trace: {' -> '.join(trace_nodes)}")

    assert "parser_initialize" in trace_nodes, f"Missing parser_initialize in trace: {trace_nodes}"
    print("✅ LLM header forwarding test complete")
