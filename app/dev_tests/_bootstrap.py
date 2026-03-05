"""Shared bootstrap utilities for development test scripts.

This module ensures direct script execution can import the `app` package
without duplicating path setup logic in every script.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def ensure_project_root() -> Path:
    """Ensure project root is present in ``sys.path`` and return it."""

    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return PROJECT_ROOT
