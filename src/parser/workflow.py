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
    request: WorkflowRunRequest
    task: Optional[WorkTaskPayload]
    trace: Annotated[List[WorkflowTraceStep], operator.add]
    gen_output: Optional[GenNodeOutput]
    verify_output: Optional[VerifyNodeOutput]
    user_task_spec_path: Optional[str]
    origin_input_path: Optional[str]
    output_task_dir: Optional[str]
    shared_task_dir: Optional[str]
    max_iterations: int
    final_stage: str
    success: bool
    error: Optional[str]


def _route_intent(raw_input_text: str) -> IntentCategory:
    normalized = raw_input_text.lower()
    if "fix" in normalized or "修复" in normalized:
        return IntentCategory.FIX_BUG
    if "verify" in normalized or "验证" in normalized:
        return IntentCategory.VERIFY_ONLY
    if "modify" in normalized or "修改" in normalized:
        return IntentCategory.MODIFY_EXISTING
    return IntentCategory.GEN_WITH_TEST


def parser_initialize_node(state: WorkflowState) -> Dict[str, Any]:
    request = state["request"]
    task_id = generate_global_task_id()

    output_task_dir = Path(request.output_root) / task_id
    origin_dir = output_task_dir / "Origin"
    archive_dir = output_task_dir / "Archive"
    result_dir = output_task_dir / "Result"
    shared_task_dir = Path(request.shared_workspace_root) / task_id
    shared_specs_dir = shared_task_dir / "specs"
    shared_rtl_dir = shared_task_dir / "rtl"
    shared_sim_dir = shared_task_dir / "sim"

    for path in [origin_dir, archive_dir, result_dir, shared_specs_dir, shared_rtl_dir, shared_sim_dir]:
        path.mkdir(parents=True, exist_ok=True)

    origin_input_path = origin_dir / request.input_filename
    origin_input_path.write_text(request.raw_input_text or "", encoding="utf-8")

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

    user_task_spec_path = output_task_dir / "UserTaskSpec.json"
    user_task_spec_path.write_text(
        user_task_spec.model_dump_json(indent=2),
        encoding="utf-8",
    )

    shared_user_task_spec_path = shared_specs_dir / "UserTaskSpec.json"
    shared_user_task_spec_path.write_text(
        user_task_spec.model_dump_json(indent=2),
        encoding="utf-8",
    )

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
    task = state.get("task")
    if task is None:
        raise ValueError("task payload is missing")

    gen_base_url = os.getenv("GEN_SERVICE_URL", "http://gen:8000")
    endpoint = f"{gen_base_url}/v1/generate"

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
    task = state.get("task")
    gen_output = state.get("gen_output")
    if task is None:
        raise ValueError("task payload is missing")
    if gen_output is None:
        raise ValueError("generator output is missing")

    verify_base_url = os.getenv("VERIFY_SERVICE_URL", "http://verify:8000")
    endpoint = f"{verify_base_url}/v1/verify"

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
    task = state.get("task")
    verify_output = state.get("verify_output")
    if task is None or verify_output is None:
        return "archive_failed"

    if verify_output.report.verdict == VerifyVerdict.PASS:
        return "archive_success"

    if task.iteration + 1 < state.get("max_iterations", 1):
        return "retry_generation"
    return "archive_failed"


def prepare_retry_node(state: WorkflowState) -> Dict[str, Any]:
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
    output_task_dir = state.get("output_task_dir")
    shared_task_dir = state.get("shared_task_dir")
    if output_task_dir is None or shared_task_dir is None:
        raise ValueError("archive path missing")

    result_dir = Path(output_task_dir) / "Result"
    source = Path(shared_task_dir)
    target = result_dir / "shared_workspace"
    if target.exists():
        shutil.rmtree(target)
    if source.exists():
        shutil.copytree(source, target)
        shutil.rmtree(source)

    trace_step = WorkflowTraceStep(
        node="archive_success", status="success", detail=f"archived artifacts to {target}"
    )
    return {"trace": [trace_step], "final_stage": "archive_success", "success": True}


def archive_failed_node(state: WorkflowState) -> Dict[str, Any]:
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
