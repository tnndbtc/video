"""
Root conftest for video/tools/.

Adds video/tools/ to sys.path so that `schemas`, `renderer`, and
other top-level packages are importable without installing a package.

This file is picked up automatically by pytest when tests under
video/tools/tests/ are collected.
"""
import sys
from pathlib import Path

_TOOLS_ROOT = Path(__file__).parent
if str(_TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT))
