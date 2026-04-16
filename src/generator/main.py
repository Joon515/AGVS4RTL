from fastapi import FastAPI
from pydantic import BaseModel, Field
import logging

# 注意：
# 请确认你项目中的真实文件名。
# 如果实际路径是 src/common/model.py，请将下面导入改为：
# from src.common.model import ApiResponse, GenNodeOutput, WorkTaskPayload
from src.common.models import ApiResponse, GenNodeOutput, WorkTaskPayload
from src.generator.workflow import run_gen_workflow


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
    title="AGVS4RTL Generator Service",
    version="0.1.0",
    description="内部生成服务，负责从结构化规约到 RTL 产物生成。",
)


@app.get("/health", response_model=ApiResponse[HealthStatus])
async def health_check() -> ApiResponse[HealthStatus]:
    """
    健康检查接口。

    用于容器探活与内部服务可用性检测。
    """
    return ApiResponse(
        status="success",
        message="generator service is ready",
        data=HealthStatus(
            service="generator",
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
        message="generator service is online",
        data=HealthStatus(
            service="generator",
            state="ready",
            detail="intended for internal container calls",
        ),
    )


@app.post("/v1/generate", response_model=ApiResponse[GenNodeOutput])
async def stateless_generate(payload: WorkTaskPayload) -> ApiResponse[GenNodeOutput]:
    """
    生成服务主入口。

    输入：
    - WorkTaskPayload：由 Parser/Orchestrator 下发的轻量任务载荷，
      包含 task_id、iteration、intent、top_module、spec_file_path、shared_task_dir 等信息。

    输出：
    - ApiResponse[GenNodeOutput]：
      返回 SpecReg 文件路径、RTL 文件路径以及简要摘要。

    说明：
    - 当前接口为同步阻塞式执行。
    - 服务本身不返回大段代码文本，而是将产物落盘到 SharedWorkspace 后返回路径。
    """
    try:
        logger.info(
            "收到生成请求: task_id=%s, iteration=%s, top_module=%s, intent=%s",
            payload.task_id,
            payload.iteration,
            payload.top_module,
            payload.intent,
        )

        gen_output = run_gen_workflow(payload)

        logger.info(
            "生成完成: task_id=%s, iteration=%s, rtl_path=%s",
            payload.task_id,
            payload.iteration,
            gen_output.rtl_path,
        )

        return ApiResponse(
            status="success",
            message="stateless generation completed via workflow",
            data=gen_output,
        )

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "生成工作流执行失败: task_id=%s, iteration=%s, error=%s",
            payload.task_id,
            payload.iteration,
            exc,
            exc_info=True,
        )
        return ApiResponse(
            status="error",
            message=f"generator workflow failed: {exc}",
            data=None,
        )