"""GET /api/pilots/{cid}/orden — die Ordensleiste in den Statistik-Details eines Piloten.

Ein Orden steht genau dort, wo es auch das Forum-Badge gibt: Bummel erst nach der Enthuellung,
Kutter erst nach der Feierabend-Bilanz und nur mit bewegter Fracht. Neueste zuerst, begrenzt
auf den Zeitraum der Statistik (30/90/365 Tage).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import app.main as main
from app.database import (
    get_connection, init_db, create_transport_event, set_transport_summarized,
    write_progress_snapshot, upsert_calendar_bummel_race, list_bummel_races,
    set_bummel_revealed,
)


def _iso(dt): return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _setup(tmp_path, monkeypatch):
    db = str(tmp_path / "t.db")
    init_db(db)
    monkeypatch.setattr(main, "get_settings",
                        lambda: SimpleNamespace(DB_PATH=db, CALLSIGN_PREFIX="FRS"))
    return db


def _kutter(conn, name, tage, teilnehmer, *, abgeschlossen=True, badge_name=None):
    dtend = _iso(datetime.now(timezone.utc) - timedelta(days=tage))
    dtstart = _iso(datetime.now(timezone.utc) - timedelta(days=tage, hours=2))
    eid = create_transport_event(conn, name=name, route="EDWG,EDXH",
                                 dtstart=dtstart, dtend=dtend, destination="EDXH")
    if badge_name:
        conn.execute("UPDATE transport_events SET badge_name=? WHERE id=?", (badge_name, eid))
    if abgeschlossen:
        set_transport_summarized(conn, eid, dtend)
        write_progress_snapshot(conn, "kutter", eid, {
            "flight_count": len(teilnehmer), "total_kg": 100.0, "participants": teilnehmer,
            "losses": [], "flights": [], "cargo": [], "route": ["EDWG", "EDXH"],
            "destination": "EDXH", "target_kg": None, "loaded_count": 1,
        }, dtend)
    return eid, dtstart


def _bummel(conn, uid, tage, complete, incomplete=(), *, enthuellt=True):
    now = datetime.now(timezone.utc)
    dtend = _iso(now - timedelta(days=tage))
    dtstart = _iso(now - timedelta(days=tage, hours=3))
    upsert_calendar_bummel_race(conn, {
        "uid": uid, "summary": f"FriesenBummel {uid}", "route": "EDWF,EDWG",
        "dtstart": dtstart, "dtend": dtend,
    })
    conn.commit()
    rid = next(r["id"] for r in list_bummel_races(conn) if r["dtstart"] == dtstart)
    if enthuellt:
        set_bummel_revealed(conn, rid, dtend)
    write_progress_snapshot(conn, "bummel", rid, {
        "id": rid, "participant_count": len(complete) + len(incomplete),
        "count": len(complete), "average_min": 60.0,
        "complete": list(complete), "incomplete": list(incomplete),
        "route": ["EDWF", "EDWG"],
    }, dtend)
    return rid, dtstart


def test_orden_aus_kutter_und_bummel_neueste_zuerst(tmp_path, monkeypatch):
    db = _setup(tmp_path, monkeypatch)
    conn = get_connection(db)
    k_alt, k_alt_start = _kutter(conn, "Nachschub", 20, [{"cid": 7, "contributed": True}])
    rid, b_start = _bummel(conn, "b1", 10, [{"cid": 7, "rank": 1}])
    k_neu, k_neu_start = _kutter(conn, "Krabben", 3, [{"cid": 7}], badge_name="Krabbenkutter")
    conn.commit()
    conn.close()

    orden = main.pilot_orden(7, days=30)

    assert [o["art"] for o in orden] == ["kutter", "bummel", "kutter"]
    assert [o["datum"] for o in orden] == [k_neu_start, b_start, k_alt_start]
    assert orden[0]["name"] == "Krabbenkutter"            # Kurzname wie auf dem Badge
    assert orden[0]["bild"] == f"/api/transport/event/{k_neu}/badge/7.png"
    assert orden[1]["bild"] == f"/api/bummel/race/{rid}/badge/7.png"
    assert orden[1]["sieger"] is True
    assert orden[2]["sieger"] is False


def test_orden_nur_fuer_teilnehmer_mit_badge(tmp_path, monkeypatch):
    db = _setup(tmp_path, monkeypatch)
    conn = get_connection(db)
    # Kutter: nur geladen und zurueckgegeben -> kein Badge, also kein Orden
    _kutter(conn, "Leerfahrt", 2, [{"cid": 7, "contributed": False}])
    # Kutter ohne Feierabend-Bilanz -> noch kein Badge
    _kutter(conn, "Laeuft noch", 1, [{"cid": 7}], abgeschlossen=False)
    # Bummel laeuft noch, ist also nicht enthuellt (nach dtend enthuellt er sich von selbst)
    _bummel(conn, "b2", -0.05, [{"cid": 7, "rank": 1}], enthuellt=False)
    # Bummel, in dem ein anderer flog
    _bummel(conn, "b3", 4, [{"cid": 8, "rank": 1}])
    # unvollstaendig geflogen gibt trotzdem ein Badge (Medaille)
    rid, _ = _bummel(conn, "b4", 5, [{"cid": 8, "rank": 1}], [{"cid": 7}])
    conn.commit()
    conn.close()

    orden = main.pilot_orden(7, days=30)

    assert len(orden) == 1
    assert orden[0]["bild"] == f"/api/bummel/race/{rid}/badge/7.png"
    assert orden[0]["sieger"] is False


def test_orden_haengen_am_zeitraum(tmp_path, monkeypatch):
    db = _setup(tmp_path, monkeypatch)
    conn = get_connection(db)
    _kutter(conn, "Neu", 5, [{"cid": 7}])
    _kutter(conn, "Mittel", 60, [{"cid": 7}])
    _kutter(conn, "Alt", 200, [{"cid": 7}])
    conn.commit()
    conn.close()

    assert [o["name"] for o in main.pilot_orden(7, days=30)] == ["Neu"]
    assert [o["name"] for o in main.pilot_orden(7, days=90)] == ["Neu", "Mittel"]
    assert [o["name"] for o in main.pilot_orden(7, days=365)] == ["Neu", "Mittel", "Alt"]
    # Unbekannter Zeitraum faellt wie bei den Spezial-Events auf 30 Tage zurueck
    assert [o["name"] for o in main.pilot_orden(7, days=12)] == ["Neu"]


# --- Anzeige in den Statistik-Details ---------------------------------------------------------

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")
_README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
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


_ORDEN = [
    {"art": "kutter", "event_id": 5, "name": "Krabbenkutter", "datum": "2026-09-20T18:00:00Z",
     "sieger": False, "bild": "/api/transport/event/5/badge/7.png"},
    {"art": "bummel", "event_id": 2, "name": "Bummel <Nord>", "datum": "2026-09-07T18:00:00Z",
     "sieger": True, "bild": "/api/bummel/race/2/badge/7.png"},
]


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_ordensleiste_zeigt_die_orden_in_der_gelieferten_reihenfolge():
    js = "\n".join(_funktion(n) for n in ("escHtml", "_fmtEventDate", "_ordenHtml"))
    html = _node(js, f"_ordenHtml({json.dumps(_ORDEN)})")
    assert html.index("/api/transport/event/5/badge/7.png") < html.index("/api/bummel/race/2/badge/7.png")
    assert "orden-band-kutter" in html and "orden-band-bummel" in html
    assert "orden-band-sieger" in html                   # der Bummel-Sieger bekommt sein Band
    assert "Bummel &lt;Nord&gt;" in html                 # Namen kommen escaped an
    assert "20.09.2026" in html


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_ohne_orden_bleibt_die_leiste_weg():
    js = "\n".join(_funktion(n) for n in ("escHtml", "_fmtEventDate", "_ordenHtml"))
    assert _node(js, "_ordenHtml([])") == ""


def test_die_piloten_details_holen_die_orden_im_zeitraum_der_statistik():
    assert 'id="pilot-orden"' in _funktion("renderFlightsList")
    laden = _funktion("_ordenLaden")
    assert "/api/pilots/${cid}/orden?days=${days}" in laden
    assert "_ordenLaden(cid, _statsDays())" in _funktion("renderFlightsList")


def test_der_zwischenspeicher_steht_vor_dem_ersten_aufruf():
    """Ein Deep-Link auf einen Piloten laeuft schon in initFromUrl() -- ein `const` dahinter
    legt die ganze Seite lahm (TDZ)."""
    assert _INDEX.index("const _ordenCache") < _INDEX.index("\ninitFromUrl();")


def test_die_readme_beschreibt_die_ordensleiste():
    abschnitt = _README[_README.index("### 📊 Statistiken"):_README.index("Einzelflüge können aus zwei Quellen")]
    assert "Orden" in abschnitt
