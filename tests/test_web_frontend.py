"""Run the frontend auth behavior tests when Node.js is available."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_frontend_auth_behavior():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for frontend behavior tests")
    result = subprocess.run([node, "--test", str(Path(__file__).with_suffix(".cjs"))],
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
