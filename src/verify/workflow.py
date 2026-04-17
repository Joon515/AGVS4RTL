from __future__ import annotations

import operator
import os
import re
import subprocess
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from src.common.models import (
    ArtifactSourceStage,
    CompileError,
    ErrorSnapshot,
    PortMismatch,
    SpecReg,
    VerifyNodeOutput,
    VerifyRpt,
    VerifyTaskPayload,
    VerifyVerdict,
)


class VerifyWorkflowState(TypedDict):
    """
    Verify 内部 LangGraph 状态。

    说明：
    - task_payload: Parser 下发的验证任务载荷
    - iteration: 当前验证轮次
    - messages: 预留给后续 LLM/诊断增强的上下文
    - spec_reg: 从 spec_file_path 读取的 SpecReg 契约
    - rtl_text: 从 rtl_path 读取的 RTL 文本
    - sim_dir: 当前任务共享工作区下的仿真/验证输出目录
    - verify_rpt_path: 本轮验证报告落盘路径
    - compile_log_path: 本轮编译日志落盘路径
    - compile_errors: 编译阶段抽取出的结构化错误
    - verify_rpt: 本轮验证报告
    - verify_output: 对外返回的最终输出
    """
    task_payload: VerifyTaskPayload
    iteration: int
    messages: Annotated[List[Any], operator.add]

    spec_reg: Optional[SpecReg]
    rtl_text: Optional[str]

    sim_dir: Optional[str]
    verify_rpt_path: Optional[str]
    compile_log_path: Optional[str]

    compile_errors: Optional[List[CompileError]]
    verify_rpt: Optional[VerifyRpt]
    verify_output: Optional[VerifyNodeOutput]


def _build_system_messages(task_payload: VerifyTaskPayload) -> List[Dict[str, str]]:
    """
    构造供后续诊断增强使用的上下文消息。

    当前 V1 阶段不实际消费这些 messages，
    但与 Generator 保持统一骨架，便于后续扩展。
    """
    task = task_payload.task

    system_prompt = f"""You are an expert RTL verification assistant.
Your task is to validate generated RTL against SpecReg contract and produce a structured VerifyRpt.

Task ID: {task.task_id}
Top module: {task.top_module}
Intent: {task.intent}
Iteration: {task.iteration}

Spec file path: {task_payload.spec_file_path}
RTL path: {task_payload.rtl_path}
"""
    return [{"role": "system", "content": system_prompt}]


def _load_spec_reg(spec_file_path: str) -> SpecReg:
    """
    从 spec_file_path 读取并解析 SpecReg。
    """
    spec_path = Path(spec_file_path)
    if not spec_path.exists():
        raise FileNotFoundError(f"SpecReg not found at {spec_path}")

    return SpecReg.model_validate_json(spec_path.read_text(encoding="utf-8"))


def _load_rtl_text(rtl_path: str) -> str:
    """
    从 rtl_path 读取 RTL 文本。
    """
    rtl_file = Path(rtl_path)
    if not rtl_file.exists():
        raise FileNotFoundError(f"RTL file not found at {rtl_file}")

    return rtl_file.read_text(encoding="utf-8")


def _build_paths(task_payload: VerifyTaskPayload) -> Dict[str, str]:
    """
    构建 Verify 阶段所需的统一输出路径。

    当前约定：
    - VerifyRpt: shared_workspace/TASK_ID/sim/VerifyRpt_iter{n}.json
    - compile log: shared_workspace/TASK_ID/sim/compile_iter{n}.log
    """
    task = task_payload.task
    sim_dir = Path(task.shared_task_dir) / "sim"
    sim_dir.mkdir(parents=True, exist_ok=True)

    verify_rpt_path = sim_dir / f"VerifyRpt_iter{task.iteration}.json"
    compile_log_path = sim_dir / f"compile_iter{task.iteration}.log"

    return {
        "sim_dir": str(sim_dir),
        "verify_rpt_path": str(verify_rpt_path),
        "compile_log_path": str(compile_log_path),
    }


def _extract_module_port_block(rtl_text: str, top_module: str) -> Optional[str]:
    """
    从 RTL 文本中提取顶层 module 声明中的端口块。

    这是一个面向 V1 Stub 的轻量文本实现，不追求完整 Verilog 语法覆盖。
    若无法匹配，则返回 None。
    """
    pattern = rf"\bmodule\s+{re.escape(top_module)}\s*\((.*?)\)\s*;"
    match = re.search(pattern, rtl_text, flags=re.DOTALL)
    if not match:
        return None
    return match.group(1)


def _extract_declared_port_names(rtl_text: str, top_module: str) -> List[str]:
    """
    提取 RTL 顶层声明中的端口名。

    支持当前 MVP 生成器输出风格，例如：
        module top(
            input wire i_clk,
            input wire i_rst_n,
            output reg o_done
        );

    当前策略：
    - 优先从 module (...) 端口块中按逗号拆分
    - 每个条目取最后一个标识符作为端口名
    - 无法匹配时返回空列表
    """
    block = _extract_module_port_block(rtl_text, top_module)
    if block is None:
        return []

    port_names: List[str] = []
    for raw_item in block.split(","):
        item = raw_item.strip()
        if not item:
            continue

        match = re.search(r"([A-Za-z_][A-Za-z0-9_$]*)\s*$", item)
        if match:
            port_names.append(match.group(1))

    return port_names


def _check_semantic_contract(spec_reg: SpecReg, rtl_text: str) -> List[PortMismatch]:
    """
    执行最小静态契约检查。

    V1 当前检查项：
    1. RTL 非空
    2. 存在顶层 module <top_module>(...)
    3. SpecReg 中声明的端口在 RTL 顶层端口列表中都可找到

    注意：
    - 当前 models.py 中 FAIL_SEMANTIC 需要 mismatched_ports 非空。
    - 因此即使是 module 声明缺失，也统一编码为 PortMismatch 形式回传。
    """
    mismatches: List[PortMismatch] = []

    if not rtl_text.strip():
        mismatches.append(
            PortMismatch(
                expected_port=spec_reg.top_module,
                actual_port=None,
                detail="RTL file is empty",
            )
        )
        return mismatches

    if f"module {spec_reg.top_module}" not in rtl_text:
        mismatches.append(
            PortMismatch(
                expected_port=spec_reg.top_module,
                actual_port=None,
                detail=f"top module declaration 'module {spec_reg.top_module}' not found in RTL",
            )
        )
        return mismatches

    actual_ports = set(_extract_declared_port_names(rtl_text, spec_reg.top_module))
    expected_ports = [port.name for port in spec_reg.ports]

    for expected_port in expected_ports:
        if expected_port not in actual_ports:
            mismatches.append(
                PortMismatch(
                    expected_port=expected_port,
                    actual_port=None,
                    detail="expected top-level port missing in RTL module declaration",
                )
            )

    return mismatches


def _parse_compile_errors(log_text: str) -> List[CompileError]:
    """
    从 iverilog 输出日志中提取结构化编译错误。

    支持常见格式示例：
    /path/to/file.v:17: syntax error
    /path/to/file.v:20: error: Invalid module instantiation

    若无法精确提取，也至少保留首行摘要。
    """
    errors: List[CompileError] = []

    for line in log_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        match = re.match(r"^(.*?):(\d+):\s*(.*)$", stripped)
        if match:
            file_path, line_no, message = match.groups()
            errors.append(
                CompileError(
                    file=file_path.strip() or None,
                    line=int(line_no),
                    message=message.strip() or "compile error",
                )
            )

    if errors:
        return errors

    first_non_empty = next((line.strip() for line in log_text.splitlines() if line.strip()), None)
    if first_non_empty:
        errors.append(CompileError(message=first_non_empty))
    else:
        errors.append(CompileError(message="iverilog compile failed with empty log"))

    return errors


def _run_iverilog_compile(
    rtl_path: str,
    top_module: str,
    output_dir: str,
    compile_log_path: str,
) -> List[CompileError]:
    """
    调用 iverilog 执行最小编译检查。

    返回：
    - 成功：空列表
    - 失败：CompileError 列表

    说明：
    - 当前仅编译单个 RTL 文件，适配 MVP 生成器输出
    - 后续若引入多文件/子模块，可在此扩展文件收集逻辑
    """
    output_path = Path(output_dir) / f"{top_module}.out"

    command = [
        "iverilog",
        "-g2012",
        "-s",
        top_module,
        "-o",
        str(output_path),
        rtl_path,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    combined_log = ""
    if result.stdout:
        combined_log += result.stdout
    if result.stderr:
        if combined_log:
            combined_log += "\n"
        combined_log += result.stderr

    Path(compile_log_path).write_text(combined_log or "", encoding="utf-8")

    if result.returncode == 0:
        return []

    return _parse_compile_errors(combined_log)


def _build_infra_error_report(
    task_payload: VerifyTaskPayload,
    infra_error: str,
) -> VerifyRpt:
    """
    构造基础设施错误报告。
    """
    task = task_payload.task

    return VerifyRpt(
        task_id=task.task_id,
        iteration=task.iteration,
        intent=task.intent,
        top_module=task.top_module,
        source_stage=ArtifactSourceStage.VERIFY,
        verdict=VerifyVerdict.INFRA_ERROR,
        error_details=ErrorSnapshot(
            infra_errors=[infra_error],
            suggested_fix="check verify environment, input file paths, and upstream artifacts",
        ),
    )


def _build_semantic_fail_report(
    task_payload: VerifyTaskPayload,
    mismatches: List[PortMismatch],
) -> VerifyRpt:
    """
    构造静态契约失败报告。
    """
    task = task_payload.task
    missing_ports = [m.expected_port for m in mismatches if m.actual_port is None]

    return VerifyRpt(
        task_id=task.task_id,
        iteration=task.iteration,
        intent=task.intent,
        top_module=task.top_module,
        source_stage=ArtifactSourceStage.VERIFY,
        verdict=VerifyVerdict.FAIL_SEMANTIC,
        error_details=ErrorSnapshot(
            mismatched_ports=mismatches,
            suggested_fix=(
                "align RTL top-level declaration with SpecReg contract"
                + (f"; missing items: {', '.join(missing_ports)}" if missing_ports else "")
            ),
        ),
    )


def _build_compile_fail_report(
    task_payload: VerifyTaskPayload,
    compile_errors: List[CompileError],
    compile_log_path: str,
) -> VerifyRpt:
    """
    构造编译失败报告。
    """
    task = task_payload.task

    return VerifyRpt(
        task_id=task.task_id,
        iteration=task.iteration,
        intent=task.intent,
        top_module=task.top_module,
        source_stage=ArtifactSourceStage.VERIFY,
        verdict=VerifyVerdict.FAIL_COMPILE,
        error_details=ErrorSnapshot(
            compile_errors=compile_errors,
            suggested_fix="fix Verilog syntax or compile errors before next iteration",
        ),
        sim_log_path=compile_log_path,
    )


def _build_pass_report(
    task_payload: VerifyTaskPayload,
    compile_log_path: Optional[str],
) -> VerifyRpt:
    """
    构造通过报告。
    """
    task = task_payload.task

    return VerifyRpt(
        task_id=task.task_id,
        iteration=task.iteration,
        intent=task.intent,
        top_module=task.top_module,
        source_stage=ArtifactSourceStage.VERIFY,
        verdict=VerifyVerdict.PASS,
        error_details=ErrorSnapshot(),
        sim_log_path=compile_log_path,
    )


def init_context_node(state: VerifyWorkflowState) -> Dict[str, Any]:
    """
    节点 1：上下文初始化。

    职责：
    1. 创建 sim 输出目录与本轮固定文件路径。
    2. 读取 SpecReg。
    3. 读取 RTL 文本。
    4. 构造统一 messages，供后续增强节点复用。

    设计原则：
    - V1 阶段仍保持与 Generator 相同的“init_context -> ... -> finalize”风格
    - 文件缺失、SpecReg 解析失败等异常先转化为 VerifyRpt，
      保持工作流最终仍能稳定返回 VerifyNodeOutput
    """
    task_payload = state["task_payload"]
    paths = _build_paths(task_payload)
    messages = _build_system_messages(task_payload)

    try:
        spec_reg = _load_spec_reg(task_payload.spec_file_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "iteration": task_payload.task.iteration,
            "messages": messages,
            "sim_dir": paths["sim_dir"],
            "verify_rpt_path": paths["verify_rpt_path"],
            "compile_log_path": paths["compile_log_path"],
            "verify_rpt": _build_infra_error_report(
                task_payload,
                f"failed to load SpecReg from {task_payload.spec_file_path}: {exc}",
            ),
        }

    try:
        rtl_text = _load_rtl_text(task_payload.rtl_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "iteration": task_payload.task.iteration,
            "messages": messages,
            "spec_reg": spec_reg,
            "sim_dir": paths["sim_dir"],
            "verify_rpt_path": paths["verify_rpt_path"],
            "compile_log_path": paths["compile_log_path"],
            "verify_rpt": _build_infra_error_report(
                task_payload,
                f"failed to load RTL from {task_payload.rtl_path}: {exc}",
            ),
        }

    return {
        "iteration": task_payload.task.iteration,
        "messages": messages,
        "spec_reg": spec_reg,
        "rtl_text": rtl_text,
        "sim_dir": paths["sim_dir"],
        "verify_rpt_path": paths["verify_rpt_path"],
        "compile_log_path": paths["compile_log_path"],
    }


def semantic_check_node(state: VerifyWorkflowState) -> Dict[str, Any]:
    """
    节点 2：静态契约核查。

    当前职责：
    1. 若 init_context 已经生成失败报告，则直接透传。
    2. 基于 SpecReg 检查 RTL 顶层声明与端口契约。
    3. 若存在不匹配，生成 FAIL_SEMANTIC 报告。

    后续扩展方向：
    - 增加方向/位宽核查
    - 增加 clock/reset 端口约束核查
    - 增加 protocol 映射检查
    """
    if state.get("verify_rpt") is not None:
        return {}

    spec_reg = state.get("spec_reg")
    rtl_text = state.get("rtl_text")

    if spec_reg is None:
        raise ValueError("spec_reg is missing")
    if rtl_text is None:
        raise ValueError("rtl_text is missing")

    mismatches = _check_semantic_contract(spec_reg, rtl_text)
    if mismatches:
        return {
            "verify_rpt": _build_semantic_fail_report(state["task_payload"], mismatches),
        }

    return {}


def compile_check_node(state: VerifyWorkflowState) -> Dict[str, Any]:
    """
    节点 3：编译检查。

    当前职责：
    1. 若前序阶段已生成失败报告，则跳过。
    2. 根据环境变量决定是否启用 iverilog 编译检查。
    3. 若编译失败，生成 FAIL_COMPILE 报告。

    环境变量：
    - VERIFY_ENABLE_IVERILOG=true/false
    """
    if state.get("verify_rpt") is not None:
        return {}

    enabled = os.getenv("VERIFY_ENABLE_IVERILOG", "true").lower() == "true"
    if not enabled:
        return {}

    task_payload = state["task_payload"]
    compile_log_path = state.get("compile_log_path")
    sim_dir = state.get("sim_dir")

    if compile_log_path is None:
        raise ValueError("compile_log_path is missing")
    if sim_dir is None:
        raise ValueError("sim_dir is missing")

    try:
        compile_errors = _run_iverilog_compile(
            rtl_path=task_payload.rtl_path,
            top_module=task_payload.task.top_module,
            output_dir=sim_dir,
            compile_log_path=compile_log_path,
        )
    except FileNotFoundError as exc:
        return {
            "verify_rpt": _build_infra_error_report(
                task_payload,
                f"iverilog not available in verify container: {exc}",
            )
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "verify_rpt": _build_infra_error_report(
                task_payload,
                f"unexpected compile-stage failure: {exc}",
            )
        }

    if compile_errors:
        return {
            "compile_errors": compile_errors,
            "verify_rpt": _build_compile_fail_report(
                task_payload=task_payload,
                compile_errors=compile_errors,
                compile_log_path=compile_log_path,
            ),
        }

    return {"compile_errors": []}


def finalize_node(state: VerifyWorkflowState) -> Dict[str, Any]:
    """
    节点 4：落盘与输出节点。

    职责：
    1. 若前序节点未生成 VerifyRpt，则构造 PASS 报告。
    2. 将 VerifyRpt 落盘到 shared_workspace/TASK_ID/sim。
    3. 组装并返回 VerifyNodeOutput。

    文件命名规则：
    - VerifyRpt: sim/VerifyRpt_iter{iteration}.json
    - compile log: sim/compile_iter{iteration}.log
    """
    verify_rpt = state.get("verify_rpt")
    verify_rpt_path = state.get("verify_rpt_path")

    if verify_rpt_path is None:
        raise ValueError("verify_rpt_path is missing at finalize stage")

    if verify_rpt is None:
        verify_rpt = _build_pass_report(
            task_payload=state["task_payload"],
            compile_log_path=state.get("compile_log_path"),
        )

    Path(verify_rpt_path).write_text(verify_rpt.model_dump_json(indent=2), encoding="utf-8")

    verify_output = VerifyNodeOutput(
        report=verify_rpt,
        summary=f"Verification completed for {verify_rpt.top_module} at iteration {verify_rpt.iteration}",
    )

    return {
        "verify_rpt": verify_rpt,
        "verify_output": verify_output,
    }


def build_verify_workflow_graph():
    """
    构建 Verify 内部状态机。

    当前执行路径：
    START
      -> init_context
      -> semantic_check
      -> compile_check
      -> finalize
      -> END

    后续可扩展方向：
    - 在 compile_check 后增加 simulate 节点
    - 增加 coverage 节点
    - 增加 report post-process 节点
    """
    graph = StateGraph(VerifyWorkflowState)

    graph.add_node("init_context", init_context_node)
    graph.add_node("semantic_check", semantic_check_node)
    graph.add_node("compile_check", compile_check_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "init_context")
    graph.add_edge("init_context", "semantic_check")
    graph.add_edge("semantic_check", "compile_check")
    graph.add_edge("compile_check", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


def run_verify_workflow(payload: VerifyTaskPayload) -> VerifyNodeOutput:
    """
    Verify 工作流统一入口。

    输入：
    - Parser 下发的 VerifyTaskPayload

    输出：
    - VerifyNodeOutput（仅包含结构化报告与摘要，不直接返回大日志文本）
    """
    app = build_verify_workflow_graph()

    initial_state: VerifyWorkflowState = {
        "task_payload": payload,
        "iteration": payload.task.iteration,
        "messages": [],
        "spec_reg": None,
        "rtl_text": None,
        "sim_dir": None,
        "verify_rpt_path": None,
        "compile_log_path": None,
        "compile_errors": None,
        "verify_rpt": None,
        "verify_output": None,
    }

    final_state = app.invoke(initial_state)

    verify_output = final_state.get("verify_output")
    if verify_output is None:
        raise RuntimeError("verify workflow failed to produce VerifyNodeOutput")

    return verify_output