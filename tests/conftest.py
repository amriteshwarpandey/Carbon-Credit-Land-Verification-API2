import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["CERTIFICATES_DIR"] = f"{_tmp}/certs"
os.environ["RATE_LIMIT_LOGIN_PER_MINUTE"] = "1000"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.celery_app import celery_app  # noqa: E402
from app.main import app  # noqa: E402

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _login(client, email, password):
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin@example.com", "admin12345")


@pytest.fixture(scope="session")
def users(client, admin):
    out = {}
    for role, email in [("field_agent", "agent@example.com"), ("auditor", "auditor@example.com"), ("field_agent", "agent2@example.com")]:
        r = client.post("/users", json={"email": email, "password": "password123", "role": role}, headers=admin)
        assert r.status_code == 201, r.text
        out[email] = _login(client, email, "password123")
    return {"agent": out["agent@example.com"], "auditor": out["auditor@example.com"], "agent2": out["agent2@example.com"]}
