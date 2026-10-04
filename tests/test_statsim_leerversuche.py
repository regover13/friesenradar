"""StatSim liefert fuer manche Fluege nie eine Spur (Fund 05.10.2026, Issue #60).

Solche Fluege galten fuer immer als "noch zu holen": Der Nachlader fragte alle zehn Minuten
dieselben 20 ab (2.880 Abrufe am Tag), und Fluege mit echter Spur dahinter kamen spaeter dran.
Ein leerer Versuch wird jetzt gemerkt und gestaffelt wiederholt -- nach einer Stunde, einem Tag,
einer Woche --, danach gilt der Flug als erledigt.
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.database import (
    count_uncached_statsim,
    get_connection,
    get_uncached_statsim_ids,
    init_db,
    save_statsim_positions,
    statsim_track_leer_merken,
)

T0 = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
PUNKT = [{"latitude": 53.0, "longitude": 8.0, "altitude": 1000, "groundspeed": 90,
          "heading": 10, "ts": "2026-07-01T10:00:00Z"}]


@pytest.fixture
def db(tmp_path):
    p = str(tmp_path / "t.db")
    init_db(p)
    c = get_connection(p)
    for sid in (1, 2):
        c.execute(
            "INSERT INTO statsim_cache (statsim_id,cid,callsign,departure,arrival,aircraft,"
            "logon_time,logoff_time,duration_min,fetched_at) VALUES "
            "(?,11,'FRS10','EDDK','EDDW','C172','2026-07-02T10:00:00Z','2026-07-02T10:50:00Z',50,'x')",
            (sid,))
    c.commit()
    yield p, c
    c.close()


def _offen(c, jetzt):
    return sorted(get_uncached_statsim_ids(c, callsign_prefix="", limit=10, jetzt=jetzt))


def test_ein_leerer_versuch_stellt_den_flug_eine_stunde_zurueck(db):
    _, c = db
    statsim_track_leer_merken(c, 1, jetzt=T0)
    assert _offen(c, T0 + timedelta(minutes=59)) == [2]
    assert count_uncached_statsim(c, callsign_prefix="", jetzt=T0 + timedelta(minutes=59)) == 1
    assert _offen(c, T0 + timedelta(minutes=61)) == [1, 2]


def test_die_wartezeit_waechst_stunde_tag_woche_und_dann_ist_schluss(db):
    _, c = db
    t = T0
    statsim_track_leer_merken(c, 1, jetzt=t)                      # 1. Versuch -> 1 h
    t += timedelta(hours=1, minutes=1)
    assert 1 in _offen(c, t)
    statsim_track_leer_merken(c, 1, jetzt=t)                      # 2. Versuch -> 1 Tag
    assert 1 not in _offen(c, t + timedelta(hours=23))
    t += timedelta(days=1, minutes=1)
    assert 1 in _offen(c, t)
    statsim_track_leer_merken(c, 1, jetzt=t)                      # 3. Versuch -> 1 Woche
    assert 1 not in _offen(c, t + timedelta(days=6))
    t += timedelta(days=7, minutes=1)
    assert 1 in _offen(c, t)
    statsim_track_leer_merken(c, 1, jetzt=t)                      # 4. Versuch -> erledigt
    assert 1 not in _offen(c, t + timedelta(days=3650))
    assert count_uncached_statsim(c, callsign_prefix="", jetzt=t + timedelta(days=3650)) == 1


def test_ohne_versuch_bleibt_alles_wie_bisher(db):
    _, c = db
    assert sorted(get_uncached_statsim_ids(c, callsign_prefix="", limit=10)) == [1, 2]
    assert count_uncached_statsim(c, callsign_prefix="") == 2


def test_die_versuche_ueberleben_das_neuschreiben_des_flugs(db):
    """statsim_cache wird bei jedem Abruf per INSERT OR REPLACE komplett neu geschrieben --
    der Zaehler darf deshalb nicht in dieser Tabelle stehen."""
    _, c = db
    statsim_track_leer_merken(c, 1, jetzt=T0)
    c.execute(
        "INSERT OR REPLACE INTO statsim_cache (statsim_id,cid,callsign,departure,arrival,aircraft,"
        "logon_time,logoff_time,duration_min,fetched_at) VALUES "
        "(1,11,'FRS10','EDDK','EDDW','C172','2026-07-02T10:00:00Z','2026-07-02T10:50:00Z',50,'y')")
    assert _offen(c, T0 + timedelta(minutes=10)) == [2]


# ---- Der Nachlader ---------------------------------------------------------------------

def _poller(db_path):
    from tests.test_poller import _make_poller
    p = _make_poller(db_path=db_path)
    p._http_client = AsyncMock()
    return p


def _lauf(poller, antworten):
    einst = SimpleNamespace(STATSIM_API_KEY="k", CALLSIGN_PREFIX="FRS")
    with patch("app.poller.get_settings", return_value=einst), patch(
        "app.poller.fetch_flight_track", new=AsyncMock(side_effect=antworten)
    ) as abruf, patch("app.poller.asyncio.sleep", new=AsyncMock()):
        asyncio.run(poller._fetch_statsim_tracks())
    return [a.args[1] for a in abruf.call_args_list]


def test_der_nachlader_merkt_leere_antworten_und_fragt_nicht_gleich_wieder(db):
    pfad, c = db
    poller = _poller(pfad)
    assert sorted(_lauf(poller, [[], PUNKT])) == [1, 2]
    # Zweiter Lauf zehn Minuten spaeter: Der leere Flug ist zurueckgestellt, der andere hat
    # seine Spur -- es gibt nichts abzufragen.
    assert _lauf(poller, []) == []
    assert c.execute("SELECT COUNT(*) FROM statsim_position_history").fetchone()[0] == 1


def test_der_datenbankteil_laeuft_nicht_im_hauptablauf(db):
    """Nach einem geleerten Dateicache las die Abfrage 132 MB kalt von der Platte, und die
    App stand dafuer Sekunden still (#60). Die Datenbank gehoert in einen Thread."""
    pfad, _ = db
    poller = _poller(pfad)
    haupt = threading.get_ident()
    gesehen = []

    import app.poller as pm
    echt = pm.get_uncached_statsim_ids

    def spion(conn, **kw):
        gesehen.append(threading.get_ident())
        return echt(conn, **kw)

    with patch("app.poller.get_uncached_statsim_ids", side_effect=spion):
        _lauf(poller, [[], []])
    assert gesehen and all(t != haupt for t in gesehen)


# ---- Fehler ist nicht "leer" -----------------------------------------------------------

def test_ein_fehler_des_dienstes_zaehlt_nicht_als_leerer_versuch(db):
    """Faellt StatSim aus (oder laeuft der Schluessel ab), kaeme sonst nach gut einer Woche
    jeder Flug faelschlich auf "erledigt". Nur eine echte, leere Antwort wird gemerkt."""
    pfad, c = db
    poller = _poller(pfad)
    _lauf(poller, [None, None])           # Abruf gescheitert
    assert c.execute("SELECT COUNT(*) FROM statsim_track_versuch").fetchone()[0] == 0
    assert sorted(_lauf(poller, [[], []])) == [1, 2]      # gleich wieder an der Reihe
    assert c.execute("SELECT COUNT(*) FROM statsim_track_versuch").fetchone()[0] == 2


def test_der_abruf_unterscheidet_fehler_von_leer():
    import httpx
    from app.statsim import fetch_flight_track

    async def lauf(handler):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cl:
            return (await fetch_flight_track(cl, 1, "k", fehler_als_none=True),
                    await fetch_flight_track(cl, 1, "k"))

    leer = asyncio.run(lauf(lambda r: httpx.Response(200, json={"positions": []})))
    kaputt = asyncio.run(lauf(lambda r: httpx.Response(503)))
    unfug = asyncio.run(lauf(lambda r: httpx.Response(200, json={"positions": "x"})))
    assert leer == ([], [])
    assert kaputt == (None, [])           # bisheriges Verhalten bleibt die Vorgabe
    assert unfug == (None, [])
