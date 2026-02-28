"""Shared LLM configuration utilities.

Resolves model/API settings from explicit args, encrypted config store, and env vars.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from .ui.config_store import ConfigStore


def _discover_workspace_root(workspace_root: Optional[Path] = None) -> Path:
    """Discover workspace root for config loading."""
    if workspace_root:
        return workspace_root

    env_root = os.getenv("AGVS_WORKSPACE_ROOT")
    if env_root:
        return Path(env_root)

    current = Path.cwd()
    if (current / "data" / "config" / "agent-config.json").exists():
        return current

    return Path(__file__).resolve().parents[1]


def resolve_agent_llm_config(
    agent_name: str,
    *,
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Resolve final LLM configuration for an agent.

    Priority:
    1) Explicit kwargs
    2) data/config/agent-config.json (including decrypted api_key_enc)
    3) Environment variables
    """
    resolved_model = model_name
    resolved_temperature = temperature
    resolved_api_key = api_key
    resolved_api_base = api_base

    root = _discover_workspace_root(workspace_root)
    try:
        store = ConfigStore(root)
        config = store.load_config()
        agent_cfg = config.get("agents", {}).get(agent_name, {})

        if not resolved_model and agent_cfg.get("model"):
            resolved_model = str(agent_cfg["model"])

        if resolved_temperature is None and agent_cfg.get("temperature") is not None:
            resolved_temperature = float(agent_cfg["temperature"])

        if not resolved_api_base:
            resolved_api_base = (
                agent_cfg.get("api_base")
                or agent_cfg.get("api_base_url")
                or agent_cfg.get("base_url")
            )

        if not resolved_api_key and agent_cfg.get("api_key_enc"):
            try:
                resolved_api_key = store.decrypt_api_key(agent_cfg["api_key_enc"], config)
            except Exception:
                resolved_api_key = None
    except Exception:
        pass

    resolved_api_key = (
        resolved_api_key
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("LLM_API_KEY")
    )
    resolved_api_base = (
        resolved_api_base
        or os.getenv("OPENAI_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("LLM_API_BASE")
        or os.getenv("LLM_BASE_URL")
    )

    return {
        "model_name": resolved_model,
        "temperature": resolved_temperature,
        "api_key": resolved_api_key,
        "api_base": resolved_api_base,
    }
