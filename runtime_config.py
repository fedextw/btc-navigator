"""Portable state location. Never place credentials in research records."""
import os
from pathlib import Path

STATE_ROOT = Path(os.environ.get("BTC_NAVIGATOR_STATE_DIR", str(Path(__file__).resolve().parent / ".local-state"))).expanduser()
