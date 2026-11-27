"""Ordensleiste als ein Bild fürs Forum (27.11.2026).

Alle Orden eines Piloten (365 Tage) als ein PNG: kleines Badge am Band wie in der Statistik,
acht je Reihe -- rund 320 px breit, passt auf ein Handy, danach Umbruch.
"""
import io
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image

import app.main as main
from app.database import init_db

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _client(tmp_path, monkeypatch, orden):
    db = str(tmp_path / "o.db")
    init_db(db)
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(
        DB_PATH=db, CALLSIGN_PREFIX="FRS", SECRET_KEY="s", ADMIN_PASSWORD="p"))
    monkeypatch.setattr(main, "pilot_orden", lambda cid, days=30: orden)
    main._orden_bilder.clear()
    return TestClient(main.app)


def _sonder(n):
    return [{"art": "sonder", "event_id": None, "name": "Gebirgsflug Teil 4",
             "datum": f"2026-11-{16 - i:02d}T19:00:00Z", "sieger": False,
             "bild": "/static/orden/gebirgsflug-4.png"} for i in range(n)]


def test_ohne_orden_ein_unsichtbares_pixel(tmp_path, monkeypatch):
    # Im Forum soll kein kaputtes Bild stehen, wenn (noch) keine Orden da sind.
    res = _client(tmp_path, monkeypatch, []).get("/api/pilots/7/orden.png")
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(res.content)).size == (1, 1)


def test_eine_reihe_handybreit(tmp_path, monkeypatch):
    res = _client(tmp_path, monkeypatch, _sonder(3)).get("/api/pilots/7/orden.png")
    bild = Image.open(io.BytesIO(res.content))
    assert bild.mode == "RGBA"
    assert bild.size[0] == 3 * main._ORDEN_ZELLE
    assert bild.size[1] == main._ORDEN_HOEHE


def test_ab_dem_neunten_orden_neue_reihe(tmp_path, monkeypatch):
    res = _client(tmp_path, monkeypatch, _sonder(9)).get("/api/pilots/7/orden.png")
    bild = Image.open(io.BytesIO(res.content))
    assert bild.size == (8 * main._ORDEN_ZELLE, 2 * main._ORDEN_HOEHE)
    assert bild.size[0] <= 330                       # passt auf ein Handy


def test_etag_und_304(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, _sonder(2))
    a = c.get("/api/pilots/7/orden.png")
    assert a.headers["cache-control"] == "no-cache"
    b = c.get("/api/pilots/7/orden.png", headers={"if-none-match": a.headers["etag"]})
    assert b.status_code == 304


def test_immer_365_tage(tmp_path, monkeypatch):
    gesehen = []
    c = _client(tmp_path, monkeypatch, [])
    monkeypatch.setattr(main, "pilot_orden", lambda cid, days=30: gesehen.append(days) or [])
    c.get("/api/pilots/7/orden.png")
    assert gesehen == [365]


def test_kopierknopf_und_handbuch():
    assert "/api/pilots/${cid}/orden.png[/img]" in INDEX
    assert "Orden fürs Forum" in INDEX
    assert "Orden fürs Forum" in README


def test_auch_ohne_anmeldung_erreichbar(tmp_path, monkeypatch):
    # Das Forum lädt das Bild ohne FriesenRadar-Cookie (Cross-Site-<img>) -- wie die Badges.
    # Die JSON-Liste dahinter bleibt hinter der Anmeldung.
    c = _client(tmp_path, monkeypatch, _sonder(1))
    monkeypatch.setattr(main, "_forum_login_active_cached", lambda s: True)
    assert c.get("/api/pilots/7/orden.png").status_code == 200
    assert c.get("/api/pilots/7/orden").status_code == 401
    assert c.get("/api/pilots/7/orden.png.json").status_code == 401
