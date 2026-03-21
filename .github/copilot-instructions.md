# Project Guidelines

## Code Style
- Prefer strict typing and schema-first design with Pydantic models in `src/common/models.py`.
- Reuse existing enums and models before adding new protocol fields; avoid ad-hoc dict payloads between modules.
- Keep comments concise and practical; preserve existing Chinese comments and domain terms when editing nearby code.
- Keep service code separated by module domain: parser logic in `src/parser`, generation logic in `src/generator`, verification logic in `src/verify`.

## Architecture
- This project uses a multi-service layout orchestrated by Docker Compose:
	- Parser service: `src/parser`
	- Generator service: `src/generator`
	- Verify service: `src/verify`
- Shared artifacts flow through `shared_workspace/` (`specs/`, `rtl/`, `sim/`) mounted into all containers.
- `src/common/models.py` is the contract layer for cross-node data; treat it as the source of truth for payload structure.
- The repository is in a transition state from Celery/Redis to FastAPI/LangGraph; prefer current FastAPI-oriented patterns in Docker files and compose config.

## Build and Test
- Local dependency install:
	- `pip install -r requirements.txt`
- Build and run all services:
	- `docker-compose up -d --build`
- Stop services:
	- `docker-compose down`
- Verify Python syntax quickly when tests are unavailable:
	- `python -m compileall src`
- If implementing API entrypoints, ensure compose targets exist (`src.parser.main`, `src.generator.main`, `src.verify.main`).

## Conventions
- Keep generated/derived artifacts under `shared_workspace/`; do not hardcode output paths outside this tree.
- Preserve container user mapping assumptions in `docker-compose.yml` (`USER_ID` / `GROUP_ID`) to avoid permission regressions.
- Prefer lightweight interfaces and dependencies for new code; avoid introducing heavy infrastructure libraries (for example Celery/Redis) unless explicitly required.
- Avoid introducing new Celery/Redis dependencies unless explicitly requested; current container setup installs FastAPI/uvicorn/httpx.
- When adding new request/response payloads, define typed models in `src/common/models.py` first, then consume them in service modules.

## Maintenance Workflow
- Keep documentation in sync with code changes (for example `README.md`, API or module usage notes) as part of the same task.
- Write a concise development log for each meaningful change set, including what changed, why, and follow-up items.
- After each commit, treat that commit as the new baseline and clear leftover temporary edits so the workspace returns to a clean state before the next task.
- Do not rewrite published commit history when doing post-commit cleanup unless explicitly requested.

## Known Pitfalls
- Compose commands reference `src.<module>.main:app`; some service entrypoint files may still be incomplete.
- Keep `requirements.txt` and Dockerfile installs in sync to avoid runtime dependency drift.
- Base image currently uses permissive `chmod -R 777` for development convenience; avoid relying on this behavior for security-sensitive changes.
