"""Code generation agent for Verilog framework output.

Consumes structured JSON state (intent/constraints/architecture/ppa) and
produces a compilable Verilog skeleton.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..llm_config import resolve_agent_llm_config


class CodegenAgent:
    """Generate Verilog framework code from structured JSON input."""

    SYSTEM_PROMPT = """你是资深RTL工程师。你的任务是把输入的JSON状态转换为Verilog框架代码。

要求：
1) 仅输出Verilog代码，不要解释文字，不要markdown代码块。
2) 输出必须至少包含：
   - 一个顶层 module 声明
   - clk/rst_n 端口（若输入中存在）
   - TODO 注释区域（接口处理、寄存器定义、读写路径）
3) 不要编造复杂子模块，只生成可扩展骨架。
4) 代码风格保持简洁、可读，便于后续自动填充。
"""

    def __init__(
        self,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        cfg = resolve_agent_llm_config(
            "generate_agent",
            model_name=model_name,
            temperature=temperature,
            api_key=api_key,
            api_base=api_base,
        )

        self.model_name = cfg["model_name"] or "Qwen/Qwen3-Coder-480B-A35B-Instruct"
        self.temperature = cfg["temperature"] if cfg["temperature"] is not None else 0.1
        self.llm = ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            openai_api_key=cfg["api_key"],
            openai_api_base=cfg["api_base"],
        )

    def generate_framework(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Generate Verilog framework from workflow state."""
        payload = {
            "intent": state.get("intent", {}),
            "constraints": state.get("constraints", {}),
            "architecture": state.get("architecture", {}),
            "ppa": state.get("ppa", {}),
            "metadata": state.get("metadata", {}),
        }

        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False, indent=2)),
        ]

        try:
            response = self.llm.invoke(messages)
            verilog = self._normalize_verilog(str(getattr(response, "content", "")))
            if "module" not in verilog:
                raise ValueError("No module keyword found in model output")
        except Exception as exc:
            print(f"Warning: Codegen failed, using fallback. Error: {exc}")
            verilog = self._fallback_framework(payload)

        return {
            "generated_code": {
                "language": "verilog",
                "kind": "framework",
                "model": self.model_name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "content": verilog,
            }
        }

    def _normalize_verilog(self, text: str) -> str:
        text = text.strip()
        if "```verilog" in text:
            start = text.find("```verilog") + len("```verilog")
            end = text.find("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            text = text[start:end].strip()
        return text

    def _fallback_framework(self, payload: Dict[str, Any]) -> str:
        intent = payload.get("intent", {})
        architecture = payload.get("architecture", {})
        top_name = (
            architecture.get("hierarchy", {}).get("top", {}).get("name")
            or self._safe_module_name(intent.get("summary", "top_module"))
        )
        clk = intent.get("clock") or "clk"
        rst = intent.get("reset") or "rst_n"

        return (
            f"module {top_name} (\n"
            f"    input  wire {clk},\n"
            f"    input  wire {rst}\n"
            f");\n\n"
            f"    // TODO: Interface signal declarations\n"
            f"    // TODO: Register definitions\n"
            f"    // TODO: Write path logic\n"
            f"    // TODO: Read path logic\n"
            f"\nendmodule\n"
        )

    def _safe_module_name(self, raw: str) -> str:
        name = raw.lower().strip()
        name = re.sub(r"[^a-z0-9_]+", "_", name)
        name = re.sub(r"_+", "_", name).strip("_")
        if not name:
            name = "top_module"
        if not name[0].isalpha() and name[0] != "_":
            name = f"m_{name}"
        return name[:64]


def codegen_framework_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node: generate Verilog framework from structured JSON state."""
    agent = CodegenAgent()
    generated = agent.generate_framework(state)

    round_outputs = list(state.get("round_outputs", []))
    codegen_input_snapshot = {
        "intent": state.get("intent", {}),
        "constraints": state.get("constraints", {}),
        "architecture": state.get("architecture", {}),
        "ppa": state.get("ppa", {}),
        "metadata": state.get("metadata", {}),
    }
    round_outputs.append(
        {
            "round": len(round_outputs) + 1,
            "stage": "codegen",
            "model": generated.get("generated_code", {}).get("model", agent.model_name),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_snapshot": codegen_input_snapshot,
            "output": {
                "generated_code": generated.get("generated_code", {}),
            },
        }
    )

    return {
        **generated,
        "round_outputs": round_outputs,
    }
