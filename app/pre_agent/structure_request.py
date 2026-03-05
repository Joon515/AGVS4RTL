"""Pre-agent request/response schema and preprocessing utilities.

This module defines structured input/output models for the pre-processing
stage. It normalizes natural-language requirements and constraints into
typed structures that can be embedded into LangGraph state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class NaturalLanguageRequest(BaseModel):
    """Raw natural language input from user."""

    text: str = Field(..., description="原始需求文本")
    language: str = Field("zh", description="输入语言，如 zh/en")
    source: str = Field("tui", description="输入来源，如 tui/api")


class Constraint(BaseModel):
    """A single constraint entry."""

    name: str = Field(..., description="约束名称")
    value: Any = Field(..., description="约束值")
    priority: int = Field(1, description="优先级，soft 约束使用")


class StructuredConstraints(BaseModel):
    """Normalized hard/soft constraints."""

    hard: List[Constraint] = Field(default_factory=list, description="硬约束")
    soft: List[Constraint] = Field(default_factory=list, description="软约束")


class DesignIntent(BaseModel):
    """High-level design intent extracted from the request."""

    summary: str = Field(..., description="需求摘要")
    target_language: str = Field("verilog", description="目标 HDL 语言")
    clock: Optional[str] = Field(None, description="时钟信息")
    reset: Optional[str] = Field(None, description="复位信息")
    interfaces: List[str] = Field(default_factory=list, description="接口/总线关键词")


class PreprocessInput(BaseModel):
    """Input bundle for preprocessing."""

    natural_language: NaturalLanguageRequest
    hard_constraints: Optional[Dict[str, Any]] = None
    soft_constraints: Optional[Dict[str, Any]] = None


class PreprocessOutput(BaseModel):
    """Output bundle for preprocessing."""

    request_id: str
    created_at: str
    intent: DesignIntent
    constraints: StructuredConstraints
    raw: NaturalLanguageRequest

    def to_state(self) -> Dict[str, Any]:
        """Convert to LangGraph state payload (partial)."""

        return {
            "intent": self.intent.model_dump(),
            "constraints": self.constraints.model_dump(),
            "metadata": {
                "request_id": self.request_id,
                "created_at": self.created_at,
                "language": self.raw.language,
                "source": self.raw.source,
            },
        }


class Preprocessor:
    """Preprocess natural language and constraints into structured payload."""

    @staticmethod
    def _normalize_constraints(
        constraints: Optional[Dict[str, Any]],
        default_priority: int = 1,
    ) -> List[Constraint]:
        """Normalize constraint dict into a list of `Constraint`.

        The input dict is interpreted as {name: value}.
        """

        if not constraints:
            return []
        normalized: List[Constraint] = []
        for name, value in constraints.items():
            normalized.append(Constraint(name=name, value=value, priority=default_priority))
        return normalized

    @classmethod
    def from_text(
        cls,
        text: str,
        language: str = "zh",
        hard_constraints: Optional[Dict[str, Any]] = None,
        soft_constraints: Optional[Dict[str, Any]] = None,
        target_language: str = "verilog",
        interfaces: Optional[List[str]] = None,
        clock: Optional[str] = None,
        reset: Optional[str] = None,
        source: str = "tui",
    ) -> PreprocessOutput:
        """Create a `PreprocessOutput` from raw text and constraints."""

        request_id = str(uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        raw = NaturalLanguageRequest(text=text, language=language, source=source)
        intent = DesignIntent(
            summary=text.strip(),
            target_language=target_language,
            clock=clock,
            reset=reset,
            interfaces=interfaces or [],
        )
        constraints = StructuredConstraints(
            hard=cls._normalize_constraints(hard_constraints, default_priority=0),
            soft=cls._normalize_constraints(soft_constraints, default_priority=1),
        )
        return PreprocessOutput(
            request_id=request_id,
            created_at=created_at,
            intent=intent,
            constraints=constraints,
            raw=raw,
        )
