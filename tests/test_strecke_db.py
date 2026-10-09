# -*- coding: utf-8 -*-
"""Ablage und Fortschreiben der Deichkontrolle (10.10.2026).

Spec: docs/superpowers/specs/2026-10-10-deichkontrolle-design.md.
"""
from __future__ import annotations

import json
import math

import pytest

import app.database as db
from app.database import (
    compute_strecke_stand, create_strecken_event, delete_strecken_event, get_connection,
    get_strecken_event, init_db, list_strecken_events, strecke_fortschreiben,
    strecke_stand_verwerfen, update_strecken_event,
)

LAT, LON = 53.72, 7.25
KM_LON = 111.32 * math.cos(math.radians(LAT))
KM_LAT = 111.32


def _ost(km):
    return LON + km / KM_LON


def _nord(km):
    return LAT + km / KM_LAT


GERADE = [[LAT, LON], [LAT, _ost(10.0)]]            # 10 km, zehn Abschnitte bei 500 m Korridor
START = "2026-10-10T18:00:00Z"


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    init_db(p)
    c = get_connection(p)
    monkeypatch.setattr(db, "_spur_sektoren", (0.0, []))
    yield c
    c.close()


def _ev(conn, grund=0.0, **extra):
    eid = create_strecken_event(conn, name="Probe", dtstart=START, punkte=GERADE, **extra)
    if grund is not None:
        update_strecken_event(conn, eid, grund_json=json.dumps([grund] * 10),
                              grund_geholt_am=START)
    conn.commit()
    return eid


def _zeit(sekunden):
    return "2026-10-10T18:%02d:%02dZ" % divmod(sekunden, 60)


def _bruegge(conn, cid, von_km, bis_km, *, ab_s=10, alt=800.0, gs=100.0, versatz_km=0.0):
    """Sekundenpunkte der Brügge entlang der Strecke, 50 m je Sekunde.

    Ein Abschnitt zählt, sobald die Spur näher als 500 m an seinen MITTELPUNKT kommt (bei 0,5 km,
    1,5 km …). Ein Flug von 0 bis 3,8 km holt deshalb genau die ersten vier Abschnitte."""
    n = int(round((bis_km - von_km) / 0.05))
    for i in range(n + 1):
        conn.execute(
            "INSERT OR REPLACE INTO bruegge_spur (cid, ts, lat, lon, alt_msl_ft, gs_kt) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cid, _zeit(ab_s + i), _nord(versatz_km), _ost(von_km + i * 0.05), alt, gs))
    conn.commit()
    return ab_s + n


def _vatsim(conn, cid, von_km, bis_km, *, ab_s, alt=800, gs=100):
    """VATSIM-Punkte alle 15 s (750 m bei 100 kt)."""
    n = int(round((bis_km - von_km) / 0.75))
    conn.execute("INSERT OR IGNORE INTO pilots (cid, name, added_at) VALUES (?, ?, ?)",
                 (cid, f"Pilot {cid}", START))
    for i in range(n + 1):
        conn.execute(
            "INSERT INTO position_history (cid, callsign, latitude, longitude, altitude, "
            "groundspeed, heading, ts) VALUES (?, ?, ?, ?, ?, ?, 90, ?)",
            (cid, f"FRS{cid}", LAT, _ost(von_km + i * 0.75), alt, gs, _zeit(ab_s + i * 15)))
    conn.commit()
    return ab_s + n * 15


# --- Ablage --------------------------------------------------------------------------------

def test_anlegen_lesen_und_vorgaben(conn):
    ev = get_strecken_event(conn, _ev(conn, grund=None))
    assert ev["name"] == "Probe" and json.loads(ev["punkte_json"]) == GERADE
    assert ev["korridor_m"] == 500 and ev["hoehe_max_ft"] == 1000
    assert ev["gs_max_kt"] == 140 and ev["gs_min_kt"] == 30
    assert ev["dtend"] == "2026-10-11T00:00:00Z", "Mitternacht des Folgetags"
    assert ev["grund_json"] is None


def test_unbekannte_felder_werden_abgewiesen(conn):
    with pytest.raises(ValueError):
        create_strecken_event(conn, name="x", dtstart=START, punkte=GERADE, korridor_km=1)
    with pytest.raises(ValueError):
        update_strecken_event(conn, _ev(conn), sued=1.0)


def test_liste_und_loeschen_nehmen_den_stand_mit(conn):
    eid = _ev(conn)
    _bruegge(conn, 7, 0.0, 3.0)
    strecke_fortschreiben(conn, get_strecken_event(conn, eid), bis=_zeit(300))
    conn.commit()
    assert [e["id"] for e in list_strecken_events(conn)] == [eid]
    delete_strecken_event(conn, eid)
    conn.commit()
    assert get_strecken_event(conn, eid) is None
    assert conn.execute("SELECT count(*) FROM progress_snapshot WHERE kind = 'strecke'"
                        ).fetchone()[0] == 0


# --- Fortschreiben -------------------------------------------------------------------------

def test_die_bruegge_deckt_ab_was_sie_abfliegt(conn):
    ev = get_strecken_event(conn, _ev(conn))
    _bruegge(conn, 7, 0.0, 3.8)
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(300))
    assert sorted(stand["treffer"]) == ["a0", "a1", "a2", "a3"]
    assert stand["abschnitte"] == 10 and stand["anteil"] == pytest.approx(0.4)
    assert stand["je_pilot"] == {7: 4}


