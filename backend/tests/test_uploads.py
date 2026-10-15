from pathlib import Path

from app.config import settings

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def make_expense(client, auth):
    r = await client.post("/expenses", json={"title": "Lunch", "amount": "9.99"}, headers=auth)
    return r.json()["id"]


async def test_upload_serve_replace_and_delete(client, auth):
    eid = await make_expense(client, auth)
    r = await client.post(f"/expenses/{eid}/receipt", files={"file": ("r.png", PNG, "image/png")}, headers=auth)
    assert r.status_code == 200
    url = r.json()["receipt_url"]
    assert url.startswith("/uploads/") and url.endswith(".png")
    assert "receipt_filename" not in r.json()  # internal name is hidden

    served = await client.get(url)  # static file serving
    assert served.status_code == 200 and served.content == PNG

    first_file = Path(settings.upload_dir) / url.split("/")[-1]
    r2 = await client.post(f"/expenses/{eid}/receipt", files={"file": ("again.png", PNG, "image/png")}, headers=auth)
    assert r2.json()["receipt_url"] != url and not first_file.exists()  # old file removed

    await client.delete(f"/expenses/{eid}", headers=auth)
    assert not (Path(settings.upload_dir) / r2.json()["receipt_url"].split("/")[-1]).exists()


async def test_rejects_wrong_type_fake_content_and_empty(client, auth):
    eid = await make_expense(client, auth)
    url = f"/expenses/{eid}/receipt"
    r = await client.post(url, files={"file": ("x.exe", b"MZ...", "application/octet-stream")}, headers=auth)
    assert r.status_code == 415
    r = await client.post(url, files={"file": ("x.png", b"this is not a png", "image/png")}, headers=auth)
    assert r.status_code == 415  # header says PNG, bytes say otherwise
    r = await client.post(url, files={"file": ("x.png", b"", "image/png")}, headers=auth)
    assert r.status_code == 400


async def test_rejects_oversized_file(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)  # 0 MB limit -> anything is too big
    eid = await make_expense(client, auth)
    r = await client.post(f"/expenses/{eid}/receipt", files={"file": ("x.png", PNG, "image/png")}, headers=auth)
    assert r.status_code == 413
