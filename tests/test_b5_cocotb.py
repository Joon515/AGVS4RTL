"""B5 Cocotb simulation tests for AGVS4RTL integration testing.

Tests cocotb testbench generation and Makefile generation via the Verify
module's simulate_node, exercising both LLM-disabled (skip) and LLM-enabled
paths through the full Parser workflow API.
"""

import ast
import json
import time
from pathlib import Path

import pytest

# TODO: Add AGVS4RTL_INJECT_PASS_ONCE and AGVS4RTL_INJECT_HIERARCHICAL constants
# to src/common/models.py. Currently used as string literals.
# See .sisyphus/assumption-validation.md assumption A2.


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _disable_llm(payload):
    payload["llm"] = {"enabled": False}
    return payload


def _enable_llm(payload):
    """Enable LLM for real LLM path tests."""
    import os

    payload["llm"] = {
        "enabled": True,
        "base_url": os.environ.get("AGVS4RTL_LLM_BASE_URL", ""),
        "api_key": os.environ.get("AGVS4RTL_LLM_API_KEY", ""),
        "model": os.environ.get("AGVS4RTL_LLM_MODEL", ""),
        "profile": os.environ.get("AGVS4RTL_LLM_PROFILE", "default"),
    }
    return payload


def _post_workflow(api_client, url, payload):
    """Send a workflow request to the Parser service and return the result."""
    print(f"🚀 发送工作流请求至 Parser 服务: {url}")
    print(f"📦 载荷数据:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")

    start_time = time.time()
    response = api_client.post(url, json=payload)
    response.raise_for_status()

    result = response.json()
    print(f"✅ 请求完成! 耗时: {time.time() - start_time:.2f} 秒")
    assert result["status"] == "success", f"API 调用失败: {result.get('message')}"
    return result


# ---------------------------------------------------------------------------
# Test 1: simulate_node skips when LLM disabled
# ---------------------------------------------------------------------------

def test_simulate_node_skips_without_llm(parser_url, api_client, unique_top_module):
    """simulate_node skips testbench generation when LLM disabled."""
    payload = _disable_llm(
        {
            "top_module": unique_top_module,
            "raw_input_text": "Generate a simple sequential done logic module",
            "refined_requirements": [
                "reset to 0",
                "otherwise 1",
                "AGVS4RTL_INJECT_PASS_ONCE",
            ],
            "max_iterations": 1,
        }
    )

    print("\n===== Test 1: simulate_node skips without LLM =====")
    result = _post_workflow(api_client, parser_url + "/v1/workflow/run", payload)

    data = result.get("data", {})
    trace = [step["node"] for step in data.get("trace", [])]
    print(f"🛤️  实际执行轨迹: {' -> '.join(trace)}")

    assert data.get("success") is True, f"❌ 工作流未成功: {data}"
    assert data.get("final_stage") == "archive_success", (
        f"❌ 未进入成功归档: {data.get('final_stage')}"
    )

    verify_output = data.get("verify_output", {})
    report = verify_output.get("report", {})

    assert report.get("verdict") == "PASS", (
        f"❌ 最终 Verify 未 PASS: {report.get('verdict')}"
    )
    assert report.get("testbench_path") is None, (
        f"❌ simulate_node 应在 LLM 不可用时跳过，"
        f"但 testbench_path 非空: {report.get('testbench_path')}"
    )
    assert report.get("makefile_path") is None, (
        f"❌ simulate_node 应在 LLM 不可用时跳过，"
        f"但 makefile_path 非空: {report.get('makefile_path')}"
    )

    print("✅ Test 1 passed: simulate_node correctly skipped when LLM disabled")


# ---------------------------------------------------------------------------
# Test 2: simulate_node generates testbench with LLM
# ---------------------------------------------------------------------------

@pytest.mark.llm
@pytest.mark.slow
def test_simulate_node_generates_testbench_with_llm(
    parser_url, api_client, unique_top_module
):
    """simulate_node generates cocotb testbench and Makefile when LLM enabled."""
    payload = _enable_llm(
        {
            "top_module": unique_top_module,
            "raw_input_text": (
                "Generate a simple sequential done logic module "
                "with clock, reset, and done signal"
            ),
            "refined_requirements": [
                "output done asserts when counting completes",
            ],
            "max_iterations": 1,
        }
    )

    print("\n===== Test 2: simulate_node generates testbench with LLM =====")
    result = _post_workflow(api_client, parser_url + "/v1/workflow/run", payload)

    data = result.get("data", {})
    trace = [step["node"] for step in data.get("trace", [])]
    print(f"🛤️  实际执行轨迹: {' -> '.join(trace)}")

    assert data.get("success") is True, f"❌ 工作流未成功: {data}"

    task_id = data.get("task_id")
    assert task_id, f"❌ 响应缺少 task_id"

    verify_output = data.get("verify_output", {})
    report = verify_output.get("report", {})

    tb_path = report.get("testbench_path")
    mf_path = report.get("makefile_path")
    assert tb_path, f"❌ testbench_path 应为非空字符串: {tb_path!r}"
    assert mf_path, f"❌ makefile_path 应为非空字符串: {mf_path!r}"

    print(f"📄 testbench_path: {tb_path}")
    print(f"🔧 makefile_path: {mf_path}")

    archived_tb = (
        Path("Output")
        / task_id
        / "Result"
        / "shared_workspace"
        / "sim"
        / f"test_{unique_top_module}.py"
    )
    assert archived_tb.exists(), f"❌ Testbench 文件未落盘: {archived_tb}"
    print(f"✅ Testbench 文件已落盘: {archived_tb}")

    archived_mf = (
        Path("Output")
        / task_id
        / "Result"
        / "shared_workspace"
        / "sim"
        / "Makefile"
    )
    assert archived_mf.exists(), f"❌ Makefile 未落盘: {archived_mf}"

    print("✅ Test 2 passed: simulate_node generated testbench and makefile")