def test_wer_zuerst_kommt_behaelt_den_abschnitt(conn):
    ev = get_strecken_event(conn, _ev(conn))
    ende = _bruegge(conn, 7, 0.0, 1.8)
    strecke_fortschreiben(conn, ev, bis=_zeit(ende + 1))
    conn.commit()
    _bruegge(conn, 9, 0.0, 3.8, ab_s=ende + 10)
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(ende + 200))
    assert stand["treffer"]["a0"][0] == 7 and stand["treffer"]["a1"][0] == 7
    assert stand["treffer"]["a2"][0] == 9 and stand["treffer"]["a3"][0] == 9
    assert stand["je_pilot"] == {7: 2, 9: 2}


def test_ueber_die_schnittkante_zweier_takte_geht_kein_abschnitt_verloren(conn):
    """Der Takt schneidet mitten im Flug. Ohne den letzten Punkt davor fehlte das Segment über
    die Kante."""
    ev = get_strecken_event(conn, _ev(conn))
    _bruegge(conn, 7, 0.0, 5.8)
    for bis in (30, 60, 90, 200):
        strecke_fortschreiben(conn, ev, bis=_zeit(bis))
        conn.commit()
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(300))
    assert sorted(stand["treffer"]) == ["a0", "a1", "a2", "a3", "a4", "a5"]


def test_zu_hoch_zu_schnell_oder_zu_weit_weg_zaehlt_nicht(conn):
    ev = get_strecken_event(conn, _ev(conn))
    _bruegge(conn, 1, 0.0, 1.8, alt=1200.0)                 # über 1.000 ft über der Strecke
    _bruegge(conn, 2, 3.0, 5.2, gs=180.0)                   # über 140 kt
    _bruegge(conn, 3, 6.0, 8.2, versatz_km=0.7)             # außerhalb des Korridors
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(300))
    assert stand["treffer"] == {} and stand["je_pilot"] == {1: 0, 2: 0, 3: 0}


def test_die_hoehe_zaehlt_ueber_dem_gelaende_des_abschnitts(conn):
    """Die Strecke steigt: Was über dem Tal zu hoch ist, passt am Berg."""
    eid = _ev(conn, grund=None)
    update_strecken_event(conn, eid, grund_json=json.dumps([0.0] * 5 + [4000.0] * 5))
    conn.commit()
    ev = get_strecken_event(conn, eid)
    _bruegge(conn, 7, 0.0, 10.0, alt=4500.0)
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(600))
    assert sorted(stand["treffer"]) == ["a5", "a6", "a7", "a8", "a9"]


def test_ohne_bruegge_keine_teilnahme(conn):
    """Die FriesenBrügge ist Pflicht (Nutzer, 10.10.2026): Eine reine VATSIM-Spur zählt nicht."""
    ev = get_strecken_event(conn, _ev(conn))
    _vatsim(conn, 5, 0.0, 6.0, ab_s=10)
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(300))
    assert stand["treffer"] == {} and stand["je_pilot"] == {}


def test_vatsim_fuellt_die_luecke_eines_teilnehmers(conn):
    ev = get_strecken_event(conn, _ev(conn))
    ende = _bruegge(conn, 5, 0.0, 1.8)                      # Brügge meldet, dann schweigt sie
    _vatsim(conn, 5, 3.0, 6.0, ab_s=ende + 20)
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(400))
    assert {"a0", "a1", "a3", "a4", "a5"} <= set(stand["treffer"])


