"""Application entry for AGVS4RTL.

Currently starts a Rich-based TUI to collect preprocessing inputs.
"""

from ui import TUIApp


def main() -> None:
	"""Run the TUI front-end."""

	TUIApp().run()


if __name__ == "__main__":
	main()