"""Badge-Sets: eigene Motive für Kutter, Bummel und Reddung (Nutzer 31.10.2026).

Ein Set hat einen Namen und zwei Bilder, Teilnehmer und Sieger. Der Bummel kennt beide Rollen,
Kutter und Reddung nur Teilnehmer. Die Bilder liegen als BLOB in der Datenbank, wie die
Musterfotos: Das nächtliche Backup sichert nur die Datenbank.
"""
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main
from app import database as db
from app.auth import ADMIN_COOKIE, CONFIRM_COOKIE, make_admin_token, make_confirm_token
from app.badge import (motiv_aufbereiten, render_kutter_badge, render_medal,
                       render_reddung_badge, render_winner_badge)

SECRET = "s" * 32
PW = "pw"
HIMMEL = (120, 190, 250)


def _png(farbe=HIMMEL, groesse=(400, 400), modus="RGB"):
    buf = BytesIO()
    Image.new(modus, groesse, farbe).save(buf, format="PNG")
    return buf.getvalue()


def _schachbrett(n=400, rand=20):
    """Wie das hochgeladene Motiv: Kreis ohne Transparenz, das Schachbrett ist eingebrannt."""
    img = Image.new("RGB", (n, n), (200, 200, 200))
    px = img.load()
    for x in range(n):
        for y in range(n):
            if (x // 16 + y // 16) % 2:
                px[x, y] = (130, 130, 130)
            if (x - n / 2) ** 2 + (y - n / 2) ** 2 < (n / 2 - rand) ** 2:
                px[x, y] = HIMMEL
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _bild(png):
    return Image.open(BytesIO(png)).convert("RGBA")


@pytest.fixture
def conn(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    c = db.get_connection(p)
    yield c
    c.close()


# --- Aufbereiten ---------------------------------------------------------------------------

def test_kein_bild_wird_abgelehnt():
    with pytest.raises(ValueError):
        motiv_aufbereiten(b"das ist kein bild")


def test_ein_rechteck_wird_mittig_quadratisch():
    assert _bild(motiv_aufbereiten(_png(groesse=(800, 400)))).size == (768, 768)


def test_ein_eingebranntes_schachbrett_faellt_weg():
    aus = _bild(motiv_aufbereiten(_schachbrett()))
    # Die Ecke des Quadrats liegt noch außerhalb des Kreises, aber der Rand des Kreises sitzt
    # jetzt am Bildrand: Die Mitte der Oberkante ist Motiv, nicht Schachbrett.
    r, g, b, _ = aus.getpixel((384, 6))
    assert abs(b - HIMMEL[2]) < 12 and b - r > 60


def test_transparenz_bestimmt_den_ausschnitt():
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    img.paste((*HIMMEL, 255), (100, 100, 300, 300))
    buf = BytesIO()
    img.save(buf, format="PNG")
    assert _bild(motiv_aufbereiten(buf.getvalue())).getpixel((10, 384))[:3] == HIMMEL


# --- Datenbank ------------------------------------------------------------------------------

def test_set_anlegen_und_lesen(conn):
    sid = db.create_badge_set(conn, "Geburtstag 2026")
    db.set_badge_set_bild(conn, sid, "teilnehmer", _png())
    conn.commit()
    s = db.list_badge_sets(conn)[0]
    assert s["name"] == "Geburtstag 2026" and s["hat_teilnehmer"] and not s["hat_sieger"]
    assert "teilnehmer_bild" not in s, "die Liste trägt keine Bilddaten"


def test_ohne_sieger_bild_gilt_das_teilnehmer_bild(conn):
    sid = db.create_badge_set(conn, "X")
    png = _png()
    db.set_badge_set_bild(conn, sid, "teilnehmer", png)
    assert db.badge_set_bild(conn, sid, "sieger") == png


def test_ein_eigenes_sieger_bild_gilt_nur_fuer_den_sieger(conn):
    sid = db.create_badge_set(conn, "X")
    t, s = _png(), _png((200, 50, 50))
    db.set_badge_set_bild(conn, sid, "teilnehmer", t)
    db.set_badge_set_bild(conn, sid, "sieger", s)
    assert db.badge_set_bild(conn, sid, "sieger") == s
    assert db.badge_set_bild(conn, sid, "teilnehmer") == t


def test_ohne_set_gibt_es_kein_motiv(conn):
    assert db.badge_motiv(conn, {"badge_set_id": None}) == (None, "")
    assert db.badge_motiv(conn, {"badge_set_id": 999}) == (None, "")


def test_der_motiv_schluessel_aendert_sich_mit_dem_bild(conn):
    sid = db.create_badge_set(conn, "X")
    db.set_badge_set_bild(conn, sid, "teilnehmer", _png())
    _, vorher = db.badge_motiv(conn, {"badge_set_id": sid})
    db.set_badge_set_bild(conn, sid, "teilnehmer", _png((10, 200, 10)))
    _, nachher = db.badge_motiv(conn, {"badge_set_id": sid})
    assert vorher and vorher != nachher


def test_ein_benutztes_set_laesst_sich_nicht_loeschen(conn):
    sid = db.create_badge_set(conn, "X")
    eid = db.create_transport_event(conn, name="Kutter", destination="EDWG",
                                    dtstart="2026-11-25T19:00:00Z", dtend="2026-11-25T21:00:00Z",
                                    cargo=[{"name": "A", "target_kg": 1, "departure": "EDWY"}])
    db.update_transport_event(conn, eid, badge_set_id=sid)
    assert db.badge_set_verwendung(conn, sid) == ["Kutter"]
    with pytest.raises(ValueError):
        db.delete_badge_set(conn, sid)
    db.update_transport_event(conn, eid, badge_set_id=None)
    db.delete_badge_set(conn, sid)
    assert db.list_badge_sets(conn) == []


def test_alle_drei_event_arten_tragen_das_set(conn):
    sid = db.create_badge_set(conn, "X")
    rid = db.create_bummel_race(conn, name="B", route="EDWG,EDWY", dtstart="2026-11-25T19:00:00Z",
                                dtend="2026-11-25T21:00:00Z")
    db.update_bummel_race(conn, rid, badge_set_id=sid)
    assert db.get_bummel_race(conn, rid)["badge_set_id"] == sid
    assert [r["badge_set_id"] for r in db.list_bummel_races(conn)] == [sid]
    eid = db.create_reddung_event(conn, name="R", dtstart="2026-11-25T19:00:00Z", sued=53, west=7,
                                  nord=54, ost=8, badge_set_id=sid)
    assert db.get_reddung_event(conn, eid)["badge_set_id"] == sid
    assert set(db.badge_set_verwendung(conn, sid)) == {"B", "R"}


# --- Zeichnen -------------------------------------------------------------------------------

KUTTER = {"callsign": "FRS49", "aircraft": "C172", "stolen_kg": 0.0, "sunk_kg": 0.0,
          "team_total_kg": 1373.0, "team_target_kg": 1373.0, "event": "Backe backe Kuchen 20.",
          "date": "25.11.2026"}
BUMMEL = {"callsign": "FRS49", "name": "Tobias", "aircraft": "C172", "total_min": 90,
          "delta_sec": 12, "complete": True, "event": "Bummel", "date": "25.11.2026"}
REDDUNG = {"callsign": "FRS49", "aircraft": "C172", "zellen": 3, "rollen": ["gefunden"],
           "icao": None, "event": "Reddung", "date": "25.11.2026"}


@pytest.mark.parametrize("zeichnen, d", [
    (render_kutter_badge, KUTTER), (render_kutter_badge, {**KUTTER, "sunk_kg": 80.0}),
    (render_medal, BUMMEL), (render_winner_badge, BUMMEL), (render_reddung_badge, REDDUNG),
])
def test_ein_motiv_ersetzt_den_hintergrund(zeichnen, d):
    png = motiv_aufbereiten(_png())
    mit = _bild(zeichnen({**d, "motiv": png}))
    ohne = _bild(zeichnen(d))
    assert mit.size == ohne.size == (256, 256)
    # Über dem Text: Himmel aus dem Motiv statt des Standard-Hintergrunds.
    assert mit.getpixel((128, 30))[:3] == pytest.approx(HIMMEL, abs=6)
    assert mit.tobytes() != ohne.tobytes()


def test_ein_kaputtes_motiv_faellt_auf_den_standard_zurueck():
    assert render_kutter_badge({**KUTTER, "motiv": b"kaputt"}) == render_kutter_badge(KUTTER)


# --- Admin-Schnittstelle --------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(
        DB_PATH=p, SECRET_KEY=SECRET, ADMIN_PASSWORD=PW, CALLSIGN_PREFIX="FRS"))
    c = TestClient(main.app)
    c.cookies.update({ADMIN_COOKIE: make_admin_token(SECRET, PW)})
    return c


def test_ohne_anmeldung_geht_nichts(tmp_path, monkeypatch, client):
    client.cookies.clear()
    assert client.get("/api/admin/badge-sets").status_code == 401
    assert client.post("/api/admin/badge-sets", json={"name": "X"}).status_code == 401


def test_set_ueber_den_admin_anlegen_und_bild_hochladen(client):
    sid = client.post("/api/admin/badge-sets", json={"name": "Geburtstag"}).json()["id"]
    r = client.post(f"/api/admin/badge-sets/{sid}/bild/teilnehmer",
                    files={"file": ("m.png", _schachbrett(), "image/png")})
    assert r.status_code == 200
    s = client.get("/api/admin/badge-sets").json()[0]
    assert s["hat_teilnehmer"] is True and s["hat_sieger"] is False
    bild = client.get(f"/api/admin/badge-sets/{sid}/bild/teilnehmer.png")
    assert bild.status_code == 200 and _bild(bild.content).size == (768, 768)
    v = client.get(f"/api/admin/badge-sets/{sid}/vorschau/teilnehmer.png")
    assert v.status_code == 200 and _bild(v.content).size == (256, 256)
    assert client.get(f"/api/admin/badge-sets/{sid}/vorschau/sieger.png").status_code == 200


def test_kein_bild_und_falsche_rolle_werden_abgelehnt(client):
    sid = client.post("/api/admin/badge-sets", json={"name": "X"}).json()["id"]
    assert client.post(f"/api/admin/badge-sets/{sid}/bild/teilnehmer",
                       files={"file": ("m.png", b"nein", "image/png")}).status_code == 400
    assert client.post(f"/api/admin/badge-sets/{sid}/bild/chef",
                       files={"file": ("m.png", _png(), "image/png")}).status_code == 404


