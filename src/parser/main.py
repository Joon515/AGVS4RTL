from fastapi import FastAPI, Query
import asyncio
import logging
import json
from datetime import datetime, timezone
import os
from pathlib import Path

import httpx

from src.common.models import (
    ApiResponse,
    generate_global_task_id,
    HealthStatus,
    WorkflowRunRequest,
    WorkflowRunResult,
    TaskListItem,
    TaskListResponse,
    TaskDetailResponse,
    TaskStatusResponse,
    ServiceHealthItem,
    ServicesHealthResponse,
)
from src.parser.workflow import run_workflow, build_task_paths, _ensure_task_directories


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AGVS4RTL Parser Service",
    version="0.1.0",
    description="对外统一入口，负责任务接收、解析与编排。",
)


@app.get("/health", response_model=ApiResponse[HealthStatus])
async def health_check() -> ApiResponse[HealthStatus]:
    """
    健康检查接口。

    用于容器探活、服务编排探测以及外部调用方快速确认 Parser 服务是否已就绪。
    """
    return ApiResponse(
        status="success",
        message="parser service is ready",
        data=HealthStatus(
            service="parser",
            state="ready",
            detail="外部入口可用",
        ),
    )


@app.get("/", response_model=ApiResponse[HealthStatus])
async def root() -> ApiResponse[HealthStatus]:
    """
    根路径接口。

    提供服务基础信息，引导调用方通过标准工作流入口提交请求。
    """
    return ApiResponse(
        status="success",
        message="parser ingress is online",
        data=HealthStatus(
            service="parser",
            state="ready",
            detail="请通过 Parser 服务提交任务请求",
        ),
    )


@app.post("/v1/workflow/run", response_model=ApiResponse[WorkflowRunResult])
async def run_workflow_api(payload: WorkflowRunRequest) -> ApiResponse[WorkflowRunResult]:
    """
    工作流主入口。

    输入：
    - WorkflowRunRequest：包含顶层模块名、原始输入、输出目录、最大重试轮次等信息。

    输出：
    - ApiResponse[WorkflowRunResult]：返回任务执行结果、执行轨迹以及最终产物摘要。

    说明：
    - 当前实现为同步阻塞式工作流执行。
    - 若后续任务耗时显著增长，可升级为异步任务队列/后台任务模式。
    """
    try:
        logger.info(
            "收到工作流请求: top_module=%s, intent=%s, max_iterations=%s, output_root=%s",
            payload.top_module,
            payload.intent,
            payload.max_iterations,
            payload.output_root,
        )

        result = run_workflow(payload)

        logger.info(
            "工作流执行完成: task_id=%s, success=%s, final_stage=%s",
            result.task_id,
            result.success,
            result.final_stage,
        )

        return ApiResponse(
            status="success",
            message="workflow completed",
            data=result,
        )

    except Exception as exc:  # noqa: BLE001
        logger.error("工作流执行失败: %s", exc, exc_info=True)
        return ApiResponse(
            status="error",
            message=f"workflow failed: {exc}",
            data=None,
        )


