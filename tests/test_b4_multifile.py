"""B4: Multi-file HDL E2E tests for hierarchical Verilog generation.

Verifies that the AGVS4RTL integration pipeline correctly handles
hierarchical designs producing multiple Verilog output files (top module
plus sub-modules), including rtl_paths propagation through the entire
Parser -> Gen -> Verify -> Archive workflow, and retry-after-failure.
"""

import json
import time
from pathlib import Path

# Injection marker constants (imported per plan guardrail)
from src.common.models import AGVS4RTL_INJECT_FAIL_SEMANTIC

# TODO: Add AGVS4RTL_INJECT_HIERARCHICAL constant to src/common/models.py
# Currently used as string literal — see assumption A2 in .sisyphus/assumption-validation.md
# TODO: Add AGVS4RTL_INJECT_PASS_ONCE constant to src/common/models.py

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Shared helpers (same pattern as test_workflow_retry.py)
# ---------------------------------------------------------------------------

def _disable_llm(payload):
    payload["llm"] = {"enabled": False}
    return payload


def _executed_nodes(result):
    return [step["node"] for step in result.get("data", {}).get("trace", [])]


def _post_workflow(api_client, url, payload):
    print(f"\U0001f680 Sending workflow request to Parser: {url}")
    print(f"\U0001f4e6 Payload:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")

    start_time = time.time()
    response = api_client.post(url, json=payload)
    response.raise_for_status()

    result = response.json()
    print(f"\u2705 Request completed! Elapsed: {time.time() - start_time:.2f}s")
    assert result["status"] == "success", f"API call failed: {result.get('message')}"
    return result


# ---------------------------------------------------------------------------
# Test 1: Hierarchical design produces at least 3 Verilog files
# ---------------------------------------------------------------------------

def test_hierarchical_generates_three_files(parser_url, api_client, unique_top_module):
    """Verify that a hierarchical design produces top + 2 sub-module .v files."""
    payload = _disable_llm({
        "top_module": unique_top_module,
        "raw_input_text": "Generate a hierarchical design with counter and comparator",
        "refined_requirements": [
            "reset to 0",
            "otherwise 1",
            "AGVS4RTL_INJECT_HIERARCHICAL",
        ],
        "max_iterations": 1,
    })

    print("\n===== Test 1: Hierarchical generates 3 files =====")
    result = _post_workflow(api_client, parser_url + "/v1/workflow/run", payload)

    data = result.get("data", {})
    executed_nodes = _executed_nodes(result)
    print(f"\U0001f6e4  Executed trace: {' -> '.join(executed_nodes)}")

    # --- overall success assertions ---
    assert data.get("success") is True, f"\u274c Workflow did not succeed: {data}"
    assert data.get("final_stage") == "archive_success", (
        f"\u274c Expected archive_success, got {data.get('final_stage')}"
    )

    # --- core nodes present ---
    for expected_node in ("parser_initialize", "gen_stateless", "verify_stateless", "archive_success"):
        assert expected_node in executed_nodes, f"\u274c Missing node: {expected_node}"

    # --- rtl_paths populated with 3+ files ---
    gen_output = data.get("gen_output", {})
    rtl_paths = gen_output.get("rtl_paths")
    assert rtl_paths is not None, "\u274c rtl_paths is None (expected list for hierarchical design)"
    assert isinstance(rtl_paths, list), f"\u274c rtl_paths is not a list: {type(rtl_paths)}"
    assert len(rtl_paths) >= 3, (
        f"\u274c Expected at least 3 files (top + 2 subs), got {len(rtl_paths)}: {rtl_paths}"
    )

    # First path should be the main RTL (top module)
    assert gen_output.get("rtl_path") is not None, "\u274c gen_output.rtl_path missing"
    print(f"\U0001f4c4 Main RTL:    {gen_output['rtl_path']}")
    print(f"\U0001f4e6 All rtl_paths: {rtl_paths}")


# ---------------------------------------------------------------------------
# Test 2: rtl_paths propagates through Parser->Gen->Verify->Archive
# ---------------------------------------------------------------------------

