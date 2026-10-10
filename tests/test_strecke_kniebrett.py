# -*- coding: utf-8 -*-
"""Wer mit dem Kniebrett fliegt, nimmt an der Deichkontrolle teil (Nutzer, 10.10.2026).

„Was ist mit Menschen, die mit dem Kniebrett fliegen? Das muss auch funktionieren." Der Meldeweg
des Kniebretts schreibt die Position des EIGENEN Flugzeugs als Sekundenpunkt mit, sobald sie im
Umkreis einer laufenden Strecke liegt -- und nur dann: Sonst bleibt es dabei, dass im Meldeweg
keine Datenbank angefasst wird.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import app.database as dbm
import app.main as main
from app.database import create_strecken_event, get_connection, update_strecken_event
from tests.test_kniebrett_melden import (  # noqa: F401  (env ist eine Fixture)
    FREMD, FREMD_CS, LAT, LON, MELDER, MELDER_CS, _flugzeug, _melden, _modus_setzen, env,
)


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture()
def strecke(env, monkeypatch):
    """Eine laufende Strecke, die am Platz der beiden Friesen vorbeiführt."""
    monkeypatch.setattr(dbm, "_spur_sektoren", (0.0, []))
    monkeypatch.setattr(dbm, "_strecken_boxen_stand", (0.0, []))
    monkeypatch.setattr(main, "_kniebrett_boxen_stand", (0.0, []))
    jetzt = datetime.now(timezone.utc)
    c = get_connection(env.db)
    try:
        eid = create_strecken_event(
            c, name="Probe", dtstart=_iso(jetzt - timedelta(minutes=30)),
            dtend=_iso(jetzt + timedelta(minutes=30)),
            punkte=[[LAT, LON - 0.05], [LAT, LON + 0.05]])
        update_strecken_event(c, eid, grund_json=json.dumps([0.0] * 7))
        c.commit()
    finally:
        c.close()
    return eid


def _spur(env):
    c = get_connection(env.db)
    try:
        return [tuple(r) for r in c.execute(
            "SELECT cid, lat, lon, alt_msl_ft, gs_kt, quelle FROM bruegge_spur").fetchall()]
    finally:
        c.close()


def test_die_eigene_position_wird_im_umkreis_der_strecke_mitgeschrieben(env, strecke):
    _modus_setzen(env, "eigene")
    r = _melden(env, [_flugzeug(cs=MELDER_CS, lat=LAT, lon=LON, alt=520.0)])
    assert r.json()["uebernommen"] == 1
    assert _spur(env) == [(MELDER, pytest.approx(LAT), pytest.approx(LON), 520.0, 0.0,
                           "kniebrett")]


def test_fremde_flugzeuge_die_das_kniebrett_sieht_werden_nicht_mitgeschrieben(env, strecke):
    """Gewertet wird, wer selbst meldet -- nicht, wen ein anderer am Himmel sieht."""
    _modus_setzen(env, "alle")
    r = _melden(env, [_flugzeug(cs=FREMD_CS)])
    assert r.json()["uebernommen"] == 1
    assert _spur(env) == []


def test_ohne_laufende_strecke_bleibt_die_datenbank_im_meldeweg_unberuehrt(env, monkeypatch):
    monkeypatch.setattr(main, "_kniebrett_boxen_stand", (0.0, []))
    monkeypatch.setattr(dbm, "_strecken_boxen_stand", (0.0, []))
    _modus_setzen(env, "eigene")
    _melden(env, [_flugzeug(cs=MELDER_CS, lat=LAT, lon=LON)])
    schreiber = []
    monkeypatch.setattr(main, "kniebrett_spur_schreiben",
                        lambda *a, **k: schreiber.append(a) or True)
    _melden(env, [_flugzeug(cs=MELDER_CS, lat=LAT, lon=LON)])
    assert schreiber == [] and _spur(env) == []


def test_eine_meldung_ohne_hoehe_wird_nicht_mitgeschrieben(env, strecke):
    """Ein altes Kniebrett-Paket schickt keine Höhe -- ohne sie ist der Punkt für die Wertung
    wertlos, und die VATSIM-Höhe als Ersatz wäre eine andere Messart."""
    _modus_setzen(env, "eigene")
    e = _flugzeug(cs=MELDER_CS, lat=LAT, lon=LON)
    del e["alt"]
    assert _melden(env, [e]).json()["uebernommen"] == 1
    assert _spur(env) == []


def test_eine_unplausible_eigene_position_wird_nicht_mitgeschrieben(env, strecke):
    """Die Prüfung gegen VATSIM steht davor: Wer sich 50 km wegmeldet, schreibt nichts."""
    _modus_setzen(env, "eigene")
    _melden(env, [_flugzeug(cs=MELDER_CS, lat=LAT + 0.5, lon=LON)])
    assert _spur(env) == []


def test_ist_das_melden_abgeschaltet_wird_nichts_geschrieben(env, strecke):
    _modus_setzen(env, "aus")
    _melden(env, [_flugzeug(cs=MELDER_CS, lat=LAT, lon=LON)])
    assert _spur(env) == []


def test_die_liste_nennt_platz_und_radius_fuer_die_flugspuren(env, strecke, monkeypatch):
    """Unter der Eventansicht stehen die Flugspuren des Abends wie bei der Reddung -- dafür
    braucht die Seite einen Platz und einen Radius, der die ganze Strecke erfasst."""
    monkeypatch.setattr(main, "reddung_analyse_platz",
                        lambda box: {"icao": "EDWS", "radius_km": 12, "box": box})
    (e,) = main.strecke_events()
    assert e["analyse"]["icao"] == "EDWS" and e["analyse"]["radius_km"] == 12
    assert e["analyse"]["box"] == {"sued": LAT, "nord": LAT, "west": pytest.approx(LON - 0.05),
                                   "ost": pytest.approx(LON + 0.05)}


def test_eine_meldung_schreibt_hoechstens_einen_sekundenpunkt(env, strecke, monkeypatch):
    """Wer das eigene Rufzeichen vielfach in eine Meldung schreibt, löst damit nicht ebenso viele
    Datenbankzugriffe aus (Befund der Sicherheitsprüfung, 10.10.2026)."""
    _modus_setzen(env, "eigene")
    rufe = []
    echt = main._kniebrett_spur
    monkeypatch.setattr(main, "_kniebrett_spur", lambda *a: rufe.append(a) or echt(*a))
    _melden(env, [_flugzeug(cs=MELDER_CS, lat=LAT, lon=LON)] * 20)
    assert len(rufe) == 1 and len(_spur(env)) == 1
