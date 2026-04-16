from __future__ import annotations

import operator
import os
import shutil
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from src.common.models import (
    GenNodeOutput,
    IntentCategory,
    TaskPaths,
    UserTaskSpec,
    WorkTaskPayload,
    WorkflowRunRequest,
    WorkflowRunResult,
    WorkflowTraceStep,
    build_task_paths,
    generate_global_task_id,
)


class WorkflowState(TypedDict):
    """
    Parser 侧 LangGraph 全局状态。

    当前版本目标：
    - 先打通 Parser -> Generator 的最小闭环
    - 暂时不接入 Verify
    - 实现“接收请求 -> 初始化任务 -> 调用生成 -> 归档成功 -> 返回结果”
    """

    request: WorkflowRunRequest
    task: Optional[WorkTaskPayload]  # 当前任务的轻量载荷
    trace: Annotated[List[WorkflowTraceStep], operator.add]  # 执行轨迹
    gen_output: Optional[GenNodeOutput]  # Generator 输出

    task_paths: Optional[TaskPaths]  # 当前任务的统一目录布局
    user_task_spec_path: Optional[str]  # Output 目录中的 UserTaskSpec 路径
    origin_input_path: Optional[str]  # 原始输入文件落盘路径

    final_stage: str  # 最终停留阶段
    success: bool  # 工作流是否成功
    error: Optional[str]  # 预留错误字段


def _route_intent(raw_input_text: str) -> IntentCategory:
    """
    简化版语义路由器。

    当前实现仅使用关键词做粗粒度路由，后续可替换为真正的 Semantic Router / LLM 分类器。
    """
    normalized = raw_input_text.lower()

    if "fix" in normalized or "修复" in normalized:
        return IntentCategory.FIX_BUG
    if "verify" in normalized or "验证" in normalized:
        return IntentCategory.VERIFY_ONLY
    if "modify" in normalized or "修改" in normalized:
        return IntentCategory.MODIFY_EXISTING
    return IntentCategory.GEN_WITH_TEST


def _build_refined_requirements(request: WorkflowRunRequest) -> List[str]:
    """
    为 UserTaskSpec 构建 refined_requirements。

    规则：
    1. 如果请求中已经提供 refined_requirements，则直接使用；
    2. 否则用 raw_input_text 去空白后的文本作为单条需求兜底。

    原因：
    - UserTaskSpec 要求 refined_requirements 至少一项；
    - 但 WorkflowRunRequest 允许 refined_requirements 为空。
    """
    if request.refined_requirements:
        return request.refined_requirements

    fallback = request.raw_input_text.strip()
    if fallback:
        return [fallback]

    raise ValueError("cannot build refined_requirements from empty request")


def _ensure_task_directories(task_paths: TaskPaths) -> None:
    """
    创建任务运行所需目录。

    目录包括：
    - Output/TASK_ID/Origin
    - Output/TASK_ID/Archive
    - Output/TASK_ID/Result
    - SharedWorkspace/TASK_ID/specs
    - SharedWorkspace/TASK_ID/rtl
    - SharedWorkspace/TASK_ID/sim
    """
    for path_str in [
        task_paths.origin_dir,
        task_paths.archive_dir,
        task_paths.result_dir,
        task_paths.specs_dir,
        task_paths.rtl_dir,
        task_paths.sim_dir,
    ]:
        Path(path_str).mkdir(parents=True, exist_ok=True)


def parser_initialize_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 1：Parser 冷启动初始化。

    职责：
    1. 生成 task_id；
    2. 创建 Output 与 SharedWorkspace 下的任务目录；
    3. 将原始输入落盘到 Origin；
    4. 进行意图路由，构造 UserTaskSpec；
    5. 将 UserTaskSpec 分别落盘到 Output 与 SharedWorkspace/specs；
    6. 构造 WorkTaskPayload，供 Generator 使用。
    """
    request = state["request"]
    task_id = generate_global_task_id()

    # 使用统一路径构造器，避免路径逻辑散落在代码中。
    task_paths = build_task_paths(
        task_id=task_id,
        output_root=request.output_root,
        shared_workspace_root=request.shared_workspace_root,
    )
    _ensure_task_directories(task_paths)

    # 原始输入落盘到 Output/TASK_ID/Origin
    origin_input_path = Path(task_paths.origin_dir) / request.input_filename
    origin_input_path.write_text(request.raw_input_text or "", encoding="utf-8")

    # 路由意图：若用户显式传入，则优先采用
    resolved_intent = request.intent if request.intent is not None else _route_intent(request.raw_input_text)

    refined_requirements = _build_refined_requirements(request)

    # 构建 Parser 阶段的结构化任务规约
    user_task_spec = UserTaskSpec(
        task_id=task_id,
        iteration=0,
        intent=resolved_intent,
        top_module=request.top_module,
        prompt_workspace_path=str(origin_input_path),
        refined_requirements=refined_requirements,
        workspace_dir=task_paths.shared_task_dir,
        external_target_path=task_paths.result_dir,
        design_rules=[],
    )

    # 落盘一份到 Output 根目录，便于人工查看与审计
    output_user_task_spec_path = Path(task_paths.user_task_spec_path)
    output_user_task_spec_path.write_text(
        user_task_spec.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # 再落盘一份到 SharedWorkspace/specs，供 Generator 服务读取
    shared_user_task_spec_path = Path(task_paths.specs_dir) / "UserTaskSpec.json"
    shared_user_task_spec_path.write_text(
        user_task_spec.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # 轻量控制面载荷：传路径，不传大文本
    task = WorkTaskPayload(
        task_id=task_id,
        iteration=0,
        intent=resolved_intent,
        top_module=request.top_module,
        spec_file_path=str(shared_user_task_spec_path),
        shared_task_dir=task_paths.shared_task_dir,
    )

    return {
        "task": task,
        "task_paths": task_paths,
        "user_task_spec_path": str(output_user_task_spec_path),
        "origin_input_path": str(origin_input_path),
        "trace": [
            WorkflowTraceStep(
                node="parser_initialize",
                status="success",
                detail=f"initialized task workspace and persisted origin input to {origin_input_path}",
                iteration=0,
            )
        ],
    }


def gen_stateless_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 2：调用 Generator 内部服务。

    职责：
    1. 从状态中读取 WorkTaskPayload；
    2. 调用内部 Generator 服务；
    3. 获取 GenNodeOutput；
    4. 将生成结果写回工作流状态。

    当前为了排查 422 问题，会在失败时打印 Generator 返回的详细 body。
    """
    task = state.get("task")
    if task is None:
        raise ValueError("task payload is missing")

    gen_base_url = os.getenv("GEN_SERVICE_URL", "http://gen:8000")
    endpoint = f"{gen_base_url}/v1/generate"

    payload_json = task.model_dump(mode="json")
    print("GEN PAYLOAD:", payload_json)

    with httpx.Client(timeout=20.0) as client:
        response = client.post(endpoint, json=payload_json)

    if response.status_code >= 400:
        raise ValueError(
            f"generator request failed: status={response.status_code}, body={response.text}, payload={payload_json}"
        )

    response_payload = response.json()
    if response_payload.get("status") != "success" or response_payload.get("data") is None:
        raise ValueError(f"generator returned invalid data: {response_payload}")

    gen_output = GenNodeOutput.model_validate(response_payload["data"])

    return {
        "gen_output": gen_output,
        "trace": [
            WorkflowTraceStep(
                node="gen_stateless",
                status="success",
                detail=str(response_payload.get("message", "generator completed")),
                iteration=task.iteration,
            )
        ],
    }


def archive_success_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 3：成功归档节点。

    当前最小闭环模式下，不等待 Verify，Generator 成功即视为本阶段成功。

    职责：
    1. 将 SharedWorkspace/TASK_ID 下的所有产物复制到 Output/TASK_ID/Result/shared_workspace；
    2. 复制完成后删除 SharedWorkspace/TASK_ID，实现空间回收；
    3. 记录归档成功轨迹。
    """
    task_paths = state.get("task_paths")
    if task_paths is None:
        raise ValueError("task paths missing")

    source = Path(task_paths.shared_task_dir)
    target = Path(task_paths.result_dir) / "shared_workspace"

    if target.exists():
        shutil.rmtree(target)

    if source.exists():
        shutil.copytree(source, target)
        shutil.rmtree(source)

    task = state.get("task")
    current_iteration = task.iteration if task is not None else 0

    return {
        "trace": [
            WorkflowTraceStep(
                node="archive_success",
                status="success",
                detail=f"archived generated artifacts to {target}",
                iteration=current_iteration,
            )
        ],
        "final_stage": "archive_success",
        "success": True,
    }


def build_workflow_graph():
    """
    构建当前阶段的最小闭环工作流图。

    执行路径：
    START
      -> parser_initialize
      -> gen_stateless
      -> archive_success
      -> END

    说明：
    - 当前版本专注打通 Parser + Generator 的主链路；
    - Verify 将在后续阶段接回流程。
    """
    graph = StateGraph(WorkflowState)

    graph.add_node("parser_initialize", parser_initialize_node)
    graph.add_node("gen_stateless", gen_stateless_node)
    graph.add_node("archive_success", archive_success_node)

    graph.add_edge(START, "parser_initialize")
    graph.add_edge("parser_initialize", "gen_stateless")
    graph.add_edge("gen_stateless", "archive_success")
    graph.add_edge("archive_success", END)

    return graph.compile()


def run_workflow(request: WorkflowRunRequest) -> WorkflowRunResult:
    """
    Parser 工作流统一入口。

    输入：
    - WorkflowRunRequest

    输出：
    - WorkflowRunResult

    当前阶段说明：
    - 一旦 Generator 成功落盘产物，即返回 success=True；
    - 不等待 Verify 服务。
    """
    app = build_workflow_graph()

    initial_state: WorkflowState = {
        "request": request,
        "task": None,
        "trace": [],
        "gen_output": None,
        "task_paths": None,
        "user_task_spec_path": None,
        "origin_input_path": None,
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
        verify_output=None,
    )