def test_rtl_paths_propagates_to_verify(parser_url, api_client, unique_top_module):
    """Verify rtl_paths reaches the Verify node and the full pipeline succeeds."""
    payload = _disable_llm({
        "top_module": unique_top_module,
        "raw_input_text": "Propagate rtl_paths through the full verification pipeline",
        "refined_requirements": [
            "reset to 0",
            "otherwise 1",
            "AGVS4RTL_INJECT_HIERARCHICAL",
        ],
        "max_iterations": 1,
    })

    print("\n===== Test 2: rtl_paths propagates to verify =====")
    result = _post_workflow(api_client, parser_url + "/v1/workflow/run", payload)

    data = result.get("data", {})
    executed_nodes = _executed_nodes(result)
    print(f"\U0001f6e4  Executed trace: {' -> '.join(executed_nodes)}")

    # --- overall success ---
    assert data.get("success") is True, f"\u274c Workflow did not succeed: {data}"
    assert data.get("final_stage") == "archive_success"

    # --- all expected pipeline nodes ---
    for expected_node in ("parser_initialize", "gen_stateless", "verify_stateless", "archive_success"):
        assert expected_node in executed_nodes, (
            f"\u274c Missing node: {expected_node}"
        )

    # --- gen_output has rtl_paths ---
    gen_output = data.get("gen_output", {})
    assert gen_output.get("rtl_paths") is not None, "\u274c gen_output.rtl_paths not set"
    assert len(gen_output["rtl_paths"]) >= 3, (
        f"\u274c Expected 3+ files, got {len(gen_output['rtl_paths'])}"
    )

    # --- verify_output exists and passed ---
    verify_output = data.get("verify_output", {})
    assert verify_output, "\u274c verify_output missing from result data"
    report = verify_output.get("report", {})
    verdict = report.get("verdict")
    assert verdict == "PASS", f"\u274c Verify verdict is {verdict}, expected PASS"

    print(f"\u2705 Verify verdict: {verdict}")
    print(f"\U0001f4e6 rtl_paths:   {gen_output['rtl_paths']}")


# ---------------------------------------------------------------------------
# Test 3: Each multi-file artifact exists on disk after workflow
# ---------------------------------------------------------------------------

def test_multi_file_artifacts_on_disk(parser_url, api_client, unique_top_module):
    """After archive_success, every file in rtl_paths exists on disk and is valid."""
    payload = _disable_llm({
        "top_module": unique_top_module,
        "raw_input_text": "Verify multi-file artifacts land on disk correctly",
        "refined_requirements": [
            "reset to 0",
            "otherwise 1",
            "AGVS4RTL_INJECT_HIERARCHICAL",
        ],
        "max_iterations": 1,
    })

    print("\n===== Test 3: Multi-file artifacts on disk =====")
    result = _post_workflow(api_client, parser_url + "/v1/workflow/run", payload)

    data = result.get("data", {})
    executed_nodes = _executed_nodes(result)
    print(f"\U0001f6e4  Executed trace: {' -> '.join(executed_nodes)}")

    assert data.get("final_stage") == "archive_success", (
        f"\u274c Expected archive_success, got {data.get('final_stage')}"
    )

    task_id = data.get("task_id")
    assert task_id, "\u274c task_id missing from result data"

    gen_output = data.get("gen_output", {})
    rtl_paths = gen_output.get("rtl_paths")
    assert rtl_paths is not None, "\u274c rtl_paths missing"
    assert len(rtl_paths) >= 3, f"\u274c Expected 3+ files, got {len(rtl_paths)}"

    # After archive_success, files are copied to Output/<task_id>/Result/shared_workspace/
    archive_rtl_dir = PROJECT_ROOT / "Output" / task_id / "Result" / "shared_workspace" / "rtl"

    for idx, container_path in enumerate(rtl_paths):
        filename = Path(container_path).name
        disk_path = archive_rtl_dir / filename

        print(f"  [{idx}] Checking: {disk_path}")

        # 1. File exists
        assert disk_path.exists(), (
            f"\u274c File not found on disk: {disk_path} (from {container_path})"
        )

        # 2. File is non-empty
        file_size = disk_path.stat().st_size
        assert file_size > 0, f"\u274c File is empty: {disk_path}"

        # 3. Verilog files contain module/endmodule keywords
        content = disk_path.read_text(encoding="utf-8")
        assert "module" in content.lower(), (
            f"\u274c 'module' keyword not found in {disk_path}"
        )
        assert "endmodule" in content.lower(), (
            f"\u274c 'endmodule' keyword not found in {disk_path}"
        )

        print(f"      \u2705 exists, size={file_size}B, has module/endmodule")

    print(f"\u2705 All {len(rtl_paths)} files verified on disk")


