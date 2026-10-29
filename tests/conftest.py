import sys
from pathlib import Path

import pytest

# Make the project root importable regardless of how pytest is invoked.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import log as applog  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_structlog_config():
    """Every test may reconfigure structlog to a capture stream; put it back
    to the default stdout configuration afterwards."""
    yield
    applog.setup_logging()
