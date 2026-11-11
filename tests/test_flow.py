import itertools
from unittest.mock import patch

_loc = itertools.count()  # every test plot gets its own spot so overlap detection doesn't fire


def _next_latlon():
    return 10.0 + next(_loc) * 0.05, 80.0


def _square(lat, lon, d):
    return {"type": "Polygon", "coordinates": [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]]}


def _setup_log(client, users, practice="no_till", quantity=None):
    f = client.post("/farmers", json={"name": "Asha", "village": "Rampur"}, headers=users["agent"]).json()
    lat, lon = _next_latlon()
    p = client.post(
        f"/farmers/{f['id']}/plots",
        json={"name": "North field", "crop_type": "wheat", "acreage": 5, "latitude": lat, "longitude": lon},
        headers=users["agent"],
    ).json()
    body = {"practice": practice, "performed_on": "2026-05-01"}
    if quantity:
        body["quantity"] = quantity
    log = client.post(f"/plots/{p['id']}/interventions", json=body, headers=users["agent"]).json()
    return f, p, log


def test_auth_required_and_roles(client, users):
    assert client.get("/farmers").status_code == 401
    # auditors cannot onboard farmers
    assert client.post("/farmers", json={"name": "x"}, headers=users["auditor"]).status_code == 403
    # agents cannot approve
    _, _, log = _setup_log(client, users)
    assert client.post(f"/interventions/{log['id']}/approve", headers=users["agent"]).status_code == 403


def test_approval_triggers_pipeline(client, users):
    f, _, log = _setup_log(client, users)
    assert log["status"] == "pending"

    r = client.post(f"/interventions/{log['id']}/approve", json={"notes": "ok"}, headers=users["auditor"])
    assert r.status_code == 200 and r.json()["status"] == "approved"

    # no_till: 0.40 tCO2e/acre * 5 acres = 2.0 t; payout = 2.0 * 15 * 0.7 = 21.0
    ledger = client.get(f"/farmers/{f['id']}/ledger", headers=users["agent"]).json()
    assert ledger["total_co2e_tonnes"] == 2.0
    assert ledger["total_amount_usd"] == 21.0

    pdf = client.get(f"/interventions/{log['id']}/certificate", headers=users["agent"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    js = client.get(f"/interventions/{log['id']}/certificate?format=json", headers=users["agent"]).json()
    assert js["co2e_tonnes"] == 2.0

    # cannot approve twice
    assert client.post(f"/interventions/{log['id']}/approve", headers=users["auditor"]).status_code == 409


def test_task_is_idempotent(client, users):
    from app.tasks import process_approved_intervention

    f, _, log = _setup_log(client, users, "biochar", 2)
    client.post(f"/interventions/{log['id']}/approve", headers=users["auditor"])
    assert process_approved_intervention(log["id"]).get("skipped")  # second run is a no-op
    ledger = client.get(f"/farmers/{f['id']}/ledger", headers=users["auditor"]).json()
    assert len(ledger["entries"]) == 1 and ledger["total_co2e_tonnes"] == 5.0


def test_rejected_log_creates_no_credit(client, users):
    f, _, log = _setup_log(client, users)
    assert client.post(f"/interventions/{log['id']}/reject", headers=users["auditor"]).json()["status"] == "rejected"
    assert client.get(f"/farmers/{f['id']}/ledger", headers=users["agent"]).json()["entries"] == []


def test_agent_isolation(client, users):
    f, p, _ = _setup_log(client, users)
    assert client.get(f"/farmers/{f['id']}", headers=users["agent2"]).status_code == 404
    assert client.get(f"/plots/{p['id']}", headers=users["agent2"]).status_code == 404


def test_validation(client, users):
    f = client.post("/farmers", json={"name": "B"}, headers=users["agent"]).json()
    # no location at all
    r = client.post(f"/farmers/{f['id']}/plots", json={"name": "p", "crop_type": "c", "acreage": 1}, headers=users["agent"])
    assert r.status_code == 422
    # GeoJSON polygon -> centroid derived
    lat, lon = _next_latlon()
    poly = _square(lat, lon, 0.0009)  # ~100 m square, ~2.5 acres
    r = client.post(f"/farmers/{f['id']}/plots", json={"name": "p", "crop_type": "c", "acreage": 2.5, "geojson": poly}, headers=users["agent"])
    assert r.status_code == 201 and lat < r.json()["latitude"] < lat + 0.0009
    # biochar requires quantity
    pid = r.json()["id"]
    r = client.post(f"/plots/{pid}/interventions", json={"practice": "biochar", "performed_on": "2026-01-01"}, headers=users["agent"])
    assert r.status_code == 422


def test_weather_endpoint(client, users):
    _, p, _ = _setup_log(client, users)
    fake = {"properties": {"parameter": {"PRECTOTCORR": {"20260101": 2.0, "20260102": 4.0}, "T2M": {"20260101": 20, "20260102": 22}, "GWETROOT": {"20260101": 0.4, "20260102": -999}}}}

    class Resp:
        def raise_for_status(self): ...
        def json(self): return fake

    with patch("app.services.weather.httpx.get", return_value=Resp()):
        r = client.get(f"/plots/{p['id']}/weather?start=2026-01-01&end=2026-01-02", headers=users["agent"])
    assert r.status_code == 200
    s = r.json()["summary"]
    assert s["total_precipitation_mm"] == 6.0 and s["root_zone_soil_wetness"] == 0.4
