"""Pytest configuration helpers used across the suite.

Ensures the project root is importable so tests can resolve modules like
``main`` when running in environments where the working directory is not on
``sys.path`` (e.g., some CI runners).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