def test_ohne_gelaendehoehen_wird_nicht_gerechnet_und_spaeter_nachgeholt(conn):
    eid = _ev(conn, grund=None)
    _bruegge(conn, 7, 0.0, 3.8)
    stand = strecke_fortschreiben(conn, get_strecken_event(conn, eid), bis=_zeit(300))
    assert stand["ohne_grund"] is True and stand["treffer"] == {}
    assert stand["bis"] == START, "der Stand rückt nicht vor -- sonst wären die Punkte verloren"
    update_strecken_event(conn, eid, grund_json=json.dumps([0.0] * 10))
    conn.commit()
    stand = strecke_fortschreiben(conn, get_strecken_event(conn, eid), bis=_zeit(300))
    assert stand["ohne_grund"] is False and len(stand["treffer"]) == 4


def test_der_stand_ueberlebt_das_aufraeumen_der_sekundenpunkte(conn):
    ev = get_strecken_event(conn, _ev(conn))
    _bruegge(conn, 7, 0.0, 3.8)
    strecke_fortschreiben(conn, ev, bis=_zeit(300))
    conn.commit()
    conn.execute("DELETE FROM bruegge_spur")
    conn.commit()
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(900))
    assert len(stand["treffer"]) == 4 and stand["je_pilot"] == {7: 4}


def test_verwerfen_setzt_den_stand_zurueck(conn):
    eid = _ev(conn)
    ev = get_strecken_event(conn, eid)
    _bruegge(conn, 7, 0.0, 3.8)
    strecke_fortschreiben(conn, ev, bis=_zeit(300))
    strecke_stand_verwerfen(conn, eid)
    conn.commit()
    conn.execute("DELETE FROM bruegge_spur")
    conn.commit()
    assert strecke_fortschreiben(conn, ev, bis=_zeit(900))["treffer"] == {}


# --- Der Stand für die Anzeige -------------------------------------------------------------

def test_der_stand_nennt_kilometer_und_piloten(conn, monkeypatch):
    ev = get_strecken_event(conn, _ev(conn))
    conn.execute("INSERT INTO pilots (cid, name, added_at) VALUES (7, 'Anna', ?)", (START,))
    _bruegge(conn, 7, 0.0, 3.8)
    monkeypatch.setattr(db, "_now_utc", lambda: _zeit(300))
    s = compute_strecke_stand(conn, ev, mit_geometrie=True)
    assert s["km_gesamt"] == 10.0 and s["km_abgedeckt"] == 4.0 and s["abschnitt_m"] == 1000
    assert s["je_pilot"] == [{"cid": 7, "name": "Anna", "abschnitte": 4, "km": 4.0}]
    assert s["regeln"]["korridor_m"] == 500 and s["ohne_grund"] is False
    assert len(s["strecke"]) == 10
    assert s["strecke"][0]["cid"] == 7 and s["strecke"][0]["ts"]
    assert s["strecke"][9]["cid"] is None and len(s["strecke"][9]["linie"]) == 2


def test_die_liste_kommt_ohne_geometrie_aus(conn, monkeypatch):
    ev = get_strecken_event(conn, _ev(conn))
    monkeypatch.setattr(db, "_now_utc", lambda: _zeit(300))
    assert "strecke" not in compute_strecke_stand(conn, ev)


# --- Die Sekundenpunkte werden auch für Strecken mitgeschrieben --------------------------------

def test_die_wache_der_sekundenspur_kennt_laufende_strecken(conn, monkeypatch):
    from app.database import bruegge_spur_schreiben
    _ev(conn)
    monkeypatch.setattr(db, "_now_utc", lambda: _zeit(120))
    lage = {"lat": LAT, "lon": _ost(5.0), "alt_msl_ft": 700.0, "gs_kt": 95.0}
    assert bruegge_spur_schreiben(conn, 7, lage) is True
    weit_weg = {"lat": 48.0, "lon": 11.0, "alt_msl_ft": 700.0, "gs_kt": 95.0}
    assert bruegge_spur_schreiben(conn, 7, weit_weg) is False


def test_vor_dem_beginn_schreibt_die_wache_nichts(conn, monkeypatch):
    from app.database import bruegge_spur_schreiben
    _ev(conn)
    monkeypatch.setattr(db, "_now_utc", lambda: "2026-10-10T17:00:00Z")
    lage = {"lat": LAT, "lon": _ost(5.0), "alt_msl_ft": 700.0, "gs_kt": 95.0}
    assert bruegge_spur_schreiben(conn, 7, lage) is False
