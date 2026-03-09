"""Application entry for AGVS4RTL.

This module starts the Rich-based TUI and supports both invocation styles:
- ``python -m app.main``
- ``python /app/app/main.py`` (common in Docker exec)
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_project_root() -> Path:
	"""Ensure the repository root is on ``sys.path``.

	When started as ``python /app/app/main.py``, Python adds ``/app/app`` to
	``sys.path`` but not ``/app``. The ``app.*`` absolute imports require
	``/app`` to be present, so we inject it here for robust startup.
	"""

	project_root = Path(__file__).resolve().parents[1]
	project_root_str = str(project_root)
	if project_root_str not in sys.path:
		sys.path.insert(0, project_root_str)
	return project_root


_ensure_project_root()

from app.ui import TUIApp


def main() -> None:
	"""Run the TUI front-end."""

	TUIApp().run()


if __name__ == "__main__":
	main()