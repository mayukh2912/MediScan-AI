import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# isolated database + storage for tests
_tmp = tempfile.mkdtemp(prefix="mediscan_test_")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ.setdefault("MEDISCAN_STORAGE_DIR", f"{_tmp}/storage")

from tests.fixtures.make_fixtures import build_all  # noqa: E402


@pytest.fixture(scope="session")
def fixtures():
    return build_all(Path(_tmp) / "fixtures")


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c