def _run_workflow_with_error_handler(payload: WorkflowRunRequest, task_paths) -> None:
    """Wrapper that runs workflow in background and handles crashes by writing error.json."""
    try:
        run_workflow(payload)
    except Exception as exc:
        logger.exception("Background workflow crashed: task_id=%s", payload.task_id)
        error_info = {
            "error": str(exc),
            "stage": "crashed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        error_path = Path(task_paths.output_task_dir) / "error.json"
        error_path.write_text(json.dumps(error_info, indent=2), encoding="utf-8")


@app.post("/v1/workflow/submit", response_model=ApiResponse[dict])
async def submit_workflow_api(payload: WorkflowRunRequest) -> ApiResponse[dict]:
    """
    工作流异步提交入口。

    输入：
    - WorkflowRunRequest：包含顶层模块名、原始输入、输出目录、最大重试轮次等信息。

    输出：
    - ApiResponse[dict]：立即返回 task_id，工作流在后台异步执行。

    说明：
    - 该接口非阻塞，立即返回 task_id。
    - 调用方可通过 GET /v1/tasks/{task_id} 和 GET /v1/tasks/{task_id}/status 查询任务状态。
    """
    try:
        task_id = generate_global_task_id()

        logger.info(
            "收到工作流异步提交请求: top_module=%s, intent=%s, max_iterations=%s, output_root=%s, task_id=%s",
            payload.top_module,
            payload.intent,
            payload.max_iterations,
            payload.output_root,
            task_id,
        )

        payload.task_id = task_id

        # Pre-create task directory so GET endpoints find it immediately
        task_paths = build_task_paths(
            task_id=task_id,
            output_root=payload.output_root,
            shared_workspace_root=payload.shared_workspace_root,
        )
        _ensure_task_directories(task_paths)

        # Write placeholder UserTaskSpec so the frontend task detail page renders immediately
        placeholder_spec = {
            "task_id": task_id,
            "iteration": 0,
            "intent": str(payload.intent) if payload.intent else "unknown",
            "top_module": payload.top_module,
            "created_at": "pending",
            "source_stage": None,
            "prompt_workspace_path": "",
            "refined_requirements": payload.refined_requirements or [],
            "workspace_dir": "",
            "external_source_path": None,
            "external_target_path": "",
            "target_protocol": None,
            "design_rules": [],
        }
        Path(task_paths.user_task_spec_path).write_text(
            json.dumps(placeholder_spec, indent=2),
            encoding="utf-8",
        )

        asyncio.create_task(asyncio.to_thread(_run_workflow_with_error_handler, payload, task_paths))

        logger.info("工作流已提交至后台: task_id=%s", task_id)

        return ApiResponse(
            status="success",
            message="task submitted",
            data={"task_id": task_id},
        )

    except Exception as exc:  # noqa: BLE001
        logger.error("工作流提交失败: %s", exc, exc_info=True)
        return ApiResponse(
            status="error",
            message=f"task submission failed: {exc}",
            data=None,
        )


# ---------------------------------------------------------------------------
# Task management endpoints (for frontend Web UI)
# ---------------------------------------------------------------------------

_OUTPUT_ROOT = os.getenv("OUTPUT_ROOT", "/app/Output")
_SHARED_WS_ROOT = os.getenv("SHARED_WORKSPACE_ROOT", "/app/shared_workspace")


def _task_final_stage(output_dir: Path) -> str | None:
    result_ws = output_dir / "Result" / "shared_workspace"
    archive_dir = output_dir / "Archive"
    if result_ws.exists():
        return "archive_success"
    if archive_dir.exists():
        return "archive_failed"
    error_path = output_dir / "error.json"
    if error_path.exists():
        return "crashed"
    return None


def _task_success(output_dir: Path) -> bool | None:
    result_ws = output_dir / "Result" / "shared_workspace"
    archive_dir = output_dir / "Archive"
    if result_ws.exists():
        return True
    if archive_dir.exists():
        return False
    error_path = output_dir / "error.json"
    if error_path.exists():
        return False
    return None


def _iter_count(task_dir: Path) -> int:
    best = 0
    for base in (task_dir / "Result" / "shared_workspace", task_dir):
        specs_dir = base / "specs"
        if not specs_dir.is_dir():
            continue
        for sp in specs_dir.glob("SpecReg_iter*.json"):
            try:
                n = int(sp.name.replace("SpecReg_iter", "").replace(".json", ""))
            except ValueError:
                continue
            if n > best:
                best = n
    return best


# ---------------------------------------------------------------------------
# GET /v1/tasks
# ---------------------------------------------------------------------------


@app.get("/v1/tasks", response_model=ApiResponse[TaskListResponse])
async def list_tasks(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[TaskListResponse]:
    """List all tasks with pagination (newest first)."""
    logger.info("GET /v1/tasks page=%s per_page=%s", page, per_page)
    try:
        output_root = Path(_OUTPUT_ROOT)
        items: list[dict] = []
        for task_dir in sorted(output_root.glob("TASK_*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if not task_dir.is_dir():
                continue
            try:
                usp_path = task_dir / "UserTaskSpec.json"
                if not usp_path.exists():
                    logger.warning("Skipping task dir without UserTaskSpec: %s", task_dir.name)
                    continue
                data = json.loads(usp_path.read_text(encoding="utf-8"))
                created_at = data.get("created_at", "")
                if isinstance(created_at, dict):
                    created_at = str(created_at)
                items.append({
                    "task_id": task_dir.name,
                    "top_module": data.get("top_module", "unknown"),
                    "intent": data.get("intent"),
                    "created_at": created_at,
                    "_mtime": task_dir.stat().st_mtime,
                })
            except Exception:
                logger.warning("Skipping corrupt task dir: %s", task_dir.name, exc_info=True)
                continue

        total = len(items)
        start = (page - 1) * per_page
        end = start + per_page
        page_items = items[start:end]

        tasks: list[TaskListItem] = []
        for it in page_items:
            task_output = output_root / it["task_id"]
            tasks.append(TaskListItem(
                task_id=it["task_id"],
                top_module=it["top_module"],
                intent=it.get("intent"),
                created_at=it["created_at"],
                final_stage=_task_final_stage(task_output),
                success=_task_success(task_output),
            ))

        return ApiResponse(
            status="success",
            message=f"returned {len(tasks)} tasks",
            data=TaskListResponse(tasks=tasks, total=total, page=page, per_page=per_page),
        )
    except Exception as exc:
        logger.error("Failed to list tasks: %s", exc, exc_info=True)
        return ApiResponse(status="error", message=f"failed to list tasks: {exc}", data=None)


# ---------------------------------------------------------------------------
# GET /v1/tasks/{task_id}
# ---------------------------------------------------------------------------


@app.get("/v1/tasks/{task_id}", response_model=ApiResponse[TaskDetailResponse])
async def get_task_detail(task_id: str) -> ApiResponse[TaskDetailResponse]:
    """Get single task detail including artifact paths."""
    logger.info("GET /v1/tasks/%s", task_id)
    try:
        output_dir = Path(_OUTPUT_ROOT) / task_id
        usp_path = output_dir / "UserTaskSpec.json"
        if not usp_path.exists():
            return ApiResponse(status="error", message="task not found", data=None)

        data = json.loads(usp_path.read_text(encoding="utf-8"))
        created_at = data.get("created_at", "")
        if isinstance(created_at, dict):
            created_at = str(created_at)

        max_iter = _iter_count(output_dir) + 1

        artifact_paths: dict[str, str | None] = {
            "spec_reg": None,
            "rtl": None,
            "verify_rpt": None,
            "testbench": None,
            "makefile": None,
        }
        result_ws = output_dir / "Result" / "shared_workspace"
        if result_ws.exists():
            specs_dir = result_ws / "specs"
            if specs_dir.is_dir():
                for sp in sorted(specs_dir.glob("SpecReg_iter*.json"), reverse=True):
                    artifact_paths["spec_reg"] = str(sp)
                    break
            rtl_dir = result_ws / "rtl"
            if rtl_dir.is_dir():
                for vf in rtl_dir.glob("*.v"):
                    artifact_paths["rtl"] = str(vf)
                    break
            sim_dir = result_ws / "sim"
            if sim_dir.is_dir():
                for rp in sorted(sim_dir.glob("VerifyRpt_iter*.json"), reverse=True):
                    artifact_paths["verify_rpt"] = str(rp)
                    break
                tb = sim_dir / "testbench.py"
                if tb.exists():
                    artifact_paths["testbench"] = str(tb)
                else:
                    for py in sim_dir.glob("test_*.py"):
                        artifact_paths["testbench"] = str(py)
                        break
                mf = sim_dir / "Makefile"
                if mf.exists():
                    artifact_paths["makefile"] = str(mf)

        trace_summary: list[str] = []
        if result_ws.exists():
            sim_dir = result_ws / "sim"
            if sim_dir.is_dir():
                for rp in sorted(sim_dir.glob("VerifyRpt_iter*.json")):
                    try:
                        rpt = json.loads(rp.read_text(encoding="utf-8"))
                        verdict = rpt.get("verdict", "unknown")
                        trace_summary.append(f"Iter {rp.name}: verdict={verdict}")
                    except Exception:
                        trace_summary.append(f"Iter {rp.name}: (unreadable)")

        error_path = output_dir / "error.json"
        if error_path.exists():
            try:
                error_data = json.loads(error_path.read_text(encoding="utf-8"))
                error_msg = error_data.get("error", "unknown crash")
                trace_summary.insert(0, f"❌ CRASH: {error_msg}")
            except Exception:
                trace_summary.insert(0, "❌ CRASH: (could not read error details)")

        return ApiResponse(
            status="success",
            message="task detail returned",
            data=TaskDetailResponse(
                task_id=task_id,
                top_module=data.get("top_module", "unknown"),
                intent=data.get("intent"),
                created_at=created_at,
                final_stage=_task_final_stage(output_dir),
                success=_task_success(output_dir),
                max_iterations=max(max_iter, 1),
                artifact_paths=artifact_paths,
                trace_summary=trace_summary,
            ),
        )
    except Exception as exc:
        logger.error("Failed to get task detail for %s: %s", task_id, exc, exc_info=True)
        return ApiResponse(status="error", message=f"failed to get task detail: {exc}", data=None)


# ---------------------------------------------------------------------------
# GET /v1/tasks/{task_id}/status
# ---------------------------------------------------------------------------


def _resolve_workspace(task_id: str) -> Path | None:
    """Find the active or archived workspace for a task.

    Priority:
    1. shared_workspace/{task_id} (active task)
    2. Output/{task_id}/Result/shared_workspace (completed)
    3. Output/{task_id}/Archive (failed)
    """
    active = Path(_SHARED_WS_ROOT) / task_id
    if active.is_dir():
        return active
    output_dir = Path(_OUTPUT_ROOT) / task_id
    result_ws = output_dir / "Result" / "shared_workspace"
    if result_ws.is_dir():
        return result_ws
    archive_ws = output_dir / "Archive" / "shared_workspace"
    if archive_ws.is_dir():
        return archive_ws
    if output_dir.is_dir():
        return output_dir
    return None


def _task_status_from_ws(workspace: Path, task_id: str) -> TaskStatusResponse:
    """Infer task status from workspace directory contents."""
    # Check for crash error.json first
    error_path = Path(_OUTPUT_ROOT) / task_id / "error.json"
    if error_path.exists():
        try:
            error_data = json.loads(error_path.read_text(encoding="utf-8"))
        except Exception:
            error_data = {"error": "unknown crash", "stage": "crashed"}
        return TaskStatusResponse(
            task_id=task_id,
            stage="failed",
            iteration=0,
            verdict=error_data.get("error", "unknown crash"),
            progress_pct=100,
        )

    specs_dir = workspace / "specs"
    rtl_dir = workspace / "rtl"
    sim_dir = workspace / "sim"

    has_spec = specs_dir.is_dir() and any(specs_dir.glob("SpecReg_iter*.json"))
    has_rtl = rtl_dir.is_dir() and any(rtl_dir.glob("*.v"))
    has_verify_rpt = sim_dir.is_dir() and any(sim_dir.glob("VerifyRpt_iter*.json"))

    iteration = 0
    if specs_dir.is_dir():
        for sp in specs_dir.glob("SpecReg_iter*.json"):
            try:
                n = int(sp.name.replace("SpecReg_iter", "").replace(".json", ""))
            except ValueError:
                continue
            if n > iteration:
                iteration = n

    if not has_spec:
        return TaskStatusResponse(
            task_id=task_id,
            stage="initializing",
            iteration=0,
            verdict=None,
            progress_pct=5,
        )

    if not has_rtl:
        return TaskStatusResponse(
            task_id=task_id,
            stage="generating",
            iteration=iteration,
            verdict=None,
            progress_pct=30,
        )

    if not has_verify_rpt:
        return TaskStatusResponse(
            task_id=task_id,
            stage="verifying",
            iteration=iteration,
            verdict=None,
            progress_pct=60,
        )

    verify_rpts = sorted(sim_dir.glob("VerifyRpt_iter*.json"), reverse=True)
    if not verify_rpts:
        return TaskStatusResponse(
            task_id=task_id,
            stage="verifying",
            iteration=iteration,
            verdict=None,
            progress_pct=60,
        )

    latest_rpt = verify_rpts[0]
    try:
        rpt_data = json.loads(latest_rpt.read_text(encoding="utf-8"))
        verdict = rpt_data.get("verdict", "unknown")
    except Exception:
        logger.warning("Corrupt VerifyRpt for %s: %s", task_id, latest_rpt.name)
        verdict = "unknown"

    if verdict == "PASS":
        return TaskStatusResponse(
            task_id=task_id,
            stage="completed",
            iteration=iteration,
            verdict=verdict,
            progress_pct=100,
        )

    if specs_dir.is_dir():
        retry_spec = specs_dir / f"SpecReg_iter{iteration + 1}.json"
        if retry_spec.exists():
            return TaskStatusResponse(
                task_id=task_id,
                stage="retrying",
                iteration=iteration + 1,
                verdict=verdict,
                progress_pct=60,
            )

    return TaskStatusResponse(
        task_id=task_id,
        stage="failed",
        iteration=iteration,
        verdict=verdict,
        progress_pct=100,
    )


@app.get("/v1/tasks/{task_id}/status", response_model=ApiResponse[TaskStatusResponse])
async def get_task_status(task_id: str) -> ApiResponse[TaskStatusResponse]:
    """Poll task real-time status."""
    logger.info("GET /v1/tasks/%s/status", task_id)
    try:
        workspace = _resolve_workspace(task_id)
        if workspace is None:
            return ApiResponse(status="error", message="task not found", data=None)
        status = _task_status_from_ws(workspace, task_id)
        return ApiResponse(status="success", message="status retrieved", data=status)
    except Exception as exc:
        logger.error("Failed to get task status for %s: %s", task_id, exc, exc_info=True)
        return ApiResponse(status="error", message=f"failed to get task status: {exc}", data=None)


# ---------------------------------------------------------------------------
# GET /v1/services/health
# ---------------------------------------------------------------------------


def _check_service_health(service: str, url: str) -> ServiceHealthItem:
    """Ping a service's /health endpoint and return its status."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, timeout=5.0)
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data", {})
            state = data.get("state", "ready") if isinstance(data, dict) else "ready"
            detail = data.get("detail", "OK") if isinstance(data, dict) else "OK"
            return ServiceHealthItem(
                service=service,
                state=state if state in ("ready", "degraded") else "ready",
                detail=str(detail),
                reachable=True,
            )
    except Exception as exc:
        return ServiceHealthItem(
            service=service,
            state="unreachable",
            detail=str(exc),
            reachable=False,
        )


@app.get("/v1/services/health", response_model=ApiResponse[ServicesHealthResponse])
async def get_services_health() -> ApiResponse[ServicesHealthResponse]:
    """Aggregate health of parser + gen + verify."""
    logger.info("GET /v1/services/health")
    try:
        gen_url = os.getenv("GEN_SERVICE_URL", "http://gen:8000")
        verify_url = os.getenv("VERIFY_SERVICE_URL", "http://verify:8000")

        services = [
            ServiceHealthItem(
                service="parser",
                state="ready",
                detail="OK",
                reachable=True,
            ),
            _check_service_health("generator", f"{gen_url}/health"),
            _check_service_health("verify", f"{verify_url}/health"),
        ]

        all_healthy = all(s.reachable for s in services)

        return ApiResponse(
            status="success",
            message="health aggregated",
            data=ServicesHealthResponse(services=services, all_healthy=all_healthy),
        )
    except Exception as exc:
        logger.error("Failed to aggregate health: %s", exc, exc_info=True)
        return ApiResponse(status="error", message=f"failed to aggregate health: {exc}", data=None)