#!/usr/bin/env python3
"""Launch the map investigation application (replaces the old Dash map)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.Mapui.api import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8051)
