"""Verification agent for requirement-code consistency checks.

Consumes artifacts from NLP/Architect/Codegen stages and evaluates whether
generated RTL framework is consistent with the original natural language intent.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..llm_config import resolve_agent_llm_config


class VerifyAgent:
    """Reasoning-based consistency verification agent."""

    SYSTEM_PROMPT = """你是RTL一致性审查专家。请审查“自然语言需求、结构化意图、架构JSON、生成代码”之间的一致性。

审查重点：
1) 需求与 intent 是否一致（接口、频率、位宽、时钟复位）
2) intent/architecture 与代码是否一致（顶层接口、信号命名、模块职责）
3) 是否存在关键遗漏（接口缺失、约束未体现、明显功能偏移）

输出要求：
- 仅输出 JSON，不要 markdown。
- JSON 格式：
{
  "status": "pass|warn|fail",
  "consistency_score": 0,
  "summary": "一句话总结",
  "issues": [
    {
      "type": "intent_mismatch|interface_mismatch|constraint_gap|code_gap",
      "severity": "high|medium|low",
      "message": "问题描述",
      "evidence": "证据片段"
    }
  ]
}
"""

    def __init__(
        self,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        cfg = resolve_agent_llm_config(
            "verify_agent",
            model_name=model_name,
            temperature=temperature,
            api_key=api_key,
            api_base=api_base,
        )

        self.model_name = cfg["model_name"] or "deepseek-reasoner"
        self.temperature = cfg["temperature"] if cfg["temperature"] is not None else 0.0

        self.llm = ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            openai_api_key=cfg["api_key"],
            openai_api_base=cfg["api_base"],
        )

    def verify(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Verify consistency across NL -> intent -> architecture -> code."""
        payload = {
            "natural_language": state.get("natural_language", ""),
            "intent": state.get("intent", {}),
            "constraints": state.get("constraints", {}),
            "architecture": state.get("architecture", {}),
            "generated_code": state.get("generated_code", {}),
        }

        messages = [
            SystemMessage(content=self.SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False, indent=2)),
        ]

        try:
            response = self.llm.invoke(messages)
            report = self._parse_report(str(getattr(response, "content", "")))
        except Exception as exc:
            print(f"Warning: Verify agent failed, using fallback. Error: {exc}")
            report = self._fallback_verify(payload)

        report.setdefault("verified_at", datetime.now(timezone.utc).isoformat())
        report.setdefault("model", self.model_name)
        return {"verification": report}

    def _parse_report(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            text = text[start:end].strip()

        parsed = json.loads(text)
        parsed.setdefault("status", "warn")
        parsed.setdefault("consistency_score", 60)
        parsed.setdefault("summary", "模型返回未包含完整摘要，已使用默认值")
        parsed.setdefault("issues", [])
        return parsed

    def _fallback_verify(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        intent = payload.get("intent", {})
        constraints = payload.get("constraints", {})
        generated = payload.get("generated_code", {})
        code = str(generated.get("content", ""))

        issues: List[Dict[str, str]] = []
        score = 100

        if "module" not in code:
            issues.append(
                {
                    "type": "code_gap",
                    "severity": "high",
                    "message": "生成代码缺少 module 声明",
                    "evidence": "未检出关键字 'module'",
                }
            )
            score -= 40

        interfaces = [str(x).lower() for x in intent.get("interfaces", [])]
        if any("axi" in itf for itf in interfaces) and "axi_" not in code.lower():
            issues.append(
                {
                    "type": "interface_mismatch",
                    "severity": "medium",
                    "message": "需求包含 AXI 接口，但代码中未检测到 axi_ 前缀信号",
                    "evidence": f"interfaces={interfaces}",
                }
            )
            score -= 20

        if any("apb" in itf for itf in interfaces) and "apb_" not in code.lower():
            issues.append(
                {
                    "type": "interface_mismatch",
                    "severity": "medium",
                    "message": "需求包含 APB 接口，但代码中未检测到 apb_ 前缀信号",
                    "evidence": f"interfaces={interfaces}",
                }
            )
            score -= 20

        clk = str(intent.get("clock") or "").strip()
        rst = str(intent.get("reset") or "").strip()
        lower_code = code.lower()

        if clk and clk.lower() not in lower_code:
            issues.append(
                {
                    "type": "constraint_gap",
                    "severity": "low",
                    "message": "代码中未匹配到 intent 指定时钟名",
                    "evidence": f"clock={clk}",
                }
            )
            score -= 10

        if rst and rst.lower() not in lower_code:
            issues.append(
                {
                    "type": "constraint_gap",
                    "severity": "low",
                    "message": "代码中未匹配到 intent 指定复位名",
                    "evidence": f"reset={rst}",
                }
            )
            score -= 10

        hard = constraints.get("hard", [])
        freq_text = "".join(str(item.get("value", "")) for item in hard if item.get("name") == "freq")
        if freq_text:
            mhz = re.findall(r"(\d+)\s*mhz", freq_text.lower())
            if mhz and "todo" in lower_code:
                score -= 5

        score = max(0, min(100, score))
        status = "pass" if score >= 85 else ("warn" if score >= 60 else "fail")

        return {
            "status": status,
            "consistency_score": score,
            "summary": "一致性校验完成（fallback 规则引擎）",
            "issues": issues,
        }


def verify_consistency_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node: verify consistency across previous stages."""
    agent = VerifyAgent()
    verify_input_snapshot = {
        "natural_language": state.get("natural_language", ""),
        "intent": state.get("intent", {}),
        "constraints": state.get("constraints", {}),
        "architecture": state.get("architecture", {}),
        "generated_code": state.get("generated_code", {}),
    }
    verified = agent.verify(state)

    round_outputs = list(state.get("round_outputs", []))
    round_outputs.append(
        {
            "round": len(round_outputs) + 1,
            "stage": "verify",
            "model": verified.get("verification", {}).get("model", agent.model_name),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_snapshot": verify_input_snapshot,
            "output": {
                "verification": verified.get("verification", {}),
            },
        }
    )

    return {
        **verified,
        "round_outputs": round_outputs,
    }
