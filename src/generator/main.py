from fastapi import FastAPI
from pathlib import Path
from pydantic import BaseModel, Field

from src.common.models import (
    ApiResponse,
    ClockResetDef,
    GenNodeOutput,
    PortDef,
    PortDirection,
    ProtocolGroup,
    ResetType,
    SpecReg,
    WorkTaskPayload,
)


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
    shared_task_dir = Path(payload.shared_task_dir)
    specs_dir = shared_task_dir / "specs"
    rtl_dir = shared_task_dir / "rtl"
    specs_dir.mkdir(parents=True, exist_ok=True)
    rtl_dir.mkdir(parents=True, exist_ok=True)

    spec_reg = SpecReg(
        task_id=payload.task_id,
        iteration=payload.iteration,
        intent=payload.intent,
        top_module=payload.top_module,
        module_description=f"placeholder spec for {payload.top_module}",
        ports=[
            PortDef(name="i_clk", direction=PortDirection.INPUT, width="1", clock_domain="i_clk"),
            PortDef(name="i_rst_n", direction=PortDirection.INPUT, width="1", clock_domain="i_clk"),
            PortDef(name="o_done", direction=PortDirection.OUTPUT, width="1", clock_domain="i_clk"),
        ],
        clock_and_reset=[
            ClockResetDef(clock_name="i_clk", reset_name="i_rst_n", reset_type=ResetType.ASYNC_LOW),
        ],
        protocols=[ProtocolGroup(protocol_type="custom", role="slave", port_mapping={})],
        verification_directives=["run smoke testbench first"],
    )

    spec_file_path = specs_dir / f"SpecReg_iter{payload.iteration}.json"
    spec_file_path.write_text(spec_reg.model_dump_json(indent=2), encoding="utf-8")

    rtl_path = rtl_dir / f"{payload.top_module}.v"
    rtl_path.write_text(
        (
            f"module {payload.top_module}(\n"
            "    input wire i_clk,\n"
            "    input wire i_rst_n,\n"
            "    output reg o_done\n"
            ");\n"
            "always @(posedge i_clk or negedge i_rst_n) begin\n"
            "    if (!i_rst_n) o_done <= 1'b0;\n"
            "    else o_done <= 1'b1;\n"
            "end\n"
            "endmodule\n"
        ),
        encoding="utf-8",
    )

    return ApiResponse(
        status="success",
        message="stateless generation completed",
        data=GenNodeOutput(
            spec_file_path=str(spec_file_path),
            rtl_path=str(rtl_path),
            summary=f"generated SpecReg and RTL for {payload.top_module} (iteration {payload.iteration})",
        ),
    )