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
