# AGVS4RTL Integration Tests

Automated integration tests for the AGVS4RTL multi-agent RTL generation and
verification system. Tests exercise the full pipeline from intent parsing
through code generation to verification, using Docker Compose to orchestrate
all three services (parser, gen, verify).

---

## Prerequisites

- **Docker** and **docker-compose** (or `docker compose` plugin)
- **Python 3.11+**
- Linux environment (the cleanup fixture uses `sudo rm` for Docker-owned
  files; macOS may need adjustments)

---

## Setup

```bash
# Install Python dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env to set AGVS4RTL_LLM_ENABLED=true if you want LLM-dependent tests
```

> The tests manage the Docker Compose lifecycle automatically (start before
> the suite, stop after). You do **not** need to run `docker compose up`
> manually.

---

## Running Tests

Run all tests:

```bash
pytest tests/ -v
```

Run tests excluding LLM-dependent ones (the common case for CI):

```bash
pytest tests/ -v -m "not llm"
```

Run only fast tests (exclude docker and slow):

```bash
pytest tests/ -v -m "not slow and not docker"
```

Run a specific test file:

```bash
pytest tests/test_host_workflow.py -v
```

Collect tests without executing them (useful to verify discovery):

```bash
pytest tests/ --collect-only
```

---

## Test Categories

| Marker   | Description                                                  |
| :------- | :----------------------------------------------------------- |
| `llm`    | Tests that call a real LLM API. Skipped unless               |
|          | `AGVS4RTL_LLM_ENABLED=true` is set.                          |
| `docker` | Tests that require the full Docker Compose environment        |
|          | (parser, gen, verify containers).                             |
| `slow`   | Tests that typically take longer than 30 seconds (e.g., full  |
|          | workflow end-to-end, LLM-driven generation).                  |

### Test files

| File                          | Covers                                                |
| :---------------------------- | :---------------------------------------------------- |
| `test_host_workflow.py`       | Full parser workflow via HTTP; retry paths             |
| `test_verify_only_faults.py`  | Fault injection scenarios via docker compose exec      |
| (future)                      | Additional test files as the test suite grows          |

---

## Expected Output

A typical run (without LLM) should produce output similar to:

```
$ pytest tests/ -v -m "not llm"
============================== test session starts ==============================
platform linux -- Python 3.11.9, pytest-9.0.2, pluggy-1.5.0
rootdir: /home/user/AGVS4RTL
configfile: tests/pytest.ini
collected 12 items

tests/test_host_workflow.py::test_health_pass       PASSED            [  8%]
tests/test_host_workflow.py::test_retry_compile     PASSED            [ 16%]
tests/test_host_workflow.py::test_retry_semantic    PASSED            [ 25%]
tests/test_host_workflow.py::test_retry_infra       PASSED            [ 33%]
tests/test_host_workflow.py::test_retry_port_dir    PASSED            [ 41%]
tests/test_host_workflow.py::test_retry_port_width  PASSED            [ 50%]
...
========================= 6 passed, 6 skipped in 42.3s ==========================
```

---

## Troubleshooting

### Docker is not running

**Error**: `docker compose up failed (exit 1)`

**Fix**: Start the Docker daemon:
```bash
sudo systemctl start docker
# or
sudo dockerd &
```

### Port conflict on 8001

**Error**: `docker: Error response from daemon: driver failed programming
external connectivity on endpoint agvs4rtl_parser`

**Fix**: Stop the conflicting process or change the port mapping in
`docker-compose.yml`. You can also override via the `AGVS4RTL_PARSER_URL`
environment variable.

### LLM tests are all skipped

Tests marked with `@pytest.mark.llm` are skipped by default. To enable them:

```bash
export AGVS4RTL_LLM_ENABLED=true
# Also set the LLM connection details in .env:
#   AGVS4RTL_LLM_BASE_URL=<your endpoint>
#   AGVS4RTL_LLM_API_KEY=<your key>
#   AGVS4RTL_LLM_MODEL=<model name>
```

### Permission denied when cleaning workspace

Docker containers create files owned by root inside `shared_workspace/` and
`Output/`. The `cleanup_workspace` fixture falls back to `sudo rm -rf`
automatically. Ensure your user has passwordless sudo configured, or expect
a password prompt.

### Containers are left running after test failure

If the test session is killed abruptly (SIGKILL, power loss), containers may
remain. Clean them up manually:

```bash
docker compose down
```

### Tests fail with connection refused

The `docker_services` fixture waits up to 60 seconds for the parser health
endpoint. If build times are consistently longer, check:

1. Are you on a slow network? First build pulls base images and can take
   several minutes. Consider running `docker compose build` ahead of time.
2. Is the parser starting correctly? Check logs:
   ```bash
   docker logs agvs4rtl_parser
   ```
3. Is the port mapping correct? The parser container maps `8001:8000` by
   default. Verify with:
   ```bash
   docker compose ps
   ```

---

## Environment Variables

| Variable                    | Default                  | Description                          |
| :-------------------------- | :----------------------- | :----------------------------------- |
| `AGVS4RTL_LLM_ENABLED`      | `false`                  | Set to `true` to enable LLM tests    |
| `AGVS4RTL_PARSER_URL`       | `http://localhost:8001`  | Parser service base URL              |
| `AGVS4RTL_LLM_BASE_URL`     | (empty)                  | LLM API endpoint                     |
| `AGVS4RTL_LLM_API_KEY`      | (empty)                  | LLM API key                          |
| `AGVS4RTL_LLM_MODEL`        | (empty)                  | LLM model name                       |
