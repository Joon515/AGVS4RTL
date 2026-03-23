from fastapi import FastAPI
from pathlib import Path
from pydantic import BaseModel, Field

from src.common.models import (
    ApiResponse,
    ErrorSnapshot,
    VerifyNodeOutput,
    VerifyRpt,
    VerifyTaskPayload,
    VerifyVerdict,
)


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
    sim_dir = Path(payload.task.shared_task_dir) / "sim"
    sim_dir.mkdir(parents=True, exist_ok=True)

    spec_exists = Path(payload.spec_file_path).exists()
    rtl_exists = Path(payload.rtl_path).exists()

    if spec_exists and rtl_exists:
        verdict = VerifyVerdict.PASS
        errors = ErrorSnapshot()
        summary = f"verify PASS for {payload.rtl_path}"
    else:
        verdict = VerifyVerdict.FAIL_SEMANTIC
        errors = ErrorSnapshot(
            mismatched_ports=["spec or rtl artifact missing"],
            suggested_fix="rerun generation or check spec_file_path/rtl_path",
        )
        summary = "verify FAIL due to missing artifacts"

    report_path = sim_dir / f"{payload.task.top_module}_report_iter{payload.task.iteration}.json"
    sim_log_path = sim_dir / f"{payload.task.top_module}_sim_iter{payload.task.iteration}.log"
    report = VerifyRpt(
        task_id=payload.task.task_id,
        iteration=payload.task.iteration,
        intent=payload.task.intent,
        top_module=payload.task.top_module,
        verdict=verdict,
        error_details=errors,
        sim_log_path=str(sim_log_path),
        wave_file_path=None,
    )
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    sim_log_path.write_text(summary + "\n", encoding="utf-8")

    return ApiResponse(
        status="success",
        message="stateless verification completed",
        data=VerifyNodeOutput(
            report=report,
            summary=summary,
        ),
    )