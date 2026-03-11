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
from ..prompts.loader import PromptLoader


class CodegenAgent:
    """Generate Verilog framework code from structured JSON input."""

    PROMPT_TEMPLATE = "generator/hdl_generation.j2"
    FALLBACK_SYSTEM_PROMPT = """你是资深RTL工程师。你的任务是把输入的JSON状态转换为完整、可综合的Verilog RTL实现代码。

要求：
1) 仅输出Verilog代码，不要解释文字，不要markdown代码块。
2) 输出必须包含：
   - 一个顶层 module 声明，含完整端口列表
   - 所有数据/控制/接口信号的声明
   - 完整的寄存器定义和线网定义
   - 完整的组合逻辑和时序逻辑实现
   - 接口协议的完整握手信号实现（如AXI-Lite需要所有通道）
   - 数据通路实现（如乘法器、流水线等）
3) 使用参数化设计（parameter/localparam）定义关键位宽。
4) 代码必须可综合，不使用initial块或系统任务。
5) 如果需求包含流水线，必须实现对应级数的流水线寄存器。
"""

    def __init__(
        self,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        llm: Optional[Any] = None,
        prompt_loader: Optional[PromptLoader] = None,
    ):
        """Initialize CodegenAgent.

        Args:
            model_name: OpenAI-compatible model name
            temperature: LLM sampling temperature
            api_key: OpenAI-compatible API key
            api_base: OpenAI-compatible base URL
            llm: Optional injected LLM client for tests
            prompt_loader: Optional injected PromptLoader for tests
        """
        cfg = resolve_agent_llm_config(
            "coder_agent",
            model_name=model_name,
            temperature=temperature,
            api_key=api_key,
            api_base=api_base,
        )
        if not cfg.get("api_key"):
            cfg = resolve_agent_llm_config(
                "generate_agent",
                model_name=model_name,
                temperature=temperature,
                api_key=api_key,
                api_base=api_base,
            )

        self.model_name = cfg["model_name"] or "Qwen/Qwen3-Coder-480B-A35B-Instruct"
        self.temperature = cfg["temperature"] if cfg["temperature"] is not None else 0.1
        debug = cfg.get("_debug", {})
        print(
            f"[CodegenAgent] Init: model={self.model_name}, "
            f"api_base={cfg['api_base']}, "
            f"has_key={debug.get('has_api_key')}, "
            f"key_src={debug.get('api_key_source')}"
        )
        self.llm = llm or ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            openai_api_key=cfg["api_key"],
            openai_api_base=cfg["api_base"],
        )
        self.prompt_loader = prompt_loader or PromptLoader()

    def generate_framework(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Generate Verilog RTL implementation from workflow state."""
        payload = {
            "intent": state.get("intent", {}),
            "constraints": state.get("constraints", {}),
            "architecture": state.get("architecture", {}),
            "ppa": state.get("ppa", {}),
            "metadata": state.get("metadata", {}),
        }

        try:
            system_prompt = self._build_system_prompt(payload)
        except Exception as exc:
            print(f"[CodegenAgent] Warning: Prompt rendering failed, using fallback prompt. Error: {exc}")
            system_prompt = self.FALLBACK_SYSTEM_PROMPT

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=(
                    "以下是结构化输入状态(JSON)，请严格按照系统提示词要求，"
                    "生成完整的、可综合的 Verilog RTL 实现代码：\n\n"
                    + json.dumps(payload, ensure_ascii=False, indent=2)
                )
            ),
        ]

        try:
            print(f"[CodegenAgent] Calling LLM: model={self.model_name}")
            response = self.llm.invoke(messages)
            raw_content = str(getattr(response, "content", ""))
            print(f"[CodegenAgent] LLM response length: {len(raw_content)} chars")
            if len(raw_content) < 20:
                print(f"[CodegenAgent] LLM response too short: {raw_content!r}")
            verilog = self._normalize_verilog(raw_content)
            if "module" not in verilog:
                raise ValueError(f"No module keyword found in model output (first 200 chars: {verilog[:200]!r})")
        except Exception as exc:
            print(f"[CodegenAgent] Codegen failed, using fallback. Error: {type(exc).__name__}: {exc}")
            verilog = self._fallback_framework(payload)

        return {
            "generated_code": {
                "language": "verilog",
                "kind": "implementation",
                "model": self.model_name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "content": verilog,
            }
        }

    def _build_system_prompt(self, payload: Dict[str, Any]) -> str:
        """Render system prompt from Jinja2 template."""
        intent = payload.get("intent", {})
        architecture = payload.get("architecture", {})
        raw_name = (
            architecture.get("hierarchy", {}).get("top", {}).get("name")
            or intent.get("summary", "top_module")
        )
        top_name = self._safe_module_name(raw_name)

        return self.prompt_loader.render(
            self.PROMPT_TEMPLATE,
            payload=payload,
            summary=intent.get("summary", ""),
            target_language=intent.get("target_language", "verilog"),
            clock=intent.get("clock") or "clk",
            reset=intent.get("reset") or "rst_n",
            interfaces=intent.get("interfaces", []),
            top_module=top_name,
            constraints=payload.get("constraints", {}),
            architecture=architecture,
            ppa=payload.get("ppa", {}),
        )

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
        raw_name = (
            architecture.get("hierarchy", {}).get("top", {}).get("name")
            or intent.get("summary", "top_module")
        )
        top_name = self._safe_module_name(raw_name)
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
    """LangGraph node: generate Verilog RTL from structured JSON state."""
    agent = CodegenAgent()
    generated = agent.generate_framework(state)

    # Save generated RTL to file
    code_content = generated.get("generated_code", {}).get("content", "")
    if code_content and "module" in code_content:
        _save_rtl_file(code_content, state)

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


def _save_rtl_file(code_content: str, state: Dict[str, Any]) -> None:
    """Save generated RTL code to data/workspace/rtl/ directory."""
    from pathlib import Path

    # Extract module name from code
    match = re.search(r"module\s+(\w+)", code_content)
    module_name = match.group(1) if match else "top_module"

    # Determine workspace root
    workspace_root = Path.cwd()
    rtl_dir = workspace_root / "data" / "workspace" / "rtl"
    rtl_dir.mkdir(parents=True, exist_ok=True)

    rtl_path = rtl_dir / f"{module_name}.v"
    rtl_path.write_text(code_content, encoding="utf-8")
    print(f"[CodegenAgent] RTL saved to: {rtl_path}")
