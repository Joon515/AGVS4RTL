from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
import logging

from src.common.models import ApiResponse, LlmRuntimeConfig, VerifyNodeOutput, VerifyTaskPayload
from src.verify.workflow import run_verify_workflow


LLM_HEADER_ENABLED = "X-AGVS4RTL-LLM-Enabled"
LLM_HEADER_BASE_URL = "X-AGVS4RTL-LLM-Base-URL"
LLM_HEADER_API_KEY = "X-AGVS4RTL-LLM-API-Key"
LLM_HEADER_MODEL = "X-AGVS4RTL-LLM-Model"
LLM_HEADER_PROFILE = "X-AGVS4RTL-LLM-Profile"


def _load_llm_config_from_headers(request: Request) -> LlmRuntimeConfig:
    return LlmRuntimeConfig(
        enabled=request.headers.get(LLM_HEADER_ENABLED, "false").lower() == "true",
        base_url=request.headers.get(LLM_HEADER_BASE_URL),
        api_key=request.headers.get(LLM_HEADER_API_KEY),
        model=request.headers.get(LLM_HEADER_MODEL),
        profile=request.headers.get(LLM_HEADER_PROFILE, "default"),
    )


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
    title="AGVS4RTL Verify Service",
    version="0.1.0",
    description="内部验证服务，负责对生成的 SpecReg 与 RTL 执行最小闭环验证。",
)


@app.get("/health", response_model=ApiResponse[HealthStatus])
async def health_check() -> ApiResponse[HealthStatus]:
    """
    健康检查接口。

    用于容器探活与内部服务可用性检测。
    """
    return ApiResponse(
        status="success",
        message="verify service is ready",
        data=HealthStatus(
            service="verify",
            state="ready",
            detail="internal service endpoint is available",
        ),
    )


@app.get("/", response_model=ApiResponse[HealthStatus])
async def root() -> ApiResponse[HealthStatus]:
    """
    根路径接口。

    返回服务基本状态信息，提示当前服务为内部容器调用用途。
    """
    return ApiResponse(
        status="success",
        message="verify service is online",
        data=HealthStatus(
            service="verify",
            state="ready",
            detail="intended for internal container calls",
        ),
    )


@app.post("/v1/verify", response_model=ApiResponse[VerifyNodeOutput])
async def stateless_verify(payload: VerifyTaskPayload, request: Request) -> ApiResponse[VerifyNodeOutput]:
    """
    验证服务主入口。

    输入：
    - VerifyTaskPayload：由 Parser/Orchestrator 下发的轻量验证任务载荷，
      包含原始任务信息、SpecReg 文件路径与 RTL 文件路径。

    输出：
    - ApiResponse[VerifyNodeOutput]：
      返回结构化验证报告 VerifyRpt 以及简要摘要。

    说明：
    - 当前接口为同步阻塞式执行。
    - 服务本身不返回大段日志文本，而是将验证报告和编译日志落盘到 SharedWorkspace 后返回结构化结果。
    """
    try:
        llm_config = _load_llm_config_from_headers(request)
        logger.info(
            "收到验证请求: task_id=%s, iteration=%s, top_module=%s, spec_file_path=%s, rtl_path=%s, llm_enabled=%s, llm_profile=%s, llm_model=%s",
            payload.task.task_id,
            payload.task.iteration,
            payload.task.top_module,
            payload.spec_file_path,
            payload.rtl_path,
            llm_config.enabled,
            llm_config.profile,
            llm_config.model,
        )

        verify_output = run_verify_workflow(payload, llm_config=llm_config)

        logger.info(
            "验证完成: task_id=%s, iteration=%s, verdict=%s",
            payload.task.task_id,
            payload.task.iteration,
            verify_output.report.verdict,
        )

        return ApiResponse(
            status="success",
            message="stateless verification completed via workflow",
            data=verify_output,
        )

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "验证工作流执行失败: task_id=%s, iteration=%s, error=%s",
            payload.task.task_id,
            payload.task.iteration,
            exc,
            exc_info=True,
        )
        return ApiResponse(
            status="error",
            message=f"verify workflow failed: {exc}",
            data=None,
        )