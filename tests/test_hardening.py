import io
from unittest.mock import patch

import pytest

from test_flow import _next_latlon, _setup_log, _square


def _farmer(client, users, who="agent"):
    return client.post("/farmers", json={"name": "F"}, headers=users[who]).json()


def _png():
    return b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _up(name="x.png", data=None, ctype="image/png"):
    return {"file": (name, io.BytesIO(data if data is not None else _png()), ctype)}


# ---- spatial -----------------------------------------------------------------------------------
def test_overlap_and_acreage_checks(client, users):
    f = _farmer(client, users)
    lat, lon = _next_latlon()
    ok = client.post(f"/farmers/{f['id']}/plots", json={"name": "a", "crop_type": "c", "acreage": 2.5, "geojson": _square(lat, lon, 0.0009)}, headers=users["agent"])
    assert ok.status_code == 201

    # a different agent registering a heavily overlapping plot is rejected, without learning whose plot it is
    f2 = _farmer(client, users, "agent2")
    dup = client.post(f"/farmers/{f2['id']}/plots", json={"name": "b", "crop_type": "c", "acreage": 2.5, "geojson": _square(lat + 0.0003, lon + 0.0003, 0.0009)}, headers=users["agent2"])
    assert dup.status_code == 409 and "#" not in dup.json()["detail"]
    # a point plot inside the polygon also conflicts
    pt = client.post(f"/farmers/{f2['id']}/plots", json={"name": "c", "crop_type": "c", "acreage": 1, "latitude": lat + 0.0004, "longitude": lon + 0.0004}, headers=users["agent2"])
    assert pt.status_code == 409
    # adjacent (non-overlapping) is fine
    adj = client.post(f"/farmers/{f2['id']}/plots", json={"name": "d", "crop_type": "c", "acreage": 2.5, "geojson": _square(lat, lon + 0.0020, 0.0009)}, headers=users["agent2"])
    assert adj.status_code == 201

    # declared acreage must roughly match the drawn polygon
    lat2, lon2 = _next_latlon()
    bad = client.post(f"/farmers/{f['id']}/plots", json={"name": "e", "crop_type": "c", "acreage": 50, "geojson": _square(lat2, lon2, 0.0009)}, headers=users["agent"])
    assert bad.status_code == 422 and "acreage" in bad.json()["detail"]
    # self-intersecting bow-tie polygon
    bow = {"type": "Polygon", "coordinates": [[[lon2, lat2], [lon2 + 0.001, lat2 + 0.001], [lon2 + 0.001, lat2], [lon2, lat2 + 0.001], [lon2, lat2]]]}
    r = client.post(f"/farmers/{f['id']}/plots", json={"name": "f", "crop_type": "c", "acreage": 1, "geojson": bow}, headers=users["agent"])
    assert r.status_code == 422


# ---- evidence ----------------------------------------------------------------------------------
def test_evidence_upload_download_and_rules(client, users):
    _, _, log = _setup_log(client, users)
    url = f"/interventions/{log['id']}/evidence"
    r = client.post(url, files=_up("../../my photo.png"), headers=users["agent"])
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["filename"] == "my_photo.png" and ev["size_bytes"] == len(_png()) and len(ev["sha256"]) == 64

    got = client.get(f"{url}/{ev['id']}", headers=users["auditor"])
    assert got.status_code == 200 and got.content == _png() and got.headers["content-type"] == "image/png"
    assert client.get(url, headers=users["auditor"]).json()[0]["id"] == ev["id"]

    # isolation: another agent can't see or add evidence
    assert client.get(url, headers=users["agent2"]).status_code == 404
    assert client.post(url, files=_up(), headers=users["agent2"]).status_code == 404
    # type, size and role checks
    assert client.post(url, files=_up("x.exe", b"MZ", "application/x-msdownload"), headers=users["agent"]).status_code == 415
    assert client.post(url, files=_up(), headers=users["auditor"]).status_code == 403
    with patch("app.routers.interventions.settings.max_evidence_mb", 0):
        assert client.post(url, files=_up(), headers=users["agent"]).status_code == 413

    assert client.get(f"/plots/{log['plot_id']}/interventions", headers=users["agent"]).json()[0]["evidence_count"] == 1
    # no new evidence once reviewed
    client.post(f"/interventions/{log['id']}/approve", headers=users["auditor"])
    assert client.post(url, files=_up(), headers=users["agent"]).status_code == 409
    cert = client.get(f"/interventions/{log['id']}/certificate?format=json", headers=users["agent"]).json()
    assert cert["evidence_count"] == 1 and cert["methodology"].startswith("ILLUSTRATIVE")


def test_evidence_required_for_approval(client, users):
    _, _, log = _setup_log(client, users)
    with patch("app.routers.interventions.settings.require_evidence_for_approval", True):
        assert client.post(f"/interventions/{log['id']}/approve", headers=users["auditor"]).status_code == 422
    assert client.post(f"/interventions/{log['id']}/approve", headers=users["auditor"]).status_code == 200


