"""Das Forum-Badge der FriesenReddung und ihr Orden in der Statistik.

Ein Badge bekommt, wer nach dem Ende des Abends in der Bilanz steht: mit Zellen, die er als
Erster abgesucht hat, oder als der, der den Havaristen gefunden, aufgenommen oder eingeliefert
hat. Vor dem Ende gibt es keins -- sonst liesse sich ein Zwischenstand verewigen.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image

import app.main as main
from app.badge import render_reddung_badge
from app.database import (
    _REDDUNG_STAND_FASSUNG, create_reddung_event, get_connection, init_db, upsert_pilot,
    write_progress_snapshot,
)

_SEKTOR = dict(sued=53.54, west=6.95, nord=53.90, ost=7.55)


def _iso(dt): return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _img(b: bytes) -> Image.Image:
    return Image.open(BytesIO(b)).convert("RGBA")


# --- Das Bild ------------------------------------------------------------------------------

def test_das_badge_ist_rund_und_256_gross():
    im = _img(render_reddung_badge({"callsign": "FRS49", "aircraft": "EC35", "zellen": 12,
                                     "rollen": ["gefunden"], "event": "FriesenReddung",
                                     "date": "25.09.2026"}))
    assert im.size == (256, 256)
    assert im.getpixel((0, 0))[3] == 0
    assert im.getpixel((128, 128))[3] >= 250


def test_der_eigene_hintergrund_wird_benutzt():
    """Der SAR-Ring mit den orange-weissen Streifen, nicht die Bummel-Medaille."""
    from app import badge
    assert badge._load_bg("reddung_bg.png") is not None


def test_rollen_und_zellen_stehen_als_text_darunter():
    from app.badge import _reddung_zeilen
    assert _reddung_zeilen({"rollen": [], "zellen": 7}) == (None, "7 Zellen als Erster abgesucht")
    assert _reddung_zeilen({"rollen": ["gefunden", "aufgenommen", "eingeliefert"], "zellen": 1,
                            "icao": "EDWR"}) == (
        "GEFUNDEN! GEBORGEN!", "eingeliefert in EDWR, 1 Zelle als Erster")
    assert _reddung_zeilen({"rollen": ["aufgenommen", "eingeliefert"], "zellen": 0,
                            "icao": "EDWR"}) == ("GEBORGEN!", "eingeliefert in EDWR")


# --- Wer eins bekommt ----------------------------------------------------------------------

def _setup(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    init_db(db)
    monkeypatch.setattr(main, "get_settings",
                        lambda: SimpleNamespace(DB_PATH=db, CALLSIGN_PREFIX="FRS"))
    return db


def _reddung(conn, tage, je_pilot, **rollen):
    now = datetime.now(timezone.utc)
    dtstart, dtend = _iso(now - timedelta(days=tage, hours=2)), _iso(now - timedelta(days=tage))
    rid = create_reddung_event(conn, name="FriesenReddung Borkum", dtstart=dtstart, dtend=dtend,
                               **_SEKTOR)
    for spalte, cid in rollen.items():
        conn.execute(f"UPDATE reddung_events SET {spalte}_am=?, {spalte}_von=? WHERE id=?",
                     (dtend, cid, rid))
    if "eingeliefert" in rollen:
        conn.execute("UPDATE reddung_events SET eingeliefert_icao='EDWR' WHERE id=?", (rid,))
    treffer = {}
    for cid, n in je_pilot.items():
        for i in range(n):
            treffer[f"z{cid}_{i}"] = [cid, dtend]
    write_progress_snapshot(conn, "reddung", rid, {
        "v": _REDDUNG_STAND_FASSUNG, "bis": dtend, "treffer": treffer,
        "je_pilot": {str(c): n for c, n in je_pilot.items()}, "fund": None,
    }, dtend)
    return rid, dtstart, dtend


def _flug(conn, cid, callsign, typ, von, bis):
    conn.execute("INSERT INTO flights (cid, callsign, aircraft_short, logon_time, logoff_time, "
                 "duration_min) VALUES (?,?,?,?,?,?)", (cid, callsign, typ, von, bis, 90))


def test_daten_fuer_einen_sucher_mit_callsign_aus_dem_flug(tmp_path, monkeypatch):
    db = _setup(tmp_path, monkeypatch)
    conn = get_connection(db)
    upsert_pilot(conn, 7, "Pilot Sieben")
    rid, dtstart, dtend = _reddung(conn, 2, {7: 3}, gefunden=7)
    _flug(conn, 7, "FRS07", "EC35", dtstart, dtend)
    conn.commit()
    ev = main.get_reddung_event(conn, rid)
    d = main._reddung_badge_data(conn, ev, 7)
    conn.close()

    assert d["callsign"] == "FRS07" and d["aircraft"] == "EC35"
    assert d["zellen"] == 3 and d["rollen"] == ["gefunden"]
    assert d["event"] == "FriesenReddung Borkum"


def test_wer_nur_eingeliefert_hat_bekommt_auch_eins(tmp_path, monkeypatch):
    db = _setup(tmp_path, monkeypatch)
    conn = get_connection(db)
    rid, _, _ = _reddung(conn, 2, {8: 4}, gefunden=8, aufgenommen=9, eingeliefert=9)
    conn.commit()
    d = main._reddung_badge_data(conn, main.get_reddung_event(conn, rid), 9)
    conn.close()
    assert d["rollen"] == ["aufgenommen", "eingeliefert"] and d["zellen"] == 0
    assert d["icao"] == "EDWR"
    assert d["callsign"] == "CID 9"          # kein Flug im Fenster -> wie bei Bummel und Kutter


def test_ohne_beitrag_kein_badge(tmp_path, monkeypatch):
    db = _setup(tmp_path, monkeypatch)
    conn = get_connection(db)
    rid, _, _ = _reddung(conn, 2, {8: 4})
    conn.commit()
    with pytest.raises(HTTPException) as e:
        main._reddung_badge_data(conn, main.get_reddung_event(conn, rid), 7)
    conn.close()
    assert e.value.status_code == 404


def test_vor_dem_ende_gibt_es_kein_badge(tmp_path, monkeypatch):
    db = _setup(tmp_path, monkeypatch)
    conn = get_connection(db)
    now = datetime.now(timezone.utc)
    rid = create_reddung_event(conn, name="Laeuft", dtstart=_iso(now - timedelta(hours=1)),
                               dtend=_iso(now + timedelta(hours=1)), **_SEKTOR)
    conn.commit()
    conn.close()
    req = SimpleNamespace(headers={})
    with pytest.raises(HTTPException) as e:
        main.get_reddung_badge(req, rid, 7)
    assert e.value.status_code == 404


def test_das_badge_kommt_als_png(tmp_path, monkeypatch):
    db = _setup(tmp_path, monkeypatch)
    conn = get_connection(db)
    rid, _, _ = _reddung(conn, 2, {7: 3})
    conn.commit()
    conn.close()
    res = main.get_reddung_badge(SimpleNamespace(headers={}), rid, 7)
    assert res.media_type == "image/png" and res.body[:4] == b"\x89PNG"
    assert res.headers["ETag"]


# --- Der Orden ------------------------------------------------------------------------------

def test_die_reddung_steht_in_der_ordensleiste(tmp_path, monkeypatch):
    db = _setup(tmp_path, monkeypatch)
    conn = get_connection(db)
    rid, dtstart, _ = _reddung(conn, 4, {7: 3, 8: 1})
    laeuft = create_reddung_event(conn, name="Laeuft", dtstart=_iso(datetime.now(timezone.utc)),
                                  dtend=_iso(datetime.now(timezone.utc) + timedelta(hours=2)),
                                  **_SEKTOR)
    conn.commit()
    conn.close()

    orden = main.pilot_orden(7, days=30)
    assert [(o["art"], o["event_id"]) for o in orden] == [("reddung", rid)]
    assert orden[0]["bild"] == f"/api/reddung/events/{rid}/badge/7.png"
    assert orden[0]["datum"] == dtstart
    assert main.pilot_orden(99, days=30) == []
    assert laeuft != rid


# --- Anzeige ----------------------------------------------------------------------------

import json
import re
import shutil
import subprocess
from pathlib import Path

_WURZEL = Path(__file__).resolve().parents[1]
_INDEX = (_WURZEL / "app" / "static" / "index.html").read_text(encoding="utf-8")
_README = (_WURZEL / "README.md").read_text(encoding="utf-8")
_NODE = shutil.which("node")


def _funktion(name: str) -> str:
    m = re.search(rf"^(async )?function {re.escape(name)}\(", _INDEX, flags=re.M)
    assert m, f"function {name} fehlt"
    return _INDEX[m.start():_INDEX.index("\n}\n", m.start()) + 3]


def _node(quelltext: str, ausdruck: str):
    skript = quelltext + "\nconsole.log(JSON.stringify(" + ausdruck + "));"
    erg = subprocess.run([_NODE, "-e", skript], capture_output=True, text=True, timeout=20)
    assert erg.returncode == 0, erg.stderr
    return json.loads(erg.stdout.strip().splitlines()[-1])


def _bilanz(vorbei: bool) -> str:
    quelle = ("function escHtml(s){return String(s);}\nfunction pilotLinkHtml(s){return String(s);}\nfunction icon(){return '';}\n"
              "function _fmtMin(m){return m+' min';}\n"
              + "".join(_funktion(n) for n in (
                  "_reddungZeitfenster", "_reddungBalken", "_reddungMarkenHtml",
                  "_reddungHatBadge", "_reddungBadgeLinks", "_reddungBilanzHtml")))
    r = {"id": 4, "name": "X", "dtstart": "2026-09-25T18:00:00Z", "dtend": "2026-09-25T19:30:00Z",
         "laeuft": not vorbei, "vorbei_seit_s": 3600 if vorbei else None,
         "stand": {"anteil": 0.5, "abgedeckt": 5, "zellen": 10, "kante_km": 1.0,
                   "flaeche_km2": 5.0,
                   "je_pilot": [{"cid": 7, "name": "Sieben", "zellen": 5},
                                {"cid": 8, "name": "Nur Doppelt", "zellen": 0}]}}
    return _node(quelle, f"_reddungBilanzHtml({json.dumps(r)})")


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_die_bilanz_verlinkt_die_badges_erst_nach_dem_ende():
    assert "/badge/" not in _bilanz(vorbei=False)
    html = _bilanz(vorbei=True)
    assert "/api/reddung/events/4/badge/7.png" in html
    assert "copyReddungBadgeCode(4, 7, this)" in html
    assert "/badge/8.png" not in html          # keine Zelle als Erster, keine Rolle


def test_im_kniebrett_gibt_es_keine_kopierknoepfe_der_reddung():
    """Im Sim gibt es keine Zwischenablage -- wie bei Bummel und Kutter ausgeblendet."""
    for name in ("copyReddungShareHeader", "copyReddungForumText", "copyReddungBadgeCode"):
        assert f'html.vr-panel [onclick*="{name}"]' in _INDEX, name


def test_die_readme_beschreibt_das_badge_und_den_orden():
    reddung = _README[_README.index("## 🚨 FriesenReddung"):_README.index("## 🔧 Verwaltung")]
    assert "Badge" in reddung
    statistik = _README[_README.index("### 📊 Statistiken"):_README.index("Einzelflüge können aus zwei Quellen")]
    assert "FriesenReddung" in statistik[statistik.index("**Orden**"):]
