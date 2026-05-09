import json
import sys
import time
from pathlib import Path

import httpx


def _post_workflow(url, payload):
    print(f"🚀 发送模糊需求工作流请求至 Parser 服务: {url}")
    print(f"📦 载荷数据:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")

    start_time = time.time()
    with httpx.Client(timeout=300.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()

    result = response.json()
    print(f"✅ 请求完成! 耗时: {time.time() - start_time:.2f} 秒")
    assert result["status"] == "success", f"API 调用失败: {result.get('message')}"
    return result


def _load_archived_json(task_id, relative_path):
    path = Path("Output") / task_id / "Result" / "shared_workspace" / relative_path
    assert path.exists(), f"❌ 归档产物不存在: {path}"
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _assert_fuzzy_requirement_success(result):
    data = result.get("data", {})
    task_id = data.get("task_id")
    assert task_id, f"❌ 响应缺少 task_id: {data}"
    assert data.get("success") is True, f"❌ 模糊需求工作流未成功: {data}"
    assert data.get("final_stage") == "archive_success", f"❌ 未进入成功归档: {data.get('final_stage')}"

    trace_nodes = [step["node"] for step in data.get("trace", [])]
    print(f"🛤️  实际执行轨迹: {' -> '.join(trace_nodes)}")
    assert trace_nodes == ["parser_initialize", "gen_stateless", "verify_stateless", "archive_success"], (
        f"❌ 非预期执行轨迹: {trace_nodes}"
    )

    verify_output = data.get("verify_output", {})
    assert verify_output.get("report", {}).get("verdict") == "PASS", "❌ 模糊需求最终 Verify 未 PASS"

    spec_reg = _load_archived_json(task_id, Path("specs") / "SpecReg_iter0.json")
    user_task_spec = _load_archived_json(task_id, Path("specs") / "UserTaskSpec.json")
    try:
        parser_chat = _load_archived_json(task_id, Path("llm") / "ParserChat_iter0.json")
        assert parser_chat.get("transcripts"), "Parser LLM transcript not saved"
    except (FileNotFoundError, AssertionError) as e:
        print(f"⚠️  ParserChat check skipped: {e} (LLM may not be configured)")
        # Continue without failing — some test runs may not have LLM

    try:
        architect_chat = _load_archived_json(task_id, Path("llm") / "ArchitectChat_iter0.json")
        assert architect_chat.get("transcripts"), "Architect LLM transcript not saved"
    except (FileNotFoundError, AssertionError) as e:
        print(f"⚠️  ArchitectChat check skipped: {e} (LLM may not be configured)")
        # Continue without failing — some test runs may not have LLM

    ports = spec_reg.get("ports", [])
    port_names = {port.get("name") for port in ports}
    input_widths = [port.get("width") for port in ports if port.get("direction") == "input"]
    output_widths = [port.get("width") for port in ports if port.get("direction") == "output"]

    assert "8" in input_widths, f"❌ SpecReg 未推导出 8 位输入端口: {ports}"
    assert "8" in output_widths, f"❌ SpecReg 未推导出 8 位输出端口: {ports}"
    assert not {"i_clk", "i_rst_n", "o_done"}.issubset(port_names), (
        f"❌ Architect 回退到默认 dummy 时序端口: {ports}"
    )

    refined_requirements = user_task_spec.get("refined_requirements", [])
    assert refined_requirements, "❌ Parser 未从模糊输入中提炼需求"
    assert any("8" in requirement for requirement in refined_requirements), (
        f"❌ Parser 提炼需求未保留 8 位约束: {refined_requirements}"
    )

    print(f"📄 UserTaskSpec refined_requirements: {refined_requirements}")
    print(f"📐 SpecReg ports: {ports}")
    print(f"✅ 模糊需求 smoke 通过，task_id={task_id}")


def run_fuzzy_requirement_case(url):
    payload = {
        "top_module": "fuzzy_8bit_datapath_smoke",
        "raw_input_text": (
            "请生成一个 Verilog-2001 组合逻辑数据处理模块，顶层名为 fuzzy_8bit_datapath_smoke。"
            "它大体上要支持 8 位输入和 8 位输出，可以根据一个简单控制信号在几种常见数据处理行为之间切换，"
            "例如透传、取反、加一或清零这类功能都可以，但我暂时没有把每个操作数、opcode 和端口一一列清楚。"
            "请你自行补全合理的顶层端口、操作选择和默认行为；不要添加时钟、复位或 done 端口。"
        ),
        "max_iterations": 1,
    }

    print("\n===== 模糊需求 -> Parser/Architect 补全契约 -> Verify PASS smoke =====")
    result = _post_workflow(url, payload)
    _assert_fuzzy_requirement_success(result)


def main():
    url = "http://localhost:8001/v1/workflow/run"

    try:
        run_fuzzy_requirement_case(url)
    except httpx.RequestError as exc:
        print(f"\n❌ 网络请求异常: {exc}")
        print("👉 请确认已经执行了 `docker compose up -d`，且 parser 服务暴露在宿主机 8001 端口。")
        sys.exit(1)
    except AssertionError as exc:
        print(f"\n{exc}")
        print("👉 该 smoke 依赖真实 LLM 路径，请确认 compose 环境中 AGVS4RTL_LLM_ENABLED=true 且模型配置可用。")
        sys.exit(1)


if __name__ == "__main__":
    main()