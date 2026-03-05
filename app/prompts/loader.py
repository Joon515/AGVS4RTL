"""Jinja2 prompt template loader.

This module centralizes prompt template rendering to keep prompts
separated from agent implementation code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound


class PromptLoader:
    """Jinja2 prompt template loader.

    This class provides a stable interface for loading and rendering
    prompt templates from the configured template directory.
    """

    def __init__(self, template_dir: Optional[str] = None):
        """Initialize the prompt loader.

        Args:
            template_dir: Optional absolute/relative template root path.
                Defaults to the local ``app/prompts`` directory.
        """
        default_template_dir = Path(__file__).resolve().parent
        resolved_template_dir = Path(template_dir) if template_dir else default_template_dir

        self.env = Environment(
            loader=FileSystemLoader(str(resolved_template_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            cache_size=400,
        )

        self.env.filters["code_escape"] = self._code_escape
        self.env.filters["json_format"] = self._json_format

    def render(self, template_name: str, **context: Any) -> str:
        """Render a prompt template with context.

        Args:
            template_name: Template filename relative to template root.
            **context: Variables passed into the template.

        Returns:
            Rendered prompt content.

        Raises:
            FileNotFoundError: If template does not exist.
        """
        try:
            template = self.env.get_template(template_name)
        except TemplateNotFound as exc:
            raise FileNotFoundError(f"Prompt template not found: {template_name}") from exc

        return template.render(**context)

    @staticmethod
    def _code_escape(text: Any) -> str:
        """Escape markdown code fence markers in generated text."""
        return str(text).replace("```", "\\```")

    @staticmethod
    def _json_format(obj: Any, indent: int = 2) -> str:
        """Render Python object as formatted JSON string."""
        return json.dumps(obj, ensure_ascii=False, indent=indent)
