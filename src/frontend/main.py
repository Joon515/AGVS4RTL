import logging
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.common.models import (
    ApiResponse,
    HealthStatus,
    ServicesHealthResponse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AGVS4RTL Web Console",
    version="0.1.0",
    description="Browser-based management interface for AGVS4RTL multi-agent RTL system.",
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.cache_size = 0  # workaround Python 3.13 + Jinja2 cache_key dict issue

PARSER_URL = os.getenv("PARSER_URL", "http://parser:8000")


def _parser_client() -> httpx.Client:
    return httpx.Client(base_url=PARSER_URL, timeout=600.0)


# ── Routes ────────────────────────────────────────────────────────────


@app.get("/health", response_model=ApiResponse[HealthStatus])
async def health_check():
    logger.info("GET /health")
    try:
        with _parser_client() as client:
            resp = client.get("/health", timeout=10.0)
            resp.raise_for_status()
        parser_ok = True
    except Exception:
        parser_ok = False

    state = "ready" if parser_ok else "degraded"
    detail = "OK" if parser_ok else "Parser unreachable"
    return ApiResponse(
        status="success",
        message="frontend service is ready",
        data=HealthStatus(service="frontend", state=state, detail=detail),
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/tasks", response_class=HTMLResponse)
async def task_history(request: Request, page: int = 1):
    tasks_data: list = []
    error_msg: str | None = None
    try:
        with _parser_client() as client:
            resp = client.get(f"/v1/tasks?page={page}&per_page=20", timeout=30.0)
            if resp.status_code == 200:
                body = resp.json()
                if body.get("status") == "success" and body.get("data"):
                    tasks_data = body["data"].get("tasks", [])
    except Exception as exc:
        logger.error("Failed to fetch tasks: %s", exc)
        error_msg = f"Parser unreachable: {exc}"

    return templates.TemplateResponse(
        request,
        "tasks.html",
        {
            "tasks": tasks_data,
            "error_msg": error_msg,
        },
    )


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail(request: Request, task_id: str):
    task_data: dict | None = None
    error_msg: str | None = None
    try:
        with _parser_client() as client:
            resp = client.get(f"/v1/tasks/{task_id}", timeout=30.0)
            if resp.status_code == 200:
                body = resp.json()
                if body.get("status") == "success":
                    task_data = body.get("data")
                else:
                    error_msg = body.get("message", "Task not found")
    except Exception as exc:
        logger.error("Failed to fetch task %s: %s", task_id, exc)
        error_msg = f"Parser unreachable: {exc}"

    return templates.TemplateResponse(
        request,
        "task_detail.html",
        {
            "task": task_data,
            "task_id": task_id,
            "error_msg": error_msg,
        },
    )


@app.get("/tasks/{task_id}/status-fragment", response_class=HTMLResponse)
async def task_status_fragment(request: Request, task_id: str):
    """Return status HTML fragment for HTMX polling (every 2s)."""
    status = None
    try:
        with _parser_client() as client:
            resp = client.get(f"/v1/tasks/{task_id}/status", timeout=10.0)
            if resp.status_code == 200:
                body = resp.json()
                if body.get("status") == "success":
                    status = body.get("data")
    except Exception:
        pass
    return templates.TemplateResponse("_status_fragment.html", {
        "request": request,
        "status": status,
    })


@app.get("/services", response_class=HTMLResponse)
async def service_health(request: Request):
    services_data: list = []
    error_msg: str | None = None
    try:
        with _parser_client() as client:
            resp = client.get("/v1/services/health", timeout=30.0)
            if resp.status_code == 200:
                body = resp.json()
                if body.get("status") == "success":
                    services_data = body.get("data", {}).get("services", [])
    except Exception as exc:
        logger.error("Failed to fetch service health: %s", exc)
        error_msg = f"Parser unreachable: {exc}"

    return templates.TemplateResponse(
        request,
        "services.html",
        {
            "services": services_data,
            "error_msg": error_msg,
        },
    )


@app.get("/services/fragment", response_class=HTMLResponse)
async def services_fragment(request: Request):
    """Return services HTML fragment for HTMX polling (every 10s)."""
    services_data: list = []
    try:
        with _parser_client() as client:
            resp = client.get("/v1/services/health", timeout=30.0)
            if resp.status_code == 200:
                body = resp.json()
                if body.get("status") == "success":
                    services_data = body.get("data", {}).get("services", [])
    except Exception:
        pass
    return templates.TemplateResponse("_services_fragment.html", {
        "request": request,
        "services": services_data,
    })


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    env_vars: dict = {}
    try:
        env_path = Path("/app/.env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()
    except Exception as exc:
        logger.error("Failed to read .env: %s", exc)

    return templates.TemplateResponse(
        request,
        "config.html",
        {
            "env_vars": env_vars,
        },
    )


@app.post("/config/save")
async def config_save(
    request: Request,
    agvs4rtl_llm_enabled: str = Form(default="false"),
    agvs4rtl_llm_base_url: str = Form(default=""),
    agvs4rtl_llm_api_key: str = Form(default=""),
    agvs4rtl_llm_model: str = Form(default=""),
    agvs4rtl_llm_profile: str = Form(default="default"),
    verify_service_timeout_seconds: str = Form(default="240"),
    gen_service_timeout_seconds: str = Form(default="600"),
    agvs4rtl_llm_timeout_seconds: str = Form(default="300"),
):
    existing: dict = {}
    try:
        env_path = Path("/app/.env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    existing[k.strip()] = v.strip()

        updates = {
            "AGVS4RTL_LLM_ENABLED": agvs4rtl_llm_enabled,
            "AGVS4RTL_LLM_BASE_URL": agvs4rtl_llm_base_url,
            "AGVS4RTL_LLM_MODEL": agvs4rtl_llm_model,
            "AGVS4RTL_LLM_PROFILE": agvs4rtl_llm_profile,
            "VERIFY_SERVICE_TIMEOUT_SECONDS": verify_service_timeout_seconds,
            "GEN_SERVICE_TIMEOUT_SECONDS": gen_service_timeout_seconds,
            "AGVS4RTL_LLM_TIMEOUT_SECONDS": agvs4rtl_llm_timeout_seconds,
        }
        if agvs4rtl_llm_api_key and agvs4rtl_llm_api_key != "••••••••":
            updates["AGVS4RTL_LLM_API_KEY"] = agvs4rtl_llm_api_key

        existing.update(updates)

        tmp_path = env_path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            f.write("# AGVS4RTL Configuration\n")
            f.write("# Updated via Web Console\n\n")
            for k, v in existing.items():
                f.write(f"{k}={v}\n")
        tmp_path.rename(env_path)

        logger.info("Configuration saved successfully")
        return HTMLResponse(
            '<div id="config-result" class="flash-success">'
            "Configuration saved. Restart services for changes to take effect."
            "</div>"
        )
    except Exception as exc:
        logger.error("Failed to save config: %s", exc, exc_info=True)
        return HTMLResponse(
            '<div id="config-result" class="flash-error">'
            f"Failed to save: {exc}"
            "</div>"
        )


@app.post("/tasks/submit")
async def submit_task(
    request: Request,
    top_module: str = Form(...),
    raw_input_text: str = Form(...),
    max_iterations: int = Form(default=2),
    intent: str = Form(default=""),
    llm_enabled: str = Form(default="false"),
    llm_model: str = Form(default=""),
):
    try:
        payload: dict = {
            "top_module": top_module,
            "raw_input_text": raw_input_text,
            "max_iterations": max_iterations,
            "output_root": "/app/Output",
            "shared_workspace_root": "/app/shared_workspace",
        }
        if intent:
            payload["intent"] = intent

        if llm_enabled == "true" and llm_model:
            payload["llm"] = {
                "enabled": True,
                "model": llm_model,
                "base_url": os.getenv("AGVS4RTL_LLM_BASE_URL", ""),
                "api_key": os.getenv("AGVS4RTL_LLM_API_KEY", ""),
                "profile": os.getenv("AGVS4RTL_LLM_PROFILE", "default"),
            }

        with _parser_client() as client:
            resp = client.post("/v1/workflow/submit", json=payload, timeout=10.0)
            if resp.status_code == 200:
                body = resp.json()
                if body.get("status") == "success":
                    task_id = body.get("data", {}).get("task_id", "unknown")
                    snippet = (
                        '<div id="result" class="flash-success">'
                        f"<strong>Task {task_id} submitted!</strong><br>"
                        "Redirecting to task status page&hellip;"
                        "</div>"
                    )
                    return HTMLResponse(
                        content=snippet,
                        headers={"HX-Redirect": f"/tasks/{task_id}"},
                    )
        return HTMLResponse(
            '<div id="result" class="flash-error">'
            "Submission failed. Check Parser logs."
            "</div>"
        )
    except Exception as exc:
        logger.error("Task submission failed: %s", exc, exc_info=True)
        return HTMLResponse(
            f'<div id="result" class="flash-error">Error: {exc}</div>'
        )


STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