# ---------------------------------------------------------------------------
# Test 3: Makefile references all rtl_paths for hierarchical designs
# ---------------------------------------------------------------------------

@pytest.mark.llm
def test_makefile_references_all_rtl_paths(parser_url, api_client, unique_top_module):
    """Makefile VERILOG_SOURCES references all .v files from hierarchical design."""
    payload = _enable_llm(
        {
            "top_module": unique_top_module,
            "raw_input_text": "Generate a hierarchical design with sub-modules",
            "refined_requirements": [
                "reset to 0",
                "otherwise 1",
                "AGVS4RTL_INJECT_HIERARCHICAL",
            ],
            "max_iterations": 1,
        }
    )

    print("\n===== Test 3: Makefile references all rtl paths =====")
    result = _post_workflow(api_client, parser_url + "/v1/workflow/run", payload)

    data = result.get("data", {})
    trace = [step["node"] for step in data.get("trace", [])]
    print(f"🛤️  实际执行轨迹: {' -> '.join(trace)}")

    task_id = data.get("task_id")
    assert task_id, f"❌ 响应缺少 task_id"

    verify_output = data.get("verify_output", {})
    report = verify_output.get("report", {})

    mf_path_report = report.get("makefile_path")
    assert mf_path_report, f"❌ makefile_path 应为非空字符串: {mf_path_report!r}"
    print(f"🔧 makefile_path (report): {mf_path_report}")

    mf_path = (
        Path("Output")
        / task_id
        / "Result"
        / "shared_workspace"
        / "sim"
        / "Makefile"
    )
    assert mf_path.exists(), f"❌ Makefile 未落盘: {mf_path}"

    makefile_content = mf_path.read_text(encoding="utf-8")
    print(f"📄 Makefile content:\n{makefile_content}")

    assert "VERILOG_SOURCES=" in makefile_content, (
        "❌ Makefile 缺少 VERILOG_SOURCES 行"
    )

    sources_line = None
    for line in makefile_content.splitlines():
        if line.startswith("VERILOG_SOURCES="):
            sources_line = line
            break

    assert sources_line is not None, "❌ 未找到 VERILOG_SOURCES 行"

    sources = sources_line.split("=", 1)[1].strip()
    v_files = [source for source in sources.split() if source.endswith(".v")]
    assert len(v_files) >= 1, (
        f"❌ VERILOG_SOURCES 应至少包含一个 .v 文件: {sources}"
    )

    assert len(v_files) >= 2, (
        f"❌ 层级设计应生成多个 .v 文件，但只有 {len(v_files)} 个: {v_files}"
    )

    print(f"✅ VERILOG_SOURCES 包含 {len(v_files)} 个 .v 文件: {v_files}")
    print("✅ Test 3 passed: Makefile references all rtl paths")


# ---------------------------------------------------------------------------
# Test 4: Generated cocotb testbench is valid Python syntax
# ---------------------------------------------------------------------------

@pytest.mark.llm
def test_cocotb_testbench_is_valid_python(parser_url, api_client, unique_top_module):
    """Generated cocotb testbench is valid Python syntax."""
    payload = _enable_llm(
        {
            "top_module": unique_top_module,
            "raw_input_text": (
                "Generate a simple sequential done logic module "
                "with clock, reset, and done signal"
            ),
            "refined_requirements": [
                "output done asserts when counting completes",
            ],
            "max_iterations": 1,
        }
    )

    print("\n===== Test 4: cocotb testbench is valid Python =====")
    result = _post_workflow(api_client, parser_url + "/v1/workflow/run", payload)

    data = result.get("data", {})
    trace = [step["node"] for step in data.get("trace", [])]
    print(f"🛤️  实际执行轨迹: {' -> '.join(trace)}")

    task_id = data.get("task_id")
    assert task_id, f"❌ 响应缺少 task_id"

    verify_output = data.get("verify_output", {})
    report = verify_output.get("report", {})

    tb_path_report = report.get("testbench_path")
    assert tb_path_report, f"❌ testbench_path 应为非空字符串: {tb_path_report!r}"
    print(f"📄 testbench_path (report): {tb_path_report}")

    tb_path = (
        Path("Output")
        / task_id
        / "Result"
        / "shared_workspace"
        / "sim"
        / f"test_{unique_top_module}.py"
    )
    assert tb_path.exists(), f"❌ Testbench 文件未落盘: {tb_path}"

    content = tb_path.read_text(encoding="utf-8")
    content_len = len(content)
    print(f"📄 Testbench size: {content_len} chars")
    print(f"📄 Testbench content (first 600 chars):\n{content[:600]}")

    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        pytest.fail(
            f"❌ Testbench 包含无效 Python 语法: {exc}\n"
            f"Content excerpt: {content[:2000]}"
        )

    assert len(tree.body) > 0, (
        "❌ Testbench 是空模块（无顶层语句）"
    )

    print(f"✅ Testbench AST has {len(tree.body)} top-level statements")
    print("✅ Test 4 passed: cocotb testbench is valid Python syntax")