# ---- user management / rate limiting -----------------------------------------------------------
def test_user_management(client, admin, users):
    listed = client.get("/users", headers=admin).json()
    assert {"agent@example.com", "admin@example.com"} <= {u["email"] for u in listed}
    assert client.get("/users", headers=users["agent"]).status_code == 403

    r = client.post("/users", json={"email": "temp@example.com", "password": "password123", "role": "field_agent"}, headers=admin)
    uid = r.json()["id"]
    tok = client.post("/auth/login", data={"username": "temp@example.com", "password": "password123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/auth/change-password", json={"current_password": "wrong", "new_password": "newpassword1"}, headers=h).status_code == 400
    assert client.post("/auth/change-password", json={"current_password": "password123", "new_password": "newpassword1"}, headers=h).status_code == 204
    assert client.post("/auth/login", data={"username": "temp@example.com", "password": "password123"}).status_code == 401
    # admin reset + deactivate (existing token stops working)
    assert client.patch(f"/users/{uid}", json={"password": "resetpass99"}, headers=admin).status_code == 200
    assert client.post("/auth/login", data={"username": "temp@example.com", "password": "resetpass99"}).status_code == 200
    assert client.patch(f"/users/{uid}", json={"is_active": False}, headers=admin).json()["is_active"] is False
    assert client.get("/auth/me", headers=h).status_code == 401
    # can't lock out the last admin / yourself
    me = client.get("/auth/me", headers=admin).json()
    assert client.patch(f"/users/{me['id']}", json={"is_active": False}, headers=admin).status_code == 409
    assert client.patch(f"/users/{me['id']}", json={"role": "auditor"}, headers=admin).status_code == 409


def test_login_rate_limit(client):
    from app.routers.auth import login_limiter

    login_limiter.reset()
    with patch("app.routers.auth.settings.rate_limit_login_per_minute", 3):
        codes = [client.post("/auth/login", data={"username": "nobody@example.com", "password": "x"}).status_code for _ in range(5)]
    login_limiter.reset()
    assert codes == [401, 401, 401, 429, 429]


# ---- methodology / storage / production checks / ndvi ------------------------------------------
def test_methodology_file_and_buffer(tmp_path):
    from app.models import Practice
    from app.services import carbon

    f = tmp_path / "m.json"
    f.write_text('{"name":"TEST","version":"2","per_acre_year":{"no_till":1.0,"cover_crop":0.5},"biochar_per_tonne":3,"tree_per_year":0.03,"buffer_pool_ratio":0.2}')
    with patch.object(carbon.settings, "methodology_file", str(f)):
        carbon.load_methodology.cache_clear()
        try:
            assert carbon.load_methodology().label == "TEST 2"
            assert carbon.estimate_co2e(Practice.no_till, 10, None) == 8.0  # 10 * 1.0 * (1 - 0.2)
        finally:
            carbon.load_methodology.cache_clear()


def test_local_storage_blocks_traversal(tmp_path):
    from app.services.storage import LocalStorage, StorageError

    s = LocalStorage(str(tmp_path))
    s.put("a/b.txt", b"hi", "text/plain")
    assert s.get("a/b.txt") == b"hi"
    with pytest.raises(StorageError):
        s.put("../escape.txt", b"x", "text/plain")


def test_production_guard():
    from app.main import check_production_settings, settings

    with patch.object(settings, "environment", "production"), patch.object(settings, "secret_key", "change-me-in-production"):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            check_production_settings()


def test_ndvi_endpoint(client, users):
    _, _, log = _setup_log(client, users)
    fake = {"source": "x", "before": {"mean_ndvi": 0.3}, "after": {"mean_ndvi": 0.5}, "delta": 0.2}
    with patch("app.routers.interventions.ndvi_change", return_value=fake):
        assert client.get(f"/interventions/{log['id']}/ndvi", headers=users["auditor"]).json()["delta"] == 0.2
        assert client.get(f"/interventions/{log['id']}/ndvi", headers=users["agent2"]).status_code == 404


def test_ndvi_scene_selection():
    from datetime import date

    from app.services import ndvi

    bbox = ndvi.plot_bbox(None, 10.0, 80.0, 5)
    assert bbox[0] < 80.0 < bbox[2] and bbox[1] < 10.0 < bbox[3]
    scene = {"id": "S2A", "properties": {"datetime": "2026-03-01T05:00:00Z", "eo:cloud_cover": 4.2}, "assets": {}}
    with patch.object(ndvi, "find_scene", side_effect=[scene, None]), patch.object(ndvi, "mean_ndvi", return_value=0.41):
        r = ndvi.ndvi_change(None, 10.0, 80.0, 5, date(2026, 3, 10))
    assert r["before"]["mean_ndvi"] == 0.41 and r["before"]["scene_date"] == "2026-03-01"
    assert r["after"] is None and r["delta"] is None
