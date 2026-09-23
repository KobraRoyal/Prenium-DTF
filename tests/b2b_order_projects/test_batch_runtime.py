"""Execute browser-side batch behaviors without a network or browser dependency."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_batch_upload_runtime_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for frontend runtime checks")
    script = Path(__file__).resolve().parents[1] / "frontend" / "b2b_batch_runtime.cjs"
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
