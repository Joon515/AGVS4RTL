from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
WORKFLOW_URL = "http://localhost:8001/v1/workflow/run"
TOP_MODULE = "multi_file_demo"


def _post_workflow(payload: dict) -> dict:
    print(f"===== Multi-file RTL workflow: {TOP_MODULE} =====")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    start_time = time.time()
    with httpx.Client(timeout=120.0) as client:
        response = client.post(WORKFLOW_URL, json=payload)
        response.raise_for_status()

    result = response.json()
    print(f"Workflow completed in {time.time() - start_time:.2f}s")
    if result.get("status") != "success":
        raise AssertionError(f"workflow API returned non-success response: {result}")
    return result


def main() -> None:
    payload = {
        "top_module": TOP_MODULE,
        "raw_input_text": "Generate hierarchical multi-file RTL with top, control, and datapath modules.",
        "refined_requirements": [
            "generate top/control/datapath modules",
            "top module instantiates control and datapath children",
            "AGVS4RTL_INJECT_MULTI_FILE",
        ],
        "max_iterations": 1,
        "llm": {"enabled": False},
    }

    result = _post_workflow(payload)
    data = result.get("data", {})
    if data.get("success") is not True:
        raise AssertionError(f"workflow did not succeed: {data}")
    if data.get("final_stage") != "archive_success":
        raise AssertionError(f"unexpected final_stage: {data.get('final_stage')}")

    verify_report = data.get("verify_output", {}).get("report", {})
    if verify_report.get("verdict") != "PASS":
        raise AssertionError(f"Verify did not PASS: {verify_report}")

    gen_output = data.get("gen_output", {})
    rtl_paths = gen_output.get("rtl_paths", [])
    if len(rtl_paths) < 3:
        raise AssertionError(f"expected at least 3 RTL files, got: {rtl_paths}")
    if gen_output.get("top_rtl_path") != gen_output.get("rtl_path"):
        raise AssertionError(f"top_rtl_path should match rtl_path: {gen_output}")

    task_id = data["task_id"]
    result_root = ROOT / "Output" / task_id / "Result" / "shared_workspace"
    spec_path = result_root / "specs" / "SpecReg_iter0.json"
    rtl_dir = result_root / "rtl"

    with spec_path.open(encoding="utf-8") as spec_file:
        spec_reg = json.load(spec_file)

    nodes = spec_reg.get("nodes", [])
    module_names = {node.get("module_name") for node in nodes}
    expected_modules = {f"{TOP_MODULE}_control", f"{TOP_MODULE}_datapath"}
    if not expected_modules.issubset(module_names):
        raise AssertionError(f"missing child module nodes: {module_names}")

    rtl_file_nodes = [node for node in nodes if node.get("is_rtl_file") is True]
    rtl_file_module_names = {node.get("module_name") for node in rtl_file_nodes}
    if not expected_modules.issubset(rtl_file_module_names):
        raise AssertionError(f"expected child modules to be marked is_rtl_file: {rtl_file_nodes}")
    if any("is_leaf" in node for node in nodes):
        raise AssertionError(f"legacy is_leaf field should not be emitted: {nodes}")

    expected_files = {
        rtl_dir / f"{TOP_MODULE}.v",
        rtl_dir / f"{TOP_MODULE}_control.v",
        rtl_dir / f"{TOP_MODULE}_datapath.v",
    }
    missing_files = [str(path) for path in expected_files if not path.exists()]
    if missing_files:
        raise AssertionError(f"missing archived RTL files: {missing_files}")

    print(f"PASS: generated and verified multi-file RTL task {task_id}")


if __name__ == "__main__":
    main()
