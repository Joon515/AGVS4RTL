from __future__ import annotations

from typing import Any, Dict, List
import re
import json

import httpx

from src.common.models import LlmRuntimeConfig


# ---------------------------------------------------------------------------
# 五个 LLM 转发 Header 常量，供 Parser / Generator / Verify 的 FastAPI
# 入口层统一使用，避免跨模块字符串字面量漂移。
# ---------------------------------------------------------------------------
LLM_HEADER_ENABLED = "X-AGVS4RTL-LLM-Enabled"
LLM_HEADER_BASE_URL = "X-AGVS4RTL-LLM-Base-URL"
LLM_HEADER_API_KEY = "X-AGVS4RTL-LLM-API-Key"
LLM_HEADER_MODEL = "X-AGVS4RTL-LLM-Model"
LLM_HEADER_PROFILE = "X-AGVS4RTL-LLM-Profile"


# ---------------------------------------------------------------------------
# 共享 LLM 工具函数
# ---------------------------------------------------------------------------


def _chat_completions_url(base_url: str) -> str:
    """Normalize a base URL into the /chat/completions endpoint."""
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _extract_json_object(content: str) -> Dict[str, Any]:
    """Extract a JSON object from LLM response content.

    Handles Markdown fenced code blocks (`` ```json … ``` ``) and
    free-form text that contains a JSON object somewhere.
    """
    fence_match = re.search(
        r"```(?:json)?\s*(.*?)```", content, re.IGNORECASE | re.DOTALL
    )
    if fence_match is not None:
        content = fence_match.group(1)

    content = content.strip()
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM parser response does not contain a JSON object")

    parsed = json.loads(content[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM parser response JSON is not an object")
    return parsed


def _call_openai_compatible_chat(
    llm_config: LlmRuntimeConfig,
    messages: List[Dict[str, str]],
) -> tuple[str, Dict[str, Any]]:
    """Call an OpenAI-compatible chat API.

    Returns
    -------
    tuple[str, dict]
        (stripped response content, transcript dict ready for logging).
    """
    if not llm_config.base_url:
        raise ValueError("LLM is enabled but base_url is missing")
    if llm_config.api_key is None:
        raise ValueError("LLM is enabled but api_key is missing")
    if not llm_config.model:
        raise ValueError("LLM is enabled but model is missing")

    payload = {
        "model": llm_config.model,
        "messages": messages,
        "temperature": 0.1,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {llm_config.api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }

    llm_timeout = float(os.getenv("AGVS4RTL_LLM_TIMEOUT_SECONDS", "300"))
    with httpx.Client(timeout=llm_timeout) as client:
        response = client.post(
            _chat_completions_url(llm_config.base_url),
            json=payload,
            headers=headers,
        )
        if response.status_code >= 400:
            raise ValueError(
                f"LLM API error: status={response.status_code}, "
                f"body={response.text[:500]}"
            )
        response.raise_for_status()

    response_payload = response.json()
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(
            "LLM response is not OpenAI chat-completions compatible"
        ) from exc

    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM response content is empty")

    sanitized_choices = []
    for response_choice in response_payload.get("choices", []):
        if not isinstance(response_choice, dict):
            continue
        message = response_choice.get("message")
        if not isinstance(message, dict):
            continue
        sanitized_choices.append(
            {
                "index": response_choice.get("index"),
                "message": {
                    "role": message.get("role"),
                    "content": message.get("content"),
                },
                "finish_reason": response_choice.get("finish_reason"),
            }
        )

    return content.strip(), {
        "request": {
            "messages": messages,
            "temperature": payload["temperature"],
            "stream": payload["stream"],
        },
        "response": {
            "id": response_payload.get("id"),
            "object": response_payload.get("object"),
            "created": response_payload.get("created"),
            "choices": sanitized_choices,
            "usage": response_payload.get("usage"),
        },
    }
