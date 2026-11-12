"""Project-wide constants and defaults."""

import os
import uuid
from pathlib import Path

from hpdq import __version__

PROJECT_URL = "https://github.com/ExHansen/harga-pangan-dq"

DATA_DIR_ENV = "HPDQ_DATA_DIR"
DEFAULT_DATA_DIR = Path("data")
DEFAULT_BUILD_DIR = Path("build")

# Politeness rules for the source (docs/design.md §2).
MIN_REQUEST_INTERVAL_S = 3.0
MAX_REQUESTS_PER_RUN = 60
RETRY_BACKOFF_S: tuple[float, ...] = (5.0, 15.0, 45.0)
REQUEST_TIMEOUT_S = 30.0

# Each daily request covers D-7..D so late data and revisions are re-read at no extra request cost.
DEFAULT_WINDOW_DAYS = 7


def user_agent() -> str:
    return f"harga-pangan-dq/{__version__} (+{PROJECT_URL})"


def default_data_dir() -> Path:
    return Path(os.environ.get(DATA_DIR_ENV, DEFAULT_DATA_DIR))


def default_run_id() -> str:
    """GitHub run id + attempt when running in Actions, otherwise a local random id."""
    gh_run = os.environ.get("GITHUB_RUN_ID")
    if gh_run:
        return f"gh{gh_run}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    return f"local-{uuid.uuid4().hex[:8]}"
