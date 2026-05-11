from __future__ import annotations

import logging
import operator
import json
import os
import re
import shutil
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from src.common.models import (
    GenNodeOutput,
    IntentCategory,
    LlmRuntimeConfig,
    ParserLlmAnalysis,
    TaskPaths,
    UserTaskSpec,
    VerifyNodeOutput,
    VerifyRpt,
    VerifyTaskPayload,
    WorkTaskPayload,
    WorkflowRunRequest,
    WorkflowRunResult,
    WorkflowTraceStep,
    build_task_paths,
    generate_global_task_id,
)

from src.common.llm_utils import (
    LLM_HEADER_ENABLED,
    LLM_HEADER_API_KEY,
    LLM_HEADER_BASE_URL,
    LLM_HEADER_MODEL,
    LLM_HEADER_PROFILE,
    _chat_completions_url,
    _extract_json_object,
)


class WorkflowState(TypedDict):
    """LangGraph 全局状态字典，用于在各节点之间传递上下文。"""

    request: WorkflowRunRequest
    task: Optional[WorkTaskPayload]  # 当前流转中的轻量任务载荷
    trace: Annotated[List[WorkflowTraceStep], operator.add]  # 节点执行轨迹，支持追加
    gen_output: Optional[GenNodeOutput]  # Generator 节点输出
    verify_output: Optional[VerifyNodeOutput]  # Verify 节点输出

    task_paths: Optional[TaskPaths]  # 统一任务目录布局对象
    user_task_spec_path: Optional[str]  # Output 目录中的 UserTaskSpec 路径（便于结果查看）
    origin_input_path: Optional[str]  # 原始输入落盘路径（便于追踪与审计）

    max_iterations: int  # 最大允许迭代轮次
    final_stage: str  # 工作流最终停留节点
    success: bool  # 工作流是否成功
    error: Optional[str]  # 预留的全局错误信息


def _route_intent(raw_input_text: str) -> IntentCategory:
    """
    语义路由（当前为降级实现）。

    这里使用关键词进行粗分类：
    - 包含“fix/修复” -> FIX_BUG
    - 包含“verify/验证” -> VERIFY_ONLY
    - 包含“modify/修改” -> MODIFY_EXISTING
    - 默认 -> GEN_WITH_TEST

    后续如果接入 LLM / Semantic Router，可直接替换本函数实现。
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
    为 UserTaskSpec 生成可落盘的 refined_requirements。

    说明：
    - 当前 UserTaskSpec 要求 refined_requirements 至少包含一项。
    - 但 WorkflowRunRequest 允许 refined_requirements 为空，只要 raw_input_text 非空即可。
    - 因此这里提供统一兜底逻辑，避免初始化节点因字段约束失败。

    规则：
    1. 若请求中已提供 refined_requirements，则直接使用。
    2. 否则使用 raw_input_text 去除首尾空白后的结果作为单条需求。
    """
    if request.refined_requirements:
        return request.refined_requirements

    fallback = request.raw_input_text.strip()
    if fallback:
        return [fallback]

    # 理论上不会走到这里，因为 WorkflowRunRequest 已经保证二者至少有一个非空。
    raise ValueError("cannot build refined_requirements from empty request")


def _resolve_llm_config(request: WorkflowRunRequest) -> LlmRuntimeConfig:
    if request.llm is not None:
        return request.llm

    return LlmRuntimeConfig(
        enabled=os.getenv("AGVS4RTL_LLM_ENABLED", "false").lower() == "true",
        base_url=os.getenv("AGVS4RTL_LLM_BASE_URL") or None,
        api_key=os.getenv("AGVS4RTL_LLM_API_KEY") or None,
        model=os.getenv("AGVS4RTL_LLM_MODEL") or None,
        profile=os.getenv("AGVS4RTL_LLM_PROFILE", "default"),
    )


