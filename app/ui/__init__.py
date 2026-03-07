"""UI package (TUI based on Rich)."""

from .config_store import ConfigStore

__all__ = ["ConfigStore", "TUIApp"]


def __getattr__(name: str):
	if name == "TUIApp":
		from .tui import TUIApp

		return TUIApp
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
