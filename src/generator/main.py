from fastapi import FastAPI
from pathlib import Path
from pydantic import BaseModel, Field

from src.common.models import (
    ApiResponse,
    ClockResetDef,
    GenNodeOutput,
    NodeType,
    PortDef,
    PortDirection,
    ProtocolGroup,
    ResetType,
    RtlEdge,
    RtlNode,
    SpecReg,
    WorkTaskPayload,
)
from src.generator.workflow import run_gen_workflow


class HealthStatus(BaseModel):
    service: str = Field(..., description="服务名称")
    state: str = Field(..., description="探活状态")
    detail: str = Field(..., description="探活补充信息")


app = FastAPI(
    title="AGVS4RTL Generator Service",
    version="0.1.0",
    description="内部生成服务，负责从规格到 RTL 产物生成。",
)


@app.get("/health", response_model=ApiResponse[HealthStatus])
async def health_check() -> ApiResponse[HealthStatus]:
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
    try:
        # 将核心生成流转交给基于 LangGraph 的 workflow
        gen_output = run_gen_workflow(payload)
        return ApiResponse(
            status="success",
            message="stateless generation completed via workflow",
            data=gen_output,
        )
    except Exception as exc:  # noqa: BLE001
        return ApiResponse(
            status="error",
            message=f"generator workflow failed: {exc}",
            data=None,
        )