def _call_parser_llm(
    llm_config: LlmRuntimeConfig,
    request: WorkflowRunRequest,
) -> tuple[ParserLlmAnalysis, Dict[str, Any]]:
    if not llm_config.base_url:
        raise ValueError("LLM is enabled but base_url is missing")
    if llm_config.api_key is None:
        raise ValueError("LLM is enabled but api_key is missing")
    if not llm_config.model:
        raise ValueError("LLM is enabled but model is missing")

    allowed_intents = [intent.value for intent in IntentCategory]
    messages = [
        {
            "role": "system",
            "content": (
                "You are the Parser node for an RTL generation workflow. "
                "Classify the user's task and refine requirements. "
                "Return JSON only, with keys: intent, refined_requirements, target_protocol, design_rules. "
                f"intent must be one of: {', '.join(allowed_intents)}. "
                "Use null when target_protocol is unknown. Keep requirements concise and actionable."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "top_module": request.top_module,
                    "raw_input_text": request.raw_input_text,
                    "provided_intent": request.intent.value if request.intent is not None else None,
                    "provided_refined_requirements": request.refined_requirements,
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]
    payload = {
        "model": llm_config.model,
        "messages": messages,
        "temperature": 0.0,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {llm_config.api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }

    try:
        llm_timeout = float(os.getenv("AGVS4RTL_LLM_TIMEOUT_SECONDS", "300"))
    except Exception:
        llm_timeout = 300.0
    with httpx.Client(timeout=llm_timeout) as client:
        response = client.post(_chat_completions_url(llm_config.base_url), json=payload, headers=headers)
        response.raise_for_status()

    response_payload = response.json()
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("LLM parser response is not OpenAI chat-completions compatible") from exc
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM parser response content is empty")

    analysis = ParserLlmAnalysis.model_validate(_extract_json_object(content))

    sanitized_choices = []
    for response_choice in response_payload.get("choices", []):
        if not isinstance(response_choice, dict):
            continue
        message = response_choice.get("message")
        if not isinstance(message, dict):
            continue
        sanitized_choices.append(
            {
                "index": response_choice.get("index"),
                "message": {
                    "role": message.get("role"),
                    "content": message.get("content"),
                },
                "finish_reason": response_choice.get("finish_reason"),
            }
        )

    return analysis, {
        "stage": "parser",
        "profile": llm_config.profile,
        "request": {
            "messages": messages,
            "temperature": payload["temperature"],
            "stream": payload["stream"],
        },
        "response": {
            "id": response_payload.get("id"),
            "object": response_payload.get("object"),
            "created": response_payload.get("created"),
            "choices": sanitized_choices,
            "usage": response_payload.get("usage"),
        },
        "parsed": analysis.model_dump(mode="json"),
    }


def _analyze_request_with_llm(
    request: WorkflowRunRequest,
    llm_config: LlmRuntimeConfig,
) -> tuple[Optional[ParserLlmAnalysis], Optional[Dict[str, Any]], Optional[str]]:
    _log = logging.getLogger(__name__)
    if not llm_config.enabled:
        _log.warning("Parser LLM analysis skipped: LLM not enabled")
        return None, None, None
    request_text = "\n".join([request.raw_input_text, *request.refined_requirements])
    if "AGVS4RTL_INJECT_" in request_text:
        _log.info("Parser LLM analysis skipped: injection directive detected")
        return None, None, None
    try:
        analysis, transcript = _call_parser_llm(llm_config, request)
        return analysis, transcript, None
    except Exception as exc:
        _log.error("Parser LLM analysis failed: %s", exc)
        return None, None, str(exc)


def _build_llm_forward_headers(request: WorkflowRunRequest) -> Dict[str, str]:
    llm_config = _resolve_llm_config(request)
    headers = {
        LLM_HEADER_ENABLED: "true" if llm_config.enabled else "false",
        LLM_HEADER_PROFILE: llm_config.profile,
    }

    if llm_config.base_url is not None:
        headers[LLM_HEADER_BASE_URL] = llm_config.base_url
    if llm_config.model is not None:
        headers[LLM_HEADER_MODEL] = llm_config.model
    if llm_config.api_key is not None:
        headers[LLM_HEADER_API_KEY] = llm_config.api_key.get_secret_value()

    return headers


def _ensure_task_directories(task_paths: TaskPaths) -> None:
    """
    创建本任务运行所需的全部目录。

    目录包括：
    - Output/TASK_ID/Origin
    - Output/TASK_ID/Archive
    - Output/TASK_ID/Result
    - SharedWorkspace/TASK_ID/specs
    - SharedWorkspace/TASK_ID/rtl
    - SharedWorkspace/TASK_ID/sim
    - SharedWorkspace/TASK_ID/llm
    """
    for path_str in [
        task_paths.origin_dir,
        task_paths.archive_dir,
        task_paths.result_dir,
        task_paths.specs_dir,
        task_paths.rtl_dir,
        task_paths.sim_dir,
        f"{task_paths.shared_task_dir}/llm",
    ]:
        Path(path_str).mkdir(parents=True, exist_ok=True)


def parser_initialize_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 1：Parser 冷启动初始化节点。

    职责：
    1. 生成全局唯一 task_id。
    2. 依据统一目录规范构建 Output 与 SharedWorkspace 路径。
    3. 创建任务目录。
    4. 将用户原始输入落盘到 Origin。
    5. 进行意图路由，构建 UserTaskSpec。
    6. 将 UserTaskSpec 同时落盘到 Output 与 SharedWorkspace/specs。
    7. 生成轻量任务载荷 WorkTaskPayload，供 Generator/Verify 调度使用。
    """
    request = state["request"]
    task_id = request.task_id or generate_global_task_id()
    llm_config = _resolve_llm_config(request)

    # 基于统一路径工厂函数创建任务目录布局，避免散落的字符串拼接逻辑。
    task_paths = build_task_paths(
        task_id=task_id,
        output_root=request.output_root,
        shared_workspace_root=request.shared_workspace_root,
    )

    # 确保所有目录存在。
    _ensure_task_directories(task_paths)

    # 原始输入首先落盘到 Output/TASK_ID/Origin，作为任务原始审计记录。
    origin_input_path = Path(task_paths.origin_dir) / request.input_filename
    origin_input_path.write_text(request.raw_input_text or "", encoding="utf-8")

    parser_analysis, parser_transcript, parser_llm_error = _analyze_request_with_llm(request, llm_config)
    if parser_transcript is not None:
        llm_dir = Path(task_paths.shared_task_dir) / "llm"
        llm_dir.mkdir(parents=True, exist_ok=True)
        llm_trace_path = llm_dir / "ParserChat_iter0.json"
        llm_trace_path.write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "iteration": 0,
                    "top_module": request.top_module,
                    "transcripts": [parser_transcript],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # 进行意图路由；如果调用者显式指定 intent，则优先使用显式值。
    if request.intent is not None:
        resolved_intent = request.intent
    elif parser_analysis is not None and parser_analysis.intent is not None:
        resolved_intent = parser_analysis.intent
    else:
        resolved_intent = _route_intent(request.raw_input_text)

    # 生成满足 UserTaskSpec 约束的 refined_requirements。
    if request.refined_requirements:
        refined_requirements = request.refined_requirements
    elif parser_analysis is not None and parser_analysis.refined_requirements:
        refined_requirements = parser_analysis.refined_requirements
    else:
        refined_requirements = _build_refined_requirements(request)

    # 结构化规约对象：这是 Parser 阶段的核心产物。
    user_task_spec = UserTaskSpec(
        task_id=task_id,
        iteration=0,
        intent=resolved_intent,
        top_module=request.top_module,
        prompt_workspace_path=str(origin_input_path),
        refined_requirements=refined_requirements,
        workspace_dir=task_paths.shared_task_dir,
        external_target_path=task_paths.result_dir,
        target_protocol=parser_analysis.target_protocol if parser_analysis is not None else None,
        design_rules=parser_analysis.design_rules if parser_analysis is not None else [],
    )

    # 1) 将 UserTaskSpec 保存到 Output/TASK_ID/UserTaskSpec.json，方便归档与人工查看。
    output_user_task_spec_path = Path(task_paths.user_task_spec_path)
    output_user_task_spec_path.write_text(
        user_task_spec.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # 2) 将同一份规约同步到 SharedWorkspace/specs，供 Generator 读取。
    shared_user_task_spec_path = Path(task_paths.specs_dir) / "UserTaskSpec.json"
    shared_user_task_spec_path.write_text(
        user_task_spec.model_dump_json(indent=2),
        encoding="utf-8",
    )

    # 生成轻量调度载荷：控制面只传路径与任务元信息，不直接传递大文本。
    task = WorkTaskPayload(
        task_id=task_id,
        iteration=0,
        intent=resolved_intent,
        top_module=request.top_module,
        spec_file_path=str(shared_user_task_spec_path),
        shared_task_dir=task_paths.shared_task_dir,
    )

    trace_detail = f"initialized task workspace and persisted origin input to {origin_input_path}"
    if parser_transcript is not None:
        trace_detail += "; parser LLM analysis saved to shared_workspace/llm/ParserChat_iter0.json"
    elif parser_llm_error is not None:
        trace_detail += "; parser LLM analysis failed, used fallback parser"
    else:
        trace_detail += "; parser LLM analysis skipped (disabled or injection mode)"

    return {
        "task": task,
        "task_paths": task_paths,
        "user_task_spec_path": str(output_user_task_spec_path),
        "origin_input_path": str(origin_input_path),
        "max_iterations": request.max_iterations,
        "trace": [
            WorkflowTraceStep(
                node="parser_initialize",
                status="success",
                detail=trace_detail,
                iteration=0,
            )
        ],
    }


def gen_stateless_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 2：无状态调用 Generator 服务。

    职责：
    1. 从状态中读取 WorkTaskPayload。
    2. 通过 HTTP 调用内部 Generator 服务。
    3. 接收生成结果（SpecReg 路径 + RTL 路径）。
    4. 将结果写回工作流状态。
    """
    task = state.get("task")
    request = state.get("request")
    if task is None:
        raise ValueError("task payload is missing")
    if request is None:
        raise ValueError("workflow request is missing")

    gen_base_url = os.getenv("GEN_SERVICE_URL", "http://gen:8000")
    endpoint = f"{gen_base_url}/v1/generate"

    # 注意：这里只通过控制面传递轻量载荷，不直接传输大段 RTL 文本。
    # 支持 LLM 生成等慢路径，超时可通过 GEN_SERVICE_TIMEOUT_SECONDS 配置，默认 240 秒
    try:
        gen_timeout = float(os.getenv("GEN_SERVICE_TIMEOUT_SECONDS", "240"))
    except Exception:
        logging.getLogger(__name__).warning(
            "Invalid GEN_SERVICE_TIMEOUT_SECONDS=%s, using default 240s",
            os.getenv("GEN_SERVICE_TIMEOUT_SECONDS", ""),
        )
        gen_timeout = 240.0
    try:
        with httpx.Client(timeout=gen_timeout) as client:
            response = client.post(
                endpoint,
                json=task.model_dump(mode="json"),
                headers=_build_llm_forward_headers(request),
            )
            response.raise_for_status()
    except httpx.TimeoutException:
        return {
            "trace": [
                WorkflowTraceStep(
                    node="gen_stateless",
                    status="error",
                    detail="Generator service timed out",
                    iteration=task.iteration,
                )
            ],
            "final_stage": "archive_failed",
            "success": False,
        }
    except httpx.HTTPStatusError as exc:
        return {
            "trace": [
                WorkflowTraceStep(
                    node="gen_stateless",
                    status="error",
                    detail=f"Generator service returned HTTP {exc.response.status_code}",
                    iteration=task.iteration,
                )
            ],
            "final_stage": "archive_failed",
            "success": False,
        }

    response_payload = response.json()
    if response_payload.get("status") != "success" or response_payload.get("data") is None:
        raise ValueError("generator returned empty data")

    # 使用当前冻结版模型做协议校验；这里不再放宽 strict。
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


def verify_stateless_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 3：无状态调用 Verify 服务。

    职责：
    1. 读取当前任务载荷与 Generator 输出。
    2. 构造 VerifyTaskPayload（传路径，不传大文件内容）。
    3. 通过 HTTP 调用内部 Verify 服务。
    4. 将 VerifyNodeOutput 写回工作流状态。
    """
    task = state.get("task")
    request = state.get("request")
    gen_output = state.get("gen_output")

    if task is None:
        raise ValueError("task payload is missing")
    if request is None:
        raise ValueError("workflow request is missing")
    if gen_output is None:
        raise ValueError("generator output is missing")

    verify_base_url = os.getenv("VERIFY_SERVICE_URL", "http://verify:8000")
    endpoint = f"{verify_base_url}/v1/verify"

    verify_payload = VerifyTaskPayload(
        task=task,
        spec_file_path=gen_output.spec_file_path,
        rtl_path=gen_output.rtl_path,
        rtl_paths=gen_output.rtl_paths,
    )

    try:
        verify_timeout = float(os.getenv("VERIFY_SERVICE_TIMEOUT_SECONDS", "240"))
    except Exception:
        logging.getLogger(__name__).warning(
            "Invalid VERIFY_SERVICE_TIMEOUT_SECONDS=%s, using default 240s",
            os.getenv("VERIFY_SERVICE_TIMEOUT_SECONDS", ""),
        )
        verify_timeout = 240.0

    try:
        with httpx.Client(timeout=verify_timeout) as client:
            response = client.post(
                endpoint,
                json=verify_payload.model_dump(mode="json"),
                headers=_build_llm_forward_headers(request),
            )
            response.raise_for_status()

        response_payload = response.json()
        if response_payload.get("status") != "success" or response_payload.get("data") is None:
            raise ValueError("verify returned empty data")

        verify_output = VerifyNodeOutput.model_validate(response_payload["data"])

        return {
            "verify_output": verify_output,
            "trace": [
                WorkflowTraceStep(
                    node="verify_stateless",
                    status="success",
                    detail=str(response_payload.get("message", "verify completed")),
                    iteration=task.iteration,
                )
            ],
        }

    except httpx.TimeoutException:
        task_paths = state.get("task_paths")
        if task_paths is None:
            raise ValueError("verify service timeout and no task_paths available")

        status_path = Path(task_paths.sim_dir) / f"VerifyStatus_iter{task.iteration}.json"
        if status_path.exists():
            status_data = json.loads(status_path.read_text(encoding="utf-8"))
            status = status_data.get("status", "unknown")
            if status == "completed":
                rpt_path = Path(task_paths.sim_dir) / f"VerifyRpt_iter{task.iteration}.json"
                if rpt_path.exists():
                    verify_rpt = VerifyRpt.model_validate_json(rpt_path.read_text(encoding="utf-8"))
                    verify_output = VerifyNodeOutput(
                        report=verify_rpt,
                        summary=f"Verification completed (recovered after timeout) for {verify_rpt.top_module} at iteration {verify_rpt.iteration}",
                    )
                    return {
                        "verify_output": verify_output,
                        "trace": [
                            WorkflowTraceStep(
                                node="verify_stateless",
                                status="success",
                                detail=f"verify completed (recovered after timeout); verdict={verify_rpt.verdict}",
                                iteration=task.iteration,
                            )
                        ],
                    }
                else:
                    raise ValueError(f"Verify status is completed but VerifyRpt not found at {rpt_path}")
            else:
                raise ValueError(
                    f"Verify service is still running (status: {status}). "
                    f"Retry the same task to check for results, or increase VERIFY_SERVICE_TIMEOUT_SECONDS (currently {verify_timeout}s)."
                )
        else:
            raise ValueError(
                f"Verify service did not respond within {verify_timeout}s and no status file was found. "
                f"The verify service may not have started. Check verify container logs."
            )


def route_after_verify(
    state: WorkflowState,
) -> Literal["archive_success", "retry_generation", "archive_failed"]:
    """
    验证后的条件路由。

    路由规则：
    1. 若验证通过，则进入成功归档。
    2. 若验证失败但属于可重试类型，且未超过最大轮次，则进入重试准备节点。
    3. 其他情况进入失败归档。

    这里直接调用 VerifyRpt 的辅助方法，而不是在工作流里手写 verdict 分支，
    让“验证结果语义”更多地由模型自身承载。
    """
    task = state.get("task")
    verify_output = state.get("verify_output")

    if task is None or verify_output is None:
        return "archive_failed"

    report = verify_output.report

    if report.is_pass():
        return "archive_success"

    if report.is_retryable() and (task.iteration + 1 < state.get("max_iterations", 1)):
        return "retry_generation"

    return "archive_failed"


def prepare_retry_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 4：准备下一轮重试。

    职责：
    1. 在原任务载荷上递增 iteration。
    2. 记录本轮失败的验证结论与修复建议。
    3. 为下一次 Generator 调用保留最小必要上下文。

    注意：
    - verify_rpt_path 通过 WorkTaskPayload 协议显式传递给 Generator，
      作为 filesystem convention 发现的补充（协议优先，约定为 fallback）。
    - iteration 与共享工作区约定仍共同驱动下一轮生成。
    """
    task = state.get("task")
    verify_output = state.get("verify_output")

    if task is None or verify_output is None:
        raise ValueError("cannot prepare retry without task and verify output")

    report = verify_output.report
    next_iteration = task.iteration + 1
    task.iteration = next_iteration

    # Set explicit verify_rpt_path so Generator receives it through protocol
    # (complements the filesystem convention discovery in init_context_node)
    task_paths = state.get("task_paths")
    if task_paths is not None:
        verify_rpt_path = f"{task_paths.sim_dir}/VerifyRpt_iter{task.iteration - 1}.json"
        task.verify_rpt_path = verify_rpt_path
        logging.getLogger(__name__).info(
            "prepare_retry: iteration=%d, verify_rpt_path=%s",
            next_iteration,
            verify_rpt_path,
        )

    detail = (
        f"prepare retry iteration={next_iteration}, "
        f"verdict={report.verdict}, "
        f"refactor_hint={report.suggested_refactor_level()}, "
        f"fix_hint={report.error_details.suggested_fix}"
    )

    return {
        "task": task,
        "trace": [
            WorkflowTraceStep(
                node="prepare_retry",
                status="success",
                detail=detail,
                iteration=next_iteration,
            )
        ],
    }


def archive_success_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 5：成功归档节点。

    职责：
    1. 将 SharedWorkspace/TASK_ID 下的全部中间产物复制到 Output/TASK_ID/Result/shared_workspace。
    2. 完成复制后删除 SharedWorkspace/TASK_ID，实现空间回收。
    3. 记录成功归档轨迹。
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
                detail=f"archived artifacts to {target}",
                iteration=current_iteration,
            )
        ],
        "final_stage": "archive_success",
        "success": True,
    }


