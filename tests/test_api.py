"""End-to-end API: upload validation, async job, confirmation, analysis, summary, deletion."""
import time

import pytest


def wait(client, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("succeeded", "failed"):
            return j
        time.sleep(0.3)
    raise TimeoutError


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


@pytest.mark.parametrize("name,data,code", [
    ("report.exe", b"MZ\x90\x00", 400),
    ("report.png", b"%PDF-1.4 fake", 400),  # extension/content mismatch
    ("report.pdf", b"%PDF-1.4 broken", 400),  # unreadable PDF
    ("empty.png", b"", 400),
])
def test_upload_rejects_bad_files(client, name, data, code):
    r = client.post("/api/reports/upload", files={"file": (name, data)})
    assert r.status_code == code


def test_upload_rejects_oversized(client, monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "max_upload_mb", 0.001)
    r = client.post("/api/reports/upload", files={"file": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 5000)})
    assert r.status_code == 400 and "limit" in r.json()["detail"]


def test_full_flow(client, fixtures):
    data = open(fixtures["lft_lipid_pdf"], "rb").read()
    r = client.post("/api/reports/upload", files={"file": ("lft.pdf", data, "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file_stored"] is False
    job = wait(client, body["job_id"])
    assert job["status"] == "succeeded"
    rep = client.get(f"/api/reports/{body['report_id']}").json()
    assert rep["status"] == "awaiting_confirmation" and rep["analysis"] is None  # no analysis before confirmation
    ms = rep["extraction"]["measurements"]

    # duplicate detection
    r2 = client.post("/api/reports/upload", files={"file": ("lft.pdf", data, "application/pdf")})
    assert r2.status_code == 409

    # user corrects ALT and confirms
    edited = []
    for m in ms:
        m = {k: m.get(k) for k in ("key", "value", "reference_range", "original_value", "original_unit",
                                   "extraction_confidence", "source_line", "lab_flag", "lab_calculated")}
        if m["key"] == "alt":
            m["value"] = 95
        edited.append(m)
    c = client.put(f"/api/reports/{body['report_id']}/confirm",
                   json={"measurements": edited, "demographics": {"age": 52, "sex": "male"}})
    assert c.status_code == 200, c.text
    a = c.json()["analysis"]
    assert {"liver", "lipid"} <= set(a)
    alt = next(m for m in a["liver"]["measurements"] if m["key"] == "alt")
    assert alt["value"] == 95 and alt["origin"] == "manual"
    full = client.get(f"/api/reports/{body['report_id']}").json()
    assert [e["action"] for e in full["audit"]] == ["uploaded", "extracted", "confirmed"]
    assert full["audit"][-1]["detail"]["changes"][0]["key"] == "alt"

    s = client.get("/api/summary").json()
    assert s["overall_score"] is None and s["abnormal_values"]
    pdf = client.get("/api/summary/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(f"/api/reports/{body['report_id']}/download").content.startswith(b"%PDF")

    stats = client.get("/api/stats").json()
    assert stats["total_reports"] >= 1

    # deletion
    assert client.delete(f"/api/reports/{body['report_id']}").status_code == 200
    assert client.get(f"/api/reports/{body['report_id']}").status_code == 404


def test_confirm_rejects_implausible(client, fixtures):
    data = open(fixtures["echo_pdf"], "rb").read()
    body = client.post("/api/reports/upload", files={"file": ("echo.pdf", data)}).json()
    wait(client, body["job_id"])
    r = client.put(f"/api/reports/{body['report_id']}/confirm",
                   json={"measurements": [{"key": "ef", "value": 450}]})
    assert r.status_code == 422


def test_consented_storage_is_encrypted_and_deleted(client, fixtures):
    import os

    data = open(fixtures["cbc_png"], "rb").read()
    body = client.post("/api/reports/upload", files={"file": ("cbc.png", data)},
                       data={"consent_store_file": "true"}).json()
    assert body["file_stored"] is True
    wait(client, body["job_id"])
    from backend.database import Report, SessionLocal

    with SessionLocal() as db:
        path = db.get(Report, body["report_id"]).stored_path
    raw = open(path, "rb").read()
    assert data not in raw and not raw.startswith(b"\x89PNG")  # encrypted at rest
    client.delete(f"/api/reports/{body['report_id']}")
    assert not os.path.exists(path)


def test_manual_endpoints(client):
    r = client.post("/api/lipid/analyze", json={"measurements": [
        {"key": "total_cholesterol", "value": 5.2, "input_unit": "mmol/L"}, {"key": "hdl", "value": 40},
        {"key": "triglycerides", "value": 150}]})
    assert r.status_code == 200
    assert any(d["key"] == "ldl_estimated" for d in r.json()["derived"])
    assert client.post("/api/blood/analyze", json={"measurements": [{"key": "hemoglobin", "value": 99}]}).status_code == 422
    assert client.post("/api/blood/analyze", json={"measurements": [{"key": "not_a_test", "value": 1}]}).status_code == 422


def test_ecg_endpoints(client):
    r = client.get("/api/ecg/sample-signal")
    assert r.status_code == 200
    res = client.post("/api/ecg/signal", files={"file": ("s.csv", r.content)}, data={"mains_hz": "60"})
    assert res.status_code == 200, res.text
    assert res.json()["signal_quality"]["usable"]
    img = client.get("/api/ecg/sample-image").content
    res2 = client.post("/api/ecg/image", files={"file": ("strip.png", img)})
    assert res2.status_code == 200 and res2.json()["digitization"]["calibrated"]
    bad = client.post("/api/ecg/signal", files={"file": ("s.csv", b"a,b\nx,y\n")})
    assert bad.status_code == 422


def test_models_endpoint(client):
    ms = client.get("/api/models").json()
    assert {m["task"] for m in ms} >= {"liver", "ecg"}


def test_delete_all_requires_confirmation(client):
    assert client.delete("/api/reports").status_code == 400
    assert client.delete("/api/reports?confirm=true").status_code == 200
    assert client.get("/api/reports").json() == []
