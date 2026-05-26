import json
import sys
import time
from pathlib import Path

import httpx


EXPLICIT_MULTI_FILE_PROMPT = (
    "请生成一个 Verilog-2001 多文件 RTL 项目，顶层模块名为 llm_multi_file_datapath。"
    "请把设计拆成三个模块并分别落到独立 RTL 文件：llm_multi_file_datapath.v、"
    "llm_multi_file_datapath_control.v、llm_multi_file_datapath_datapath.v。"
    "顶层模块只负责端口声明、内部连线和例化子模块；control 子模块负责根据 i_opcode[1:0] "
    "产生控制语义和 o_valid；datapath 子模块负责在 i_clk 上升沿、i_rst_n 异步低有效复位下处理 8 位数据。"
    "顶层端口必须明确为 input wire i_clk、input wire i_rst_n、input wire [7:0] i_data、"
    "input wire [1:0] i_opcode、output wire [7:0] o_data、output wire o_valid。"
    "功能要求：00 透传 i_data，01 按位取反，10 加一，11 清零；复位时 o_data=0 且 o_valid=0；"
    "复位释放后 o_valid=1。SpecReg 请表达模块图结构，包含 TOP 到 control/datapath 的实例节点和信号边。"
    "不要添加 done 端口，不要添加未声明端口，不要使用 SystemVerilog-only 语法。"
)


EXPECTED_RTL_FILES = {
    "llm_multi_file_datapath.v",
    "llm_multi_file_datapath_control.v",
    "llm_multi_file_datapath_datapath.v",
}


def _post_workflow(url, payload):
    print(f"发送明确多文件 LLM 工作流请求至 Parser 服务: {url}")
    print(f"明确提示:\n{payload['raw_input_text']}")
    print(f"载荷数据:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")

    start_time = time.time()
    with httpx.Client(timeout=540.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()

    result = response.json()
    print(f"请求完成，耗时: {time.time() - start_time:.2f} 秒")
    assert result["status"] == "success", f"API 调用失败: {result.get('message')}"
    return result


def _archived_path(task_id, relative_path):
    return Path("Output") / task_id / "Result" / "shared_workspace" / relative_path


def _load_archived_json(task_id, relative_path):
    path = _archived_path(task_id, relative_path)
    assert path.exists(), f"归档产物不存在: {path}"
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _assert_explicit_multi_file_success(result):
    data = result.get("data", {})
    task_id = data.get("task_id")
    assert task_id, f"响应缺少 task_id: {data}"
    assert data.get("success") is True, f"明确多文件 LLM 工作流未成功: {data}"
    assert data.get("final_stage") == "archive_success", f"未进入成功归档: {data.get('final_stage')}"

    trace_nodes = [step["node"] for step in data.get("trace", [])]
    print(f"实际执行轨迹: {' -> '.join(trace_nodes)}")
    assert trace_nodes == ["parser_initialize", "gen_stateless", "verify_stateless", "archive_success"], (
        f"非预期执行轨迹: {trace_nodes}"
    )

    verify_output = data.get("verify_output", {})
    assert verify_output.get("report", {}).get("verdict") == "PASS", "明确多文件 LLM 最终 Verify 未 PASS"

    gen_output = data.get("gen_output", {})
    rtl_paths = gen_output.get("rtl_paths", [])
    assert len(rtl_paths) >= 3, f"LLM 多文件提示未生成至少 3 个 RTL 文件: {rtl_paths}"
    assert gen_output.get("top_rtl_path") == gen_output.get("rtl_path"), f"top_rtl_path/rtl_path 不一致: {gen_output}"

    spec_reg = _load_archived_json(task_id, Path("specs") / "SpecReg_iter0.json")
    architect_chat = _load_archived_json(task_id, Path("llm") / "ArchitectChat_iter0.json")
    coder_chat = _load_archived_json(task_id, Path("llm") / "CoderChat_iter0.json")

    assert architect_chat.get("transcripts"), "Architect LLM transcript 未落盘，SpecReg 未走 LLM 生成路径"
    assert coder_chat.get("transcripts"), "Coder LLM transcript 未落盘，RTL 代码未走 LLM 生成路径"

    nodes = spec_reg.get("nodes", [])
    instance_nodes = [node for node in nodes if node.get("node_type") == "instance"]
    module_names = {node.get("module_name") for node in instance_nodes}
    assert {"llm_multi_file_datapath_control", "llm_multi_file_datapath_datapath"}.issubset(module_names), (
        f"SpecReg 未表达 control/datapath 子模块图结构: {nodes}"
    )

    archived_rtl_dir = _archived_path(task_id, Path("rtl"))
    archived_rtl_files = {path.name for path in archived_rtl_dir.glob("*.v")}
    assert EXPECTED_RTL_FILES.issubset(archived_rtl_files), (
        f"归档 RTL 文件不完整，期望 {EXPECTED_RTL_FILES}，实际 {archived_rtl_files}"
    )

    for rtl_file in EXPECTED_RTL_FILES:
        rtl_text = (archived_rtl_dir / rtl_file).read_text(encoding="utf-8")
        module_name = rtl_file.removesuffix(".v")
        assert f"module {module_name}" in rtl_text, f"{rtl_file} 缺少对应 module 声明"

    print(f"SpecReg instance module_names: {sorted(module_names)}")
    print(f"RTL paths: {rtl_paths}")
    print(f"明确多文件 LLM smoke 通过，task_id={task_id}")


def run_explicit_multi_file_case(url):
    payload = {
        "top_module": "llm_multi_file_datapath",
        "raw_input_text": EXPLICIT_MULTI_FILE_PROMPT,
        "max_iterations": 1,
    }

    print("\n===== 明确提示 -> LLM SpecReg 图结构 -> 多文件 RTL -> Verify PASS smoke =====")
    result = _post_workflow(url, payload)
    _assert_explicit_multi_file_success(result)


def main():
    url = "http://localhost:8001/v1/workflow/run"

    try:
        run_explicit_multi_file_case(url)
    except httpx.RequestError as exc:
        print(f"\n网络请求异常: {exc}")
        print("请确认已经执行了 `docker compose up -d`，且 parser 服务暴露在宿主机 8001 端口。")
        sys.exit(1)
    except AssertionError as exc:
        print(f"\n{exc}")
        print("该 smoke 依赖真实 LLM 路径，请确认 compose 环境中 AGVS4RTL_LLM_ENABLED=true 且模型配置可用。")
        sys.exit(1)


if __name__ == "__main__":
    main()