# ---------------------------------------------------------------------------
# Test 4: Hierarchical design survives retry after FAIL_SEMANTIC
# ---------------------------------------------------------------------------

def test_hierarchical_with_retry(parser_url, api_client, unique_top_module):
    """Hierarchical design: FAIL_SEMANTIC on iter 0 -> retry -> PASS on iter 1."""
    payload = _disable_llm({
        "top_module": unique_top_module,
        "raw_input_text": "Hierarchical design with retry after semantic failure",
        "refined_requirements": [
            "reset to 0",
            "otherwise 1",
            "AGVS4RTL_INJECT_HIERARCHICAL",
            AGVS4RTL_INJECT_FAIL_SEMANTIC,
        ],
        "max_iterations": 2,
    })

    print("\n===== Test 4: Hierarchical with retry =====")
    result = _post_workflow(api_client, parser_url + "/v1/workflow/run", payload)

    data = result.get("data", {})
    executed_nodes = _executed_nodes(result)
    print(f"\U0001f6e4  Executed trace: {' -> '.join(executed_nodes)}")

    # --- overall final success ---
    assert data.get("success") is True, (
        f"\u274c Workflow should succeed after retry: {data}"
    )
    assert data.get("final_stage") == "archive_success", (
        f"\u274c Expected archive_success, got {data.get('final_stage')}"
    )

    # --- retry path was exercised ---
    assert "prepare_retry" in executed_nodes, (
        "\u274c prepare_retry missing — retry path was not exercised"
    )

    # --- first iteration produced a FAIL_SEMANTIC verdict ---
    trace = data.get("trace", [])
    iter0_verify_steps = [
        step for step in trace
        if step["node"] == "verify_stateless" and step["iteration"] == 0
    ]
    assert iter0_verify_steps, "\u274c No verify_stateless at iteration 0 in trace"

    # --- prepare_retry advanced to iteration 1 ---
    retry_steps = [step for step in trace if step["node"] == "prepare_retry"]
    assert retry_steps, "\u274c No prepare_retry step in trace"
    assert retry_steps[0]["iteration"] == 1, (
        f"\u274c prepare_retry iteration is {retry_steps[0]['iteration']}, expected 1"
    )

    # --- final gen_output has correct rtl_paths ---
    gen_output = data.get("gen_output", {})
    rtl_paths = gen_output.get("rtl_paths")
    assert rtl_paths is not None, "\u274c rtl_paths missing in final gen_output"
    assert len(rtl_paths) >= 3, (
        f"\u274c Expected 3+ files in final output, got {len(rtl_paths)}"
    )

    # Verify the retry-aware summary mentions the previous failure
    summary = gen_output.get("summary", "")
    assert "FAIL_SEMANTIC" in summary, (
        f"\u274c gen_output.summary should mention FAIL_SEMANTIC: {summary}"
    )
    assert "iteration 1" in summary, (
        f"\u274c gen_output.summary should mention iteration 1: {summary}"
    )

    # --- final verify passed ---
    verify_output = data.get("verify_output", {})
    assert verify_output.get("report", {}).get("verdict") == "PASS", (
        "\u274c Final verify did not PASS"
    )

    print(f"\u2705 Retry path verified: FAIL_SEMANTIC -> prepare_retry -> PASS")
    print(f"\U0001f4c4 Gen summary:  {summary}")
    print(f"\U0001f4e6 rtl_paths:    {rtl_paths}")
