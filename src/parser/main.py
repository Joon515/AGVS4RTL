from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.common.models import ApiResponse


class HealthStatus(BaseModel):
    service: str = Field(..., description="服务名称")
    state: str = Field(..., description="探活状态")
    detail: str = Field(..., description="探活补充信息")


app = FastAPI(
    title="AGVS4RTL Parser Service",
    version="0.1.0",
    description="对外统一入口，负责任务接收、解析与编排。",
)


@app.get("/health", response_model=ApiResponse[HealthStatus])
async def health_check() -> ApiResponse[HealthStatus]:
    return ApiResponse(
        status="success",
        message="parser service is ready",
        data=HealthStatus(
            service="parser",
            state="ready",
            detail="external ingress is available",
        ),
    )


@app.get("/", response_model=ApiResponse[HealthStatus])
async def root() -> ApiResponse[HealthStatus]:
    return ApiResponse(
        status="success",
        message="parser ingress is online",
        data=HealthStatus(
            service="parser",
            state="ready",
            detail="submit tasks through parser only",
        ),
    )