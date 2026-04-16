from fastapi import FastAPI
from pydantic import BaseModel, Field
import logging

from src.common.models import ApiResponse, WorkflowRunRequest, WorkflowRunResult
from src.parser.workflow import run_workflow


class HealthStatus(BaseModel):
    service: str = Field(..., description="服务名称")
    state: str = Field(..., description="探活状态")
    detail: str = Field(..., description="探活补充信息")


# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AGVS4RTL Parser Service",
    version="0.1.0",
    description="对外统一入口，负责任务接收、解析与编排。",
)

@app.get("/health", response_model=ApiResponse[HealthStatus])
async def health_check() -> ApiResponse[HealthStatus]:
    """健康检查接口，用于确认服务是否在线并准备就绪。"""
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
    """根路径接口，提供服务基本信息。"""
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
    执行工作流的主接口。接收 WorkflowRunRequest，触发 LangGraph 工作流并返回结果。
    """
    try:
        result = run_workflow(payload)
        return ApiResponse(
            status="success",
            message="workflow completed",
            data=result,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"工作流执行失败: {exc}", exc_info=True) # 记录详细错误信息和堆栈
        return ApiResponse(
            status="error",
            message=f"workflow failed: {exc}",
            data=None,
        )