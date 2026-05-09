from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
HOST_SHARED_ROOT = ROOT / "shared_workspace"
CONTAINER_SHARED_ROOT = Path("/app/shared_workspace")
TOP_MODULE = "verify_only_demo"


def _base_spec(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "iteration": 0,
        "refactor_label": "NONE",
        "intent": "VERIFY_ONLY",
        "top_module": TOP_MODULE,
        "source_stage": "architect",
        "module_description": "Verify-only smoke module with one sequential output.",
        "parameters": [],
        "ports": [
            {
                "name": "i_clk",
                "direction": "input",
                "net_type": "wire",
                "width": "1",
                "is_clock": True,
                "is_reset": False,
                "description": "clock",
            },
            {
                "name": "i_rst_n",
                "direction": "input",
                "net_type": "wire",
                "width": "1",
                "clock_domain": "i_clk",
                "is_clock": False,
                "is_reset": True,
                "description": "active-low reset",
            },
            {
                "name": "i_data",
                "direction": "input",
                "net_type": "wire",
                "width": "8",
                "clock_domain": "i_clk",
                "is_clock": False,
                "is_reset": False,
                "description": "data input",
            },
            {
                "name": "o_done",
                "direction": "output",
                "net_type": "reg",
                "width": "1",
                "clock_domain": "i_clk",
                "is_clock": False,
                "is_reset": False,
                "description": "done output",
            },
        ],
        "clock_and_reset": [
            {
                "clock_name": "i_clk",
                "reset_name": "i_rst_n",
                "reset_type": "async_low",
            }
        ],
        "protocols": [],
        "verification_directives": ["compile and check top-level port contract"],
        "functional_requirements": ["reset clears o_done", "o_done follows nonzero i_data"],
        "corner_cases": ["i_data is zero"],
        "illegal_conditions": [],
        "latency_notes": ["one cycle latency after reset"],
        "nodes": [],
        "edges": [],
    }


GOOD_RTL = """module verify_only_demo(
    input wire i_clk,
    input wire i_rst_n,
    input wire [7:0] i_data,
    output reg o_done
);

always @(posedge i_clk or negedge i_rst_n) begin
    if (!i_rst_n) begin
        o_done <= 1'b0;
    end else begin
        o_done <= |i_data;
    end
end

endmodule
"""


def _remove_output_port(rtl_text: str) -> str:
    return rtl_text.replace("    output reg o_done\n", "")


def _change_output_direction(rtl_text: str) -> str:
    return rtl_text.replace("output reg o_done", "input wire o_done")


def _change_data_width(rtl_text: str) -> str:
    return rtl_text.replace("input wire [7:0] i_data", "input wire [3:0] i_data")


def _add_extra_port(rtl_text: str) -> str:
    return rtl_text.replace("    output reg o_done\n", "    output reg o_done,\n    output wire debug_extra\n")


def _break_compile_only(rtl_text: str) -> str:
    return rtl_text.replace("o_done <= |i_data;", "o_done <= |i_data")


CASES: list[tuple[str, str, Callable[[str], str]]] = [
    ("pass", "PASS", lambda rtl_text: rtl_text),
    ("missing_port", "FAIL_SEMANTIC", _remove_output_port),
    ("direction_mismatch", "FAIL_SEMANTIC", _change_output_direction),
    ("width_mismatch", "FAIL_SEMANTIC", _change_data_width),
    ("extra_port", "FAIL_SEMANTIC", _add_extra_port),
    ("compile_error", "FAIL_COMPILE", _break_compile_only),
]


def _prepare_case(case_name: str, mutate: Callable[[str], str]) -> tuple[str, Path, Path, Path]:
    task_id = f"TASK_VERIFY_ONLY_{case_name.upper()}"
    task_dir = HOST_SHARED_ROOT / task_id
    specs_dir = task_dir / "specs"
    rtl_dir = task_dir / "rtl"
    sim_dir = task_dir / "sim"
    specs_dir.mkdir(parents=True, exist_ok=True)
    rtl_dir.mkdir(parents=True, exist_ok=True)
    sim_dir.mkdir(parents=True, exist_ok=True)

    spec_path = specs_dir / "SpecReg_iter0.json"
    rtl_path = rtl_dir / f"{TOP_MODULE}.v"
    spec_path.write_text(json.dumps(_base_spec(task_id), indent=2), encoding="utf-8")
    rtl_path.write_text(mutate(GOOD_RTL), encoding="utf-8")
    return task_id, task_dir, spec_path, rtl_path


def _container_path(host_path: Path) -> str:
    relative = host_path.relative_to(HOST_SHARED_ROOT)
    return str(CONTAINER_SHARED_ROOT / relative)


def _call_verify(task_id: str, task_dir: Path, spec_path: Path, rtl_path: Path) -> dict[str, Any]:
    payload = {
        "task": {
            "task_id": task_id,
            "iteration": 0,
            "intent": "VERIFY_ONLY",
            "top_module": TOP_MODULE,
            "spec_file_path": _container_path(spec_path),
            "shared_task_dir": _container_path(task_dir),
        },
        "spec_file_path": _container_path(spec_path),
        "rtl_path": _container_path(rtl_path),
    }

    verify_client = """
import json
import sys
import httpx
payload = json.load(sys.stdin)
response = httpx.post('http://verify:8000/v1/verify', json=payload, timeout=60.0)
print(response.text)
response.raise_for_status()
"""
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "parser", "python", "-c", verify_client],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Verify service call failed\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    api_response = json.loads(result.stdout)
    if api_response.get("status") != "success":
        raise AssertionError(f"Verify API returned non-success response: {api_response}")
    return api_response["data"]


def main() -> None:
    print("===== Verify-only fault injection =====")
    for case_name, expected_verdict, mutate in CASES:
        task_id, task_dir, spec_path, rtl_path = _prepare_case(case_name, mutate)
        data = _call_verify(task_id, task_dir, spec_path, rtl_path)
        report = data["report"]
        actual_verdict = report["verdict"]
        rpt_path = task_dir / "sim" / "VerifyRpt_iter0.json"
        print(f"{case_name}: {actual_verdict} -> {rpt_path}")
        if actual_verdict != expected_verdict:
            raise AssertionError(
                f"case {case_name} expected {expected_verdict}, got {actual_verdict}: {report}"
            )

    print("All verify-only cases passed.")


if __name__ == "__main__":
    main()
