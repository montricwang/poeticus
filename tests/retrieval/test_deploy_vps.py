"""Guard against shipping a Retrieval service without its path configuration."""
import shutil
import subprocess
from pathlib import Path

import pytest


DEPLOY_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/retrieval/deploy_vps.sh"


def test_deployment_bundle_contains_shared_data_path_module():
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "backend/data_paths.py" in source
    assert "refusing deployment" in source
    assert "POETICUS_RETRIEVAL_REMOTE_DATA_ROOT" in source


def test_deployment_script_has_valid_bash_syntax():
    if shutil.which("bash") is None:
        pytest.skip("Bash is not available on this runner")
    subprocess.run(["bash", "-n", str(DEPLOY_SCRIPT)], check=True)
