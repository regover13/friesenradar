# -*- coding: utf-8 -*-
"""Der Poller-Takt der Deichkontrolle (10.10.2026).

⚠ Zeiten relativ zur echten Uhr, wie in tests/test_reddung_poller.py: Der Takt überspringt
Events, die noch nicht begonnen haben -- ein festes Datum in der Zukunft wäre stumm grün.
"""
from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timedelta, timezone

import pytest

import app.database as dbm
from app.database import (
    create_strecken_event, get_connection, get_progress_snapshot, init_db, update_strecken_event,
)
from app.poller import VatsimPoller

LAT, LON = 53.72, 7.25
KM_LON = 111.32 * math.cos(math.radians(LAT))
JETZT = datetime.now(timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ost(km):
    return LON + km / KM_LON


@pytest.fixture()
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    init_db(p)
    monkeypatch.setattr(dbm, "_spur_sektoren", (0.0, []))
    monkeypatch.setattr(dbm, "_strecken_boxen_stand", (0.0, []))
    return p


def _event(pfad, *, start_vor_min=30.0, ende_in_min=30.0, grund=True, name="Probe"):
    c = get_connection(pfad)
    try:
        eid = create_strecken_event(
            c, name=name, dtstart=_iso(JETZT - timedelta(minutes=start_vor_min)),
            dtend=_iso(JETZT + timedelta(minutes=ende_in_min)),
            punkte=[[LAT, LON], [LAT, _ost(10.0)]])
        if grund:
            update_strecken_event(c, eid, grund_json=json.dumps([0.0] * 10))
        c.commit()
        return eid
    finally:
        c.close()


def _flug(pfad, cid, *, vor_min, km=3.8):
    """Sekundenpunkte der Brügge von 0 bis ``km``, beginnend ``vor_min`` Minuten vor jetzt."""
    c = get_connection(pfad)
    try:
        t0 = JETZT - timedelta(minutes=vor_min)
        for i in range(int(round(km / 0.05)) + 1):
            c.execute("INSERT OR REPLACE INTO bruegge_spur (cid, ts, lat, lon, alt_msl_ft, gs_kt) "
                      "VALUES (?, ?, ?, ?, 700, 100)",
                      (cid, _iso(t0 + timedelta(seconds=i)), LAT, _ost(i * 0.05)))
        c.commit()
    finally:
        c.close()


def _stand(pfad, eid):
    c = get_connection(pfad)
    try:
        return get_progress_snapshot(c, "strecke", eid)
    finally:
        c.close()


def _takt(pfad):
    asyncio.run(VatsimPoller(pfad)._check_strecke())


def test_der_takt_schreibt_den_stand_fort_ohne_dass_jemand_zusieht(db):
    eid = _event(db)
    _flug(db, 7, vor_min=10)
    _takt(db)
    s = _stand(db, eid)
    assert s is not None and sorted(s["treffer"]) == ["a0", "a1", "a2", "a3"]


def test_ein_event_das_noch_nicht_begonnen_hat_bleibt_unberuehrt(db):
    eid = _event(db, start_vor_min=-10, ende_in_min=60)
    _takt(db)
    assert _stand(db, eid) is None


def test_nach_dem_ende_wird_noch_einmal_abgeschlossen_aber_nicht_darueber_hinaus(db):
    """Der Flug liegt vor dem Ende, ein zweiter danach -- nur der erste zählt."""
    eid = _event(db, start_vor_min=60, ende_in_min=-5)
    _flug(db, 7, vor_min=20, km=1.8)                 # im Event
    c = get_connection(db)
    t0 = JETZT - timedelta(minutes=3)                # nach dtend
    for i in range(40):
        c.execute("INSERT OR REPLACE INTO bruegge_spur (cid, ts, lat, lon, alt_msl_ft, gs_kt) "
                  "VALUES (7, ?, ?, ?, 700, 100)",
                  (_iso(t0 + timedelta(seconds=i)), LAT, _ost(6.0 + i * 0.05)))
    c.commit()
    c.close()
    _takt(db)
    assert sorted(_stand(db, eid)["treffer"]) == ["a0", "a1"]


def test_ein_laengst_beendetes_event_laeuft_nicht_mehr_durch_den_takt(db):
    eid = _event(db, start_vor_min=600, ende_in_min=-120)
    _takt(db)
    assert _stand(db, eid) is None


def test_ein_kaputtes_event_haelt_die_anderen_nicht_auf(db):
    kaputt = _event(db, name="kaputt")
    gut = _event(db, name="gut")
    c = get_connection(db)
    c.execute("UPDATE strecken_events SET gs_max_kt = 'viel' WHERE id = ?", (kaputt,))
    c.commit()
    c.close()
    _flug(db, 7, vor_min=10)
    _takt(db)
    assert _stand(db, gut) is not None and len(_stand(db, gut)["treffer"]) == 4


def test_der_takt_ist_im_poller_eingeplant():
    """An den Namen im Code gebunden, nicht an freien Text."""
    import inspect
    import app.poller as poller
    quelle = inspect.getsource(poller.VatsimPoller)
    assert "self._check_strecke," in quelle and 'id="strecke_check"' in quelle
    assert poller._STRECKE_TAKT_S <= 60


# --- Push: Erinnerung eine Stunde vorher und Meldung zum Beginn -----------------------------------

class _Mitschnitt(VatsimPoller):
    def __init__(self, pfad):
        super().__init__(pfad)
        self.gesendet = []

    def broadcast_notify(self, kanal, cid, payload):
        self.gesendet.append((kanal, payload))


def test_zum_beginn_kommt_einmal_eine_meldung(db):
    _event(db, start_vor_min=1, ende_in_min=60, name="Grenzflug")
    p = _Mitschnitt(db)
    asyncio.run(p._check_strecke())
    asyncio.run(p._check_strecke())
    assert len(p.gesendet) == 1
    kanal, payload = p.gesendet[0]
    assert kanal == "events" and payload["title"] == "Grenzflug"
    assert "FriesenBrügge" in payload["body"]


def test_ohne_push_bleibt_es_still_und_spaeter_wird_nicht_nachgeholt(db):
    eid = _event(db, start_vor_min=1, ende_in_min=60)
    c = get_connection(db)
    update_strecken_event(c, eid, push_enabled=0)
    c.commit()
    p = _Mitschnitt(db)
    asyncio.run(p._check_strecke())
    update_strecken_event(c, eid, push_enabled=1)
    c.commit()
    c.close()
    asyncio.run(p._check_strecke())
    assert p.gesendet == [], "der Beginn ist gelatcht -- kein verspäteter Push mitten im Abend"


def test_nach_dem_ende_kommt_keine_meldung_zum_beginn_mehr(db):
    _event(db, start_vor_min=60, ende_in_min=-5)
    p = _Mitschnitt(db)
    asyncio.run(p._check_strecke())
    assert p.gesendet == []


def test_die_erinnerung_kennt_die_deichkontrolle(db):
    from app.database import strecken_events_due_for_reminder
    bald = _event(db, start_vor_min=-30, ende_in_min=120, name="bald")
    _event(db, start_vor_min=-300, ende_in_min=400, name="später")
    aus = _event(db, start_vor_min=-30, ende_in_min=120, name="aus")
    c = get_connection(db)
    update_strecken_event(c, aus, push_enabled=0)
    c.commit()
    jetzt = _iso(datetime.now(timezone.utc))
    assert [e["id"] for e in strecken_events_due_for_reminder(c, jetzt)] == [bald]
    c.close()
    p = _Mitschnitt(db)
    asyncio.run(p._check_event_reminders())
    asyncio.run(p._check_event_reminders())
    assert [x[1]["title"] for x in p.gesendet] == ["Deichkontrolle"]
    assert "bald" in p.gesendet[0][1]["body"]


def test_ein_kaputtes_event_meldet_seinen_beginn_nicht_in_jedem_takt_neu(db):
    """Scheitert das Fortschreiben, darf das Zurückrollen den Latch des Beginns nicht mitnehmen --
    sonst käme die Meldung alle 30 Sekunden (Befund der Sicherheitsprüfung, 10.10.2026)."""
    eid = _event(db, start_vor_min=1, ende_in_min=60)
    c = get_connection(db)
    c.execute("UPDATE strecken_events SET gs_max_kt = 'viel' WHERE id = ?", (eid,))
    c.commit()
    c.close()
    _flug(db, 7, vor_min=0.5, km=0.5)          # Punkte, damit die Rechnung wirklich anläuft
    p = _Mitschnitt(db)
    for _ in range(3):
        asyncio.run(p._check_strecke())
    assert len(p.gesendet) == 1


# --- Fundstellen im Takt ---------------------------------------------------------------------

def _fundstelle(pfad, eid, km=3.0):
    c = get_connection(pfad)
    try:
        dbm.strecke_fundstellen_setzen(c, eid, [{
            "lat": LAT, "lon": _ost(km), "art": "seehund_kuh", "menge_min": 4, "menge_max": 4,
            "abstand_min_m": 10, "abstand_max_m": 30, "startwert": "p", "grund_ft": 0.0}])
        c.commit()
    finally:
        c.close()


def _soll(pfad, eid):
    c = get_connection(pfad)
    try:
        return {r["id"]: r for r in dbm.bruegge_soll_alle(c)
                if r["id"].startswith(f"strecke-{eid}-")}
    finally:
        c.close()


def test_der_takt_stellt_die_fundstelle_verborgen_in_den_simulator(db):
    eid = _event(db)
    _fundstelle(db, eid)
    _takt(db)
    soll = _soll(db, eid)
    assert len(soll) >= 4 and all(r["nur_nah_m"] is not None for r in soll.values())


def test_nach_dem_fund_stellt_der_takt_rauch_dazu_und_zeigt_sie_allen(db):
    eid = _event(db)
    _fundstelle(db, eid)
    _flug(db, 7, vor_min=10)
    _takt(db)
    soll = _soll(db, eid)
    assert all(r["nur_nah_m"] is None for r in soll.values())
    assert {r["art"] for i, r in soll.items() if i.endswith("-rauch")
            or "-rauch-" in i} == {"rauch_hellblau"}


def test_nach_dem_ende_raeumt_der_takt_den_simulator(db):
    eid = _event(db, start_vor_min=60, ende_in_min=-2)
    _fundstelle(db, eid)
    c = get_connection(db)
    dbm.bruegge_soll_setzen(c, f"strecke-{eid}-f1-0", "licht", LAT, LON)
    c.commit()
    c.close()
    _takt(db)
    assert _soll(db, eid) == {}


def test_reste_eines_events_das_waehrend_eines_ausfalls_endete_werden_abgeraeumt(db):
    """Stand der Server ueber das Ende hinaus laenger als der Nachlauf, sieht der Takt das Event
    nie wieder -- seine Objekte duerfen trotzdem nicht im Soll liegen bleiben."""
    alt = _iso(JETZT - timedelta(hours=3))
    c = get_connection(db)
    dbm.bruegge_soll_setzen(c, "strecke-77-f1-0", "licht", LAT, LON, gilt_bis=alt)
    dbm.bruegge_soll_setzen(c, "strecke-78-f1-0", "licht", LAT, LON,
                            gilt_bis=_iso(JETZT + timedelta(hours=1)))
    dbm.bruegge_soll_setzen(c, "reddung-1-havarist", "licht", LAT, LON, gilt_bis=alt)
    c.commit()
    c.close()
    _takt(db)
    c = get_connection(db)
    da = {r["id"] for r in dbm.bruegge_soll_alle(c)}
    c.close()
    assert da == {"strecke-78-f1-0", "reddung-1-havarist"}