def test_umbenennen_und_leerer_name(client):
    sid = client.post("/api/admin/badge-sets", json={"name": "X"}).json()["id"]
    assert client.post(f"/api/admin/badge-sets/{sid}", json={"name": "Y"}).status_code == 200
    assert client.get("/api/admin/badge-sets").json()[0]["name"] == "Y"
    assert client.post("/api/admin/badge-sets", json={"name": "  "}).status_code == 400


def test_loeschen_verlangt_die_bestaetigung_und_ein_freies_set(client):
    sid = client.post("/api/admin/badge-sets", json={"name": "X"}).json()["id"]
    assert client.delete(f"/api/admin/badge-sets/{sid}").status_code == 403
    import time
    client.cookies.update({CONFIRM_COOKIE: make_confirm_token(SECRET, PW, int(time.time()) + 300)})
    assert client.delete(f"/api/admin/badge-sets/{sid}").status_code == 200


def test_ein_unbekanntes_set_am_event_wird_abgelehnt(client):
    body = {"name": "K", "destination": "EDWG", "dtstart": "2026-11-25T19:00:00Z",
            "dtend": "2026-11-25T21:00:00Z", "badge_set_id": 999,
            "cargo": [{"name": "A", "target_kg": 1, "departure": "EDWY"}]}
    assert client.post("/api/admin/transport/events", json=body).status_code == 400


def test_kutter_speichert_das_set_und_laesst_es_wieder_los(client):
    sid = client.post("/api/admin/badge-sets", json={"name": "X"}).json()["id"]
    body = {"name": "K", "destination": "EDWG", "dtstart": "2026-11-25T19:00:00Z",
            "dtend": "2026-11-25T21:00:00Z", "badge_set_id": sid,
            "cargo": [{"name": "A", "target_kg": 1, "departure": "EDWY"}]}
    eid = client.post("/api/admin/transport/events", json=body).json()["id"]
    ev = next(e for e in client.get("/api/admin/transport/events").json() if e["id"] == eid)
    assert ev["badge_set_id"] == sid
    assert client.post(f"/api/admin/transport/events/{eid}", json={"badge_set_id": None}).status_code == 200
    ev = next(e for e in client.get("/api/admin/transport/events").json() if e["id"] == eid)
    assert ev["badge_set_id"] is None


def test_bummel_speichert_das_set(client):
    sid = client.post("/api/admin/badge-sets", json={"name": "X"}).json()["id"]
    rid = client.post("/api/admin/bummel/races", json={
        "name": "B", "route": "EDWG,EDWY", "dtstart": "2026-11-25T19:00:00Z",
        "dtend": "2026-11-25T21:00:00Z", "badge_set_id": sid}).json()["id"]
    assert client.post(f"/api/admin/bummel/races/{rid}", json={"badge_set_id": None}).status_code == 200


REDDUNG_KOERPER = {"name": "R", "dtstart": "2026-11-25T19:00:00Z", "dtend": "2026-11-25T21:00:00Z",
                   "sued": 53.5, "nord": 53.8, "west": 7.0, "ost": 7.5}


def test_reddung_speichert_das_set_ohne_die_abdeckung_neu_zu_rechnen(client):
    sid = client.post("/api/admin/badge-sets", json={"name": "X"}).json()["id"]
    r = client.post("/api/admin/reddung/events", json={**REDDUNG_KOERPER, "badge_set_id": sid})
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    assert client.post(f"/api/admin/reddung/events/{eid}", json={"badge_set_id": None}).status_code == 200
    assert client.post(f"/api/admin/reddung/events/{eid}", json={"badge_set_id": 999}).status_code == 400
    assert client.post("/api/admin/reddung/events",
                       json={**REDDUNG_KOERPER, "badge_set_id": 999}).status_code == 400


# --- Oberfläche -----------------------------------------------------------------------------

ADMIN = open(main.__file__.replace("main.py", "static/admin.html"), encoding="utf-8").read()


@pytest.mark.parametrize("feld", ["nr-badge-set", "ke-badge-set", "rd-badge-set"])
def test_jedes_formular_hat_die_auswahl(feld):
    assert f'<select id="{feld}"' in ADMIN


def test_die_bummel_bearbeitung_hat_die_auswahl():
    assert "edit-badge-set-${r.id}" in ADMIN


def test_es_gibt_den_bereich_fuer_die_sets():
    assert 'data-typ="badges"' in ADMIN and 'id="typ-badges"' in ADMIN
