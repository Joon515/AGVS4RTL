"""Pytest configuration and shared fixtures for AGVS4RTL integration tests."""

import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

# ---------------------------------------------------------------------------
# Project root resolution -- DO NOT hardcode absolute paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_WORKSPACE = PROJECT_ROOT / "shared_workspace"
OUTPUT_DIR = PROJECT_ROOT / "Output"

# ---------------------------------------------------------------------------
# Load .env into os.environ so pytest can read LLM config from the host
# ---------------------------------------------------------------------------
_ENV_FILE = PROJECT_ROOT / ".env"
if _ENV_FILE.is_file():
    with _ENV_FILE.open(encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _, _val = _line.partition("=")
            _key = _key.strip()
            _val = _val.strip().strip('"').strip("'")
            if _key and _key not in os.environ:
                os.environ[_key] = _val


# ---------------------------------------------------------------------------
# pytest hooks
# ---------------------------------------------------------------------------
def pytest_configure(config):
    """Register custom markers (supplementing pytest.ini definitions)."""
    config.addinivalue_line(
        "markers",
        "llm: tests requiring real LLM API (skipped when AGVS4RTL_LLM_ENABLED != true)",
    )
    config.addinivalue_line(
        "markers",
        "docker: tests requiring Docker Compose environment",
    )
    config.addinivalue_line(
        "markers",
        "slow: tests taking more than 30 seconds",
    )


def pytest_runtest_setup(item):
    """Skip @pytest.mark.llm tests when AGVS4RTL_LLM_ENABLED is not 'true'."""
    if item.get_closest_marker("llm"):
        enabled = os.environ.get("AGVS4RTL_LLM_ENABLED", "").strip().lower()
        if enabled != "true":
            pytest.skip("LLM tests disabled: set AGVS4RTL_LLM_ENABLED=true to run")


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def docker_services():
    """Start Docker Compose services before the test session and tear them down
    afterwards.

    Idempotent: if services are already running and healthy, skips rebuild.
    Waits for the parser /health endpoint to return 200 before yielding.
    Polls every 2 seconds with a 60-second timeout.
    """
    compose_file = PROJECT_ROOT / "docker-compose.yml"
    if not compose_file.exists():
        raise FileNotFoundError(
            f"docker-compose.yml not found at {compose_file}. "
            "Ensure you are running tests from the project root."
        )

    parser_url = os.environ.get("AGVS4RTL_PARSER_URL", "http://localhost:8001")
    health_url = f"{parser_url.rstrip('/')}/health"
    started_by_us = False

    # Phase 1: check if services are already running
    already_running = False
    try:
        resp = httpx.get(health_url, timeout=5.0)
        if resp.status_code == 200:
            already_running = True
    except (httpx.ConnectError, httpx.TimeoutException):
        pass

    if not already_running:
        # Phase 2: start services (prefer up -d without --build to avoid
        # Docker Hub pulls when images are already cached)
        for attempt, extra_args in enumerate(([], ["--build"])):
            cmd = ["docker", "compose", "up", "-d"] + extra_args
            result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
            if result.returncode == 0:
                started_by_us = True
                break
            if attempt == 0 and "failed to solve" not in result.stderr.lower():
                raise RuntimeError(
                    f"docker compose up failed (exit {result.returncode}):\n"
                    f"stdout: {result.stdout}\nstderr: {result.stderr}"
                )
        else:
            raise RuntimeError(
                f"docker compose up failed (all attempts exhausted):\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )

        # Phase 3: wait for health
        deadline = time.time() + 60
        ready = False
        while time.time() < deadline:
            try:
                resp = httpx.get(health_url, timeout=5.0)
                if resp.status_code == 200:
                    ready = True
                    break
            except (httpx.ConnectError, httpx.TimeoutException):
                pass
            time.sleep(2)

        if not ready:
            if started_by_us:
                subprocess.run(
                    ["docker", "compose", "down"], cwd=PROJECT_ROOT, capture_output=True
                )
            raise RuntimeError(
                "Docker services did not become ready within 60 seconds. "
                f"Parser health endpoint: {health_url}"
            )

    # Phase 4: fix shared workspace permissions (docker creates root-owned dirs)
    # Always run this, whether services were already running or we started them
    subprocess.run(
        ["docker", "compose", "exec", "-T", "parser",
         "chmod", "-R", "777", "/app/shared_workspace", "/app/Output"],
        cwd=PROJECT_ROOT, capture_output=True,
    )

    yield

    # Teardown (only if we started them)
    if started_by_us:
        subprocess.run(
            ["docker", "compose", "down"], cwd=PROJECT_ROOT, capture_output=True
        )


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def cleanup_workspace(docker_services):
    """Clean shared_workspace and Output after each test.

    Depends on docker_services to ensure containers are running before tests
    that use this fixture.  Uses sudo if a plain rm raises PermissionError
    (Docker-created files are owned by root inside the container).
    """
    yield
    _rm_workspace_tree(SHARED_WORKSPACE)
    _rm_workspace_tree(OUTPUT_DIR)


def _rm_workspace_tree(directory: Path) -> None:
    """Remove all top-level subdirectories inside *directory*.

    Tries plain shutil.rmtree first.  Falls back to sudo rm -rf on
    PermissionError.
    """
    if not directory.is_dir():
        return
    for entry in directory.iterdir():
        if not entry.is_dir():
            continue
        try:
            shutil.rmtree(entry)
        except PermissionError:
            subprocess.run(
                ["sudo", "rm", "-rf", str(entry)],
                check=True,
                capture_output=True,
            )


# ---------------------------------------------------------------------------
# Simple fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def parser_url() -> str:
    """Return the base URL of the Parser service."""
    return os.environ.get("AGVS4RTL_PARSER_URL", "http://localhost:8001")


@pytest.fixture(scope="function")
def api_client() -> httpx.Client:
    """Return an httpx client with a 600-second timeout (supports LLM calls)."""
    return httpx.Client(timeout=600.0)


@pytest.fixture(scope="function")
def unique_top_module(request: pytest.FixtureRequest) -> str:
    """Generate a unique top module name per test.

    Format: ``test_<test_function_name>_<random_hex>``
    """
    name = request.node.name
    return f"test_{name}_{uuid4().hex[:6]}"
