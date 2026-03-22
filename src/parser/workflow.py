from __future__ import annotations

import os
from typing import Any, Dict, List, Literal, Optional, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph

from src.common.models import (
    ApiResponse,
    GenNodeOutput,
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
    trace: List[WorkflowTraceStep]
    gen_output: Optional[GenNodeOutput]
    verify_output: Optional[VerifyNodeOutput]
    final_stage: str
    success: bool
    error: Optional[str]


def _append_trace(
    trace: List[WorkflowTraceStep],
    node: str,
    status: Literal["success", "error"],
    detail: str,
) -> List[WorkflowTraceStep]:
    new_trace = list(trace)
    new_trace.append(WorkflowTraceStep(node=node, status=status, detail=detail))
    return new_trace


def parser_prepare_node(state: WorkflowState) -> Dict[str, Any]:
    request = state["request"]
    task = WorkTaskPayload(
        task_id=generate_global_task_id(),
        intent=request.intent,
        top_module=request.top_module,
        refined_requirements=request.refined_requirements,
        workspace_dir=request.workspace_dir,
    )
    trace = _append_trace(state.get("trace", []), "parser_prepare", "success", "parser prepared task payload")
    return {"task": task, "trace": trace}


def gen_stateless_node(state: WorkflowState) -> Dict[str, Any]:
    task = state.get("task")
    if task is None:
        raise ValueError("task payload is missing")

    gen_base_url = os.getenv("GEN_SERVICE_URL", "http://gen:8000")
    endpoint = f"{gen_base_url}/v1/generate"

    with httpx.Client(timeout=15.0) as client:
        response = client.post(endpoint, json=task.model_dump(mode="json"))
        response.raise_for_status()

    response_payload = ApiResponse[GenNodeOutput].model_validate(response.json())
    gen_output = response_payload.data
    if gen_output is None:
        raise ValueError("generator returned empty data")

    trace = _append_trace(state.get("trace", []), "gen_stateless", "success", response_payload.message)
    return {"gen_output": gen_output, "trace": trace}


def verify_stateless_node(state: WorkflowState) -> Dict[str, Any]:
    task = state.get("task")
    gen_output = state.get("gen_output")
    if task is None:
        raise ValueError("task payload is missing")
    if gen_output is None:
        raise ValueError("generator output is missing")

    verify_base_url = os.getenv("VERIFY_SERVICE_URL", "http://verify:8000")
    endpoint = f"{verify_base_url}/v1/verify"

    verify_payload = VerifyTaskPayload(task=task, rtl_path=gen_output.rtl_path)

    with httpx.Client(timeout=20.0) as client:
        response = client.post(endpoint, json=verify_payload.model_dump(mode="json"))
        response.raise_for_status()

    response_payload = ApiResponse[VerifyNodeOutput].model_validate(response.json())
    verify_output = response_payload.data
    if verify_output is None:
        raise ValueError("verify returned empty data")

    trace = _append_trace(state.get("trace", []), "verify_stateless", "success", response_payload.message)
    return {"verify_output": verify_output, "trace": trace}


def route_after_verify(state: WorkflowState) -> Literal["finalize_success", "finalize_failed"]:
    verify_output = state.get("verify_output")
    if verify_output is not None and verify_output.verdict == VerifyVerdict.PASS:
        return "finalize_success"
    return "finalize_failed"


def finalize_success_node(state: WorkflowState) -> Dict[str, Any]:
    trace = _append_trace(state.get("trace", []), "finalize_success", "success", "workflow completed with PASS verdict")
    return {"trace": trace, "final_stage": "finalize_success", "success": True}


def finalize_failed_node(state: WorkflowState) -> Dict[str, Any]:
    trace = _append_trace(state.get("trace", []), "finalize_failed", "error", "workflow completed with non-PASS verdict")
    return {"trace": trace, "final_stage": "finalize_failed", "success": False}


def build_workflow_graph():
    graph = StateGraph(WorkflowState)

    graph.add_node("parser_prepare", parser_prepare_node)
    graph.add_node("gen_stateless", gen_stateless_node)
    graph.add_node("verify_stateless", verify_stateless_node)
    graph.add_node("finalize_success", finalize_success_node)
    graph.add_node("finalize_failed", finalize_failed_node)

    graph.add_edge(START, "parser_prepare")
    graph.add_edge("parser_prepare", "gen_stateless")
    graph.add_edge("gen_stateless", "verify_stateless")
    graph.add_conditional_edges(
        "verify_stateless",
        route_after_verify,
        {
            "finalize_success": "finalize_success",
            "finalize_failed": "finalize_failed",
        },
    )
    graph.add_edge("finalize_success", END)
    graph.add_edge("finalize_failed", END)

    return graph.compile()


def run_workflow(request: WorkflowRunRequest) -> WorkflowRunResult:
    app = build_workflow_graph()
    initial_state: WorkflowState = {
        "request": request,
        "task": None,
        "trace": [],
        "gen_output": None,
        "verify_output": None,
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
