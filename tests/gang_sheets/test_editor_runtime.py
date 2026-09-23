"""Execute the gang sheet editor's critical browser behaviors in Node.js."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_gang_sheet_editor_runtime_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for frontend runtime checks")
    script = Path(__file__).resolve().parents[1] / "frontend" / "gang_sheet_editor_runtime.cjs"
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
