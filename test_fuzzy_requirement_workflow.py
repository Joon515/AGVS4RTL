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
    parser_chat = _load_archived_json(task_id, Path("llm") / "ParserChat_iter0.json")
    architect_chat = _load_archived_json(task_id, Path("llm") / "ArchitectChat_iter0.json")

    assert parser_chat.get("transcripts"), "❌ Parser LLM transcript 未落盘，模糊需求未走 LLM 分析路径"
    assert architect_chat.get("transcripts"), "❌ Architect LLM transcript 未落盘，SpecReg 未走 LLM 生成路径"

    ports = spec_reg.get("ports", [])
    port_names = {port.get("name") for port in ports}
    input_widths = [port.get("width") for port in ports if port.get("direction") == "input"]
    output_widths = [port.get("width") for port in ports if port.get("direction") == "output"]

    # assert "8" in input_widths, f"❌ SpecReg 未推导出 8 位输入端口: {ports}"
    # assert "8" in output_widths, f"❌ SpecReg 未推导出 8 位输出端口: {ports}"
    # assert not {"i_clk", "i_rst_n", "o_done"}.issubset(port_names), (
    #     f"❌ Architect 回退到默认 dummy 时序端口: {ports}"
    # )

    refined_requirements = user_task_spec.get("refined_requirements", [])
    assert refined_requirements, "❌ Parser 未从模糊输入中提炼需求"
    # assert any("8" in requirement for requirement in refined_requirements), (
    #     f"❌ Parser 提炼需求未保留 8 位约束: {refined_requirements}"
    # )

    print(f"📄 UserTaskSpec refined_requirements: {refined_requirements}")
    print(f"📐 SpecReg ports: {ports}")
    print(f"✅ 模糊需求 smoke 通过，task_id={task_id}")


def run_fuzzy_requirement_case(url):
    payload = {
        "top_module": "fuzzy_pipeline_accel_smoke",
        "raw_input_text": (
            "我想设计一个轻量级流水线加速器，顶层名为 fuzzy_pipeline_accel_smoke。"
            "输入数据是一条一条进来的，每条数据大概包含操作码和操作数，"
            "但我没定好操作码几位、操作数几位，你帮我拆一个合理的字段格式。"
            "模块内部应该分好几个阶段处理，比如先解码、再运算、最后写回结果，"
            "具体分几段、每段做什么我没想清楚，你根据支持的功能自己排。"
            "要支持的基本运算有加减乘除和位运算，但除法可以简化成移位近似，"
            "具体哪些运算优先级高、资源怎么分配你看着办。"
            "每个流水线段之间要用 ready/valid 握手，我不能接受气泡太多，"
            "但如果某些运算需要多拍完成，允许局部阻塞或者旁路。"
            "输出要带上结果有效标记和溢出标记，如果运算出错也要能报出来。"
            "另外我希望流水线深度是可参数化的，默认 3 到 5 级都可以，"
            "但参数位宽和默认值你来定。"
            "整个设计是时序逻辑，需要时钟和异步低复位，不要 done 端口。"
            "Verilog-2001 语法，综合友好，但不要求最高性能，先能跑通。"
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