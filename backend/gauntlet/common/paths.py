"""Repository-relative locations of bundled content, overridable for container layouts."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("GAUNTLET_ROOT", Path(__file__).resolve().parents[3]))
SUITES_DIR = Path(os.environ.get("GAUNTLET_SUITES_DIR", REPO_ROOT / "suites"))
CONFIG_DIR = Path(os.environ.get("GAUNTLET_CONFIG_DIR", REPO_ROOT / "config"))
CALIBRATION_DIR = Path(os.environ.get("GAUNTLET_CALIBRATION_DIR", REPO_ROOT / "calibration"))
DATA_DIR = Path(os.environ.get("GAUNTLET_DATA_DIR", REPO_ROOT / ".data"))
CACHE_DIR = Path(os.environ.get("GAUNTLET_CACHE_DIR", REPO_ROOT / ".cache"))