def archive_failed_node(state: WorkflowState) -> Dict[str, Any]:
    """
    节点 6：失败归档节点。

    职责：
    1. 当达到最大重试次数后仍未通过验证，将现场复制到 Output/TASK_ID/Archive/shared_workspace。
    2. 保留失败现场用于后续问题排查。
    3. 复制完成后清理 SharedWorkspace/TASK_ID。
    """
    task_paths = state.get("task_paths")
    if task_paths is None:
        raise ValueError("task paths missing")

    source = Path(task_paths.shared_task_dir)
    target = Path(task_paths.archive_dir) / "shared_workspace"

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
                node="archive_failed",
                status="error",
                detail=f"archived failed artifacts to {target}",
                iteration=current_iteration,
            )
        ],
        "final_stage": "archive_failed",
        "success": False,
    }


def build_workflow_graph():
    """
    构建 LangGraph 状态机。

    工作流主路径：
    START
      -> parser_initialize
      -> gen_stateless
      -> verify_stateless
      -> (条件路由)
         - archive_success
         - prepare_retry -> gen_stateless
         - archive_failed
      -> END
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
    """
    工作流统一执行入口。

    步骤：
    1. 构建 LangGraph 工作流图。
    2. 准备初始状态。
    3. 执行状态机。
    4. 将最终状态收敛为 WorkflowRunResult 返回给 FastAPI 层。
    """
    app = build_workflow_graph()

    initial_state: WorkflowState = {
        "request": request,
        "task": None,
        "trace": [],
        "gen_output": None,
        "verify_output": None,
        "task_paths": None,
        "user_task_spec_path": None,
        "origin_input_path": None,
        "max_iterations": request.max_iterations,
        "final_stage": "unknown",
        "success": False,
        "error": None,
    }

    try:
        final_state = app.invoke(initial_state)
    except Exception as exc:
        logging.getLogger(__name__).exception("Workflow execution failed")
        return WorkflowRunResult(
            success=False,
            final_stage="workflow_error",
            trace=[WorkflowTraceStep(node="workflow", status="error", detail=str(exc))],
        )
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