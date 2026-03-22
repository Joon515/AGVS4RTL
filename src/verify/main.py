from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.common.models import ApiResponse, VerifyNodeOutput, VerifyTaskPayload, VerifyVerdict


class HealthStatus(BaseModel):
    service: str = Field(..., description="服务名称")
    state: str = Field(..., description="探活状态")
    detail: str = Field(..., description="探活补充信息")


app = FastAPI(
    title="AGVS4RTL Verify Service",
    version="0.1.0",
    description="内部验证服务，负责静态检查与仿真验证。",
)


@app.get("/health", response_model=ApiResponse[HealthStatus])
async def health_check() -> ApiResponse[HealthStatus]:
    return ApiResponse(
        status="success",
        message="verify service is ready",
        data=HealthStatus(
            service="verify",
            state="ready",
            detail="internal verification endpoint is available",
        ),
    )


@app.get("/", response_model=ApiResponse[HealthStatus])
async def root() -> ApiResponse[HealthStatus]:
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
async def stateless_verify(payload: VerifyTaskPayload) -> ApiResponse[VerifyNodeOutput]:
    report_path = f"{payload.task.workspace_dir}/sim/{payload.task.top_module}_report.json"
    return ApiResponse(
        status="success",
        message="stateless verification completed",
        data=VerifyNodeOutput(
            verdict=VerifyVerdict.PASS,
            summary=f"placeholder verify PASS for {payload.rtl_path}",
            report_path=report_path,
        ),
    )