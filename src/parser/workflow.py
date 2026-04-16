from __future__ import annotations

import operator
import os
import shutil
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from src.common.models import (
    GenNodeOutput,
    IntentCategory,
    UserTaskSpec,
    VerifyNodeOutput,
    VerifyTaskPayload,
    VerifyVerdict,
    WorkTaskPayload,
    WorkflowRunRequest,
    WorkflowRunResult,
    WorkflowTraceStep,
    generate_global_task_id,
)


class WorkflowState(TypedDict):
    """LangGraph 全局状态字典，用于在节点间传递上下文"""
    request: WorkflowRunRequest
    task: Optional[WorkTaskPayload]  # 当前流转的任务载荷
    trace: Annotated[List[WorkflowTraceStep], operator.add]  # 节点执行轨迹，支持追加
    gen_output: Optional[GenNodeOutput]  # Gen 节点的输出结果
    verify_output: Optional[VerifyNodeOutput]  # Verify 节点的输出结果
    user_task_spec_path: Optional[str]  # 结构化规约落盘路径
    origin_input_path: Optional[str]  # 原始需求落盘路径
    output_task_dir: Optional[str]  # 宿主机或输出挂载的专属任务目录
    shared_task_dir: Optional[str]  # 共享工作区 (Sandbox) 目录
    max_iterations: int  # 最大允许的重试/迭代轮次
    final_stage: str  # 最终停留在的阶段节点
    success: bool  # 工作流最终成功与否标志
    error: Optional[str]  # 全局错误信息


def _route_intent(raw_input_text: str) -> IntentCategory:
    """
    语义路由 (Semantic Router) 的降级/简单实现。
    此处根据自然语言的关键词进行粗略的意图分类。
    后续可拓展为接入 LLM 进行精准判断。
    """
    normalized = raw_input_text.lower()
    # Agent_DEF.md: "例如，用户提到“修复”，路由至 FIX_BUG；提到“新模块”，路由至 GEN_WITH_TEST。"
    if "fix" in normalized or "修复" in normalized:
        return IntentCategory.FIX_BUG
    if "verify" in normalized or "验证" in normalized:
        return IntentCategory.VERIFY_ONLY
    if "modify" in normalized or "修改" in normalized:
        return IntentCategory.MODIFY_EXISTING
    return IntentCategory.GEN_WITH_TEST


def parser_initialize_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 1：工作流冷启动。
    职责：分配 UUID，创建隔离的目录规范，将非结构化输入转化为 UserTaskSpec 并落盘。
    """
    request = state["request"]
    task_id = generate_global_task_id()

    # 1. 按照 Agent_DEF.md 规范构建 /Output 下的物理目录结构
    output_task_dir = Path(request.output_root) / task_id
    origin_dir = output_task_dir / "Origin"
    archive_dir = output_task_dir / "Archive"
    result_dir = output_task_dir / "Result"
    
    # 2. 构建共享工作区 (Sandbox) 目录，用于模块间环境隔离
    shared_task_dir = Path(request.shared_workspace_root) / task_id
    shared_specs_dir = shared_task_dir / "specs"
    shared_rtl_dir = shared_task_dir / "rtl"
    shared_sim_dir = shared_task_dir / "sim"

    for path in [origin_dir, archive_dir, result_dir, shared_specs_dir, shared_rtl_dir, shared_sim_dir]:
        path.mkdir(parents=True, exist_ok=True)

    # 3. 保存原始需求至 /Origin (非结构化文本落盘)
    origin_input_path = origin_dir / request.input_filename
    origin_input_path.write_text(request.raw_input_text or "", encoding="utf-8")

    # 4. 语义路由，实例化 UserTaskSpec (结构化规约)
    resolved_intent = request.intent if request.intent is not None else _route_intent(request.raw_input_text)
    user_task_spec = UserTaskSpec(
        task_id=task_id,
        iteration=0,
        intent=resolved_intent,
        top_module=request.top_module,
        prompt_workspace_path=str(origin_input_path),
        refined_requirements=request.refined_requirements,
        workspace_dir=str(shared_task_dir),
        external_target_path=str(result_dir),
        design_rules=[],
    )

    # 将规约备份到 Output 任务根目录
    user_task_spec_path = output_task_dir / "UserTaskSpec.json"
    user_task_spec_path.write_text(
        user_task_spec.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # 将规约落盘至共享工作区 (轻量化数据平面通信基础)
    shared_user_task_spec_path = shared_specs_dir / "UserTaskSpec.json"
    shared_user_task_spec_path.write_text(
        user_task_spec.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # 5. 实例化任务总线载荷 WorkTaskPayload
    task = WorkTaskPayload(
        task_id=task_id,
        iteration=0,
        intent=resolved_intent,
        top_module=request.top_module,
        spec_file_path=str(shared_user_task_spec_path),
        shared_task_dir=str(shared_task_dir),
    )

    return {
        "task": task,
        "trace": [
            WorkflowTraceStep(
                node="parser_initialize",
                status="success",
                detail=f"created task workspace and persisted origin input: {origin_input_path}",
            )
        ],
        "user_task_spec_path": str(user_task_spec_path),
        "origin_input_path": str(origin_input_path),
        "output_task_dir": str(output_task_dir),
        "shared_task_dir": str(shared_task_dir),
        "max_iterations": request.max_iterations,
    }


def gen_stateless_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 2：Gen 模块无状态调用。
    职责：通过 HTTP 请求触发 Generator 服务，仅在控制面传递任务元数据，
    不传递大段 RTL 代码。
    """
    task = state.get("task")
    if task is None:
        raise ValueError("task payload is missing")

    gen_base_url = os.getenv("GEN_SERVICE_URL", "http://gen:8000")
    endpoint = f"{gen_base_url}/v1/generate"

    # 外部网络调用，发起无状态生成请求
    with httpx.Client(timeout=15.0) as client:
        response = client.post(endpoint, json=task.model_dump(mode="json"))
        response.raise_for_status()

    response_payload = response.json()
    if response_payload.get("status") != "success" or response_payload.get("data") is None:
        raise ValueError("generator returned empty data")
    gen_output = GenNodeOutput.model_validate(response_payload["data"], strict=False)

    trace_step = WorkflowTraceStep(
        node="gen_stateless", status="success", detail=str(response_payload.get("message", ""))
    )
    return {"gen_output": gen_output, "trace": [trace_step]}


def verify_stateless_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 3：Verify 模块无状态调用。
    职责：将 Gen 生成的路径 (spec 和 rtl) 转交给验证模块。
    此时 Parser 充当编排器收集验证节点的 Verdict。
    """
    task = state.get("task")
    gen_output = state.get("gen_output")
    if task is None:
        raise ValueError("task payload is missing")
    if gen_output is None:
        raise ValueError("generator output is missing")

    verify_base_url = os.getenv("VERIFY_SERVICE_URL", "http://verify:8000")
    endpoint = f"{verify_base_url}/v1/verify"

    # 构建交接给验证模块的载荷 (数据面传递路径而非字符串)
    verify_payload = VerifyTaskPayload(
        task=task,
        spec_file_path=gen_output.spec_file_path,
        rtl_path=gen_output.rtl_path,
    )

    with httpx.Client(timeout=20.0) as client:
        response = client.post(endpoint, json=verify_payload.model_dump(mode="json"))
        response.raise_for_status()

    response_payload = response.json()
    if response_payload.get("status") != "success" or response_payload.get("data") is None:
        raise ValueError("verify returned empty data")
    verify_output = VerifyNodeOutput.model_validate(response_payload["data"], strict=False)

    trace_step = WorkflowTraceStep(
        node="verify_stateless", status="success", detail=str(response_payload.get("message", ""))
    )
    return {"verify_output": verify_output, "trace": [trace_step]}


def route_after_verify(
    state: WorkflowState,
) -> Literal["archive_success", "retry_generation", "archive_failed"]:
    """
    条件路由边 (Conditional Edge)。
    根据 VerifyNodeOutput.report.verdict，决定是推进迭代重试还是终止并归档。
    """
    task = state.get("task")
    verify_output = state.get("verify_output")
    if task is None or verify_output is None:
        return "archive_failed"

    # 如果通过，直接走向成功归档
    if verify_output.report.verdict == VerifyVerdict.PASS:
        return "archive_success"

    # 如果失败，且当前重试次数未达上限，则循环重试
    if task.iteration + 1 < state.get("max_iterations", 1):
        return "retry_generation"
        
    # 超过最大轮次依然失败，走向失败归档
    return "archive_failed"


def prepare_retry_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 4：准备重试上下文。
    职责：递增 iteration，收集错误详情作为下一轮 Gen 的输入提示。
    """
    task = state.get("task")
    verify_output = state.get("verify_output")
    if task is None or verify_output is None:
        raise ValueError("cannot prepare retry without task and verify output")

    task.iteration += 1
    detail = (
        f"prepare retry iteration={task.iteration}, verdict={verify_output.report.verdict}, "
        f"fix_hint={verify_output.report.error_details.suggested_fix}"
    )
    return {"task": task, "trace": [WorkflowTraceStep(node="prepare_retry", status="error", detail=detail)]}


def archive_success_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 5：成功归档节点。
    职责：将 /SharedWorkspace 中的所有中间产物搬运到 /Output/TASK_ID/Result 下，
    并回收 (rm -rf) 共享工作区空间。
    """
    output_task_dir = state.get("output_task_dir")
    shared_task_dir = state.get("shared_task_dir")
    if output_task_dir is None or shared_task_dir is None:
        raise ValueError("archive path missing")

    result_dir = Path(output_task_dir) / "Result"
    source = Path(shared_task_dir)
    target = result_dir / "shared_workspace"
    if target.exists():
        shutil.rmtree(target)
    # Agent_DEF.md 要求：空间回收与搬运
    if source.exists():
        shutil.copytree(source, target)
        shutil.rmtree(source)

    trace_step = WorkflowTraceStep(
        node="archive_success", status="success", detail=f"archived artifacts to {target}"
    )
    return {"trace": [trace_step], "final_stage": "archive_success", "success": True}


def archive_failed_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 6：失败归档节点。
    职责：当达到最大重试次数依旧失败时，将现场保留至 /Output/TASK_ID/Archive，
    并清理工作区。
    """
    output_task_dir = state.get("output_task_dir")
    shared_task_dir = state.get("shared_task_dir")
    if output_task_dir is None or shared_task_dir is None:
        raise ValueError("archive path missing")

    archive_dir = Path(output_task_dir) / "Archive"
    source = Path(shared_task_dir)
    target = archive_dir / "shared_workspace"
    if target.exists():
        shutil.rmtree(target)
    if source.exists():
        shutil.copytree(source, target)
        shutil.rmtree(source)

    trace_step = WorkflowTraceStep(
        node="archive_failed", status="error", detail=f"archived failed artifacts to {target}"
    )
    return {"trace": [trace_step], "final_stage": "archive_failed", "success": False}


def build_workflow_graph():
    """
    编排装配：使用 LangGraph 将所有无状态 HTTP 调度节点和持久化节点拼装为有限状态机。
    """
    graph = StateGraph(WorkflowState)

    graph.add_node("parser_initialize", parser_initialize_node)
    graph.add_node("gen_stateless", gen_stateless_node)
    graph.add_node("verify_stateless", verify_stateless_node)
    graph.add_node("prepare_retry", prepare_retry_node)
    graph.add_node("archive_success", archive_success_node)
    graph.add_node("archive_failed", archive_failed_node)

    graph.add_edge(START, "parser_initialize")
    graph.add_edge("parser_initialize", "gen_stateless")
    graph.add_edge("gen_stateless", "verify_stateless")
    graph.add_conditional_edges(
        "verify_stateless",
        route_after_verify,
        {
            "archive_success": "archive_success",
            "retry_generation": "prepare_retry",
            "archive_failed": "archive_failed",
        },
    )
    graph.add_edge("prepare_retry", "gen_stateless")
    graph.add_edge("archive_success", END)
    graph.add_edge("archive_failed", END)

    return graph.compile()


def run_workflow(request: WorkflowRunRequest) -> WorkflowRunResult:
    app = build_workflow_graph()
    initial_state: WorkflowState = {
        "request": request,
        "task": None,
        "trace": [],
        "gen_output": None,
        "verify_output": None,
        "user_task_spec_path": None,
        "origin_input_path": None,
        "output_task_dir": None,
        "shared_task_dir": None,
        "max_iterations": request.max_iterations,
        "final_stage": "unknown",
        "success": False,
        "error": None,
    }

    final_state = app.invoke(initial_state)
    task = final_state.get("task")
    if task is None:
        raise RuntimeError("workflow ended without task payload")

    return WorkflowRunResult(
        task_id=task.task_id,
        final_stage=final_state.get("final_stage", "unknown"),
        success=final_state.get("success", False),
        trace=final_state.get("trace", []),
        gen_output=final_state.get("gen_output"),
        verify_output=final_state.get("verify_output"),
    )
