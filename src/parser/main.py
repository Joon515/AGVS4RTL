from fastapi import FastAPI
from pydantic import BaseModel, Field
import logging

from src.common.models import ApiResponse, WorkflowRunRequest, WorkflowRunResult
from src.parser.workflow import run_workflow


class HealthStatus(BaseModel):
    """服务探活响应体。"""
    service: str = Field(..., description="服务名称")
    state: str = Field(..., description="探活状态")
    detail: str = Field(..., description="探活补充信息")


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