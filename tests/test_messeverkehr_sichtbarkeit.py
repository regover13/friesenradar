import asyncio
from types import SimpleNamespace

import pytest

import app.main as main
from app.database import (
    init_db, get_connection, add_messeverkehr_erlaubt, get_messeverkehr_positions,
    set_messeverkehr_aktiv,
)
from app.main import _positions_fuer_betrachter


def _conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return get_connection(db_path)


_POSITIONEN = [
    {"cid": 123, "callsign": "FRS1", "latitude": 1.0},
    {"cid": -900000, "callsign": "FRS801", "latitude": 2.0, "_messeverkehr": True},
]


def test_nicht_berechtigter_betrachter_sieht_nur_echte(tmp_path):
    conn = _conn(tmp_path)
    ergebnis = _positions_fuer_betrachter(conn, _POSITIONEN, viewer_cid=999999)
    assert len(ergebnis) == 1
    assert ergebnis[0]["cid"] == 123
    conn.close()


def test_kein_viewer_cid_sieht_nur_echte(tmp_path):
    conn = _conn(tmp_path)
    ergebnis = _positions_fuer_betrachter(conn, _POSITIONEN, viewer_cid=None)
    assert len(ergebnis) == 1
    assert ergebnis[0]["cid"] == 123
    conn.close()


def test_berechtigter_betrachter_sieht_beide_ohne_markierung(tmp_path):
    conn = _conn(tmp_path)
    add_messeverkehr_erlaubt(conn, 123456, "Test")
    conn.commit()
    ergebnis = _positions_fuer_betrachter(conn, _POSITIONEN, viewer_cid=123456)
    assert len(ergebnis) == 2
    assert all("_messeverkehr" not in e for e in ergebnis)
    conn.close()


class _FakeReq:
    cookies: dict = {}


def test_get_live_schreibt_die_simulation_nicht_fort(tmp_path, monkeypatch):
    """Final-Fix C3: GET /api/live darf die Simulation nicht antreiben -- sonst wuerde jeder
    unangemeldete, oeffentliche Seitenaufruf das Tempo bestimmen. Beweis: Feature an, aber vom
    Poller noch nie geschrieben (Tabelle leer) -- nach dem Endpunkt-Aufruf MUSS sie weiter
    leer sein, statt dass get_live selbst drei neue Fluege erzeugt."""
    db_path = str(tmp_path / "t.db")
    init_db(db_path)
    monkeypatch.setattr(main, "get_settings",
                        lambda: SimpleNamespace(DB_PATH=db_path, SECRET_KEY="s3cr3t"))
    conn = get_connection(db_path)
    set_messeverkehr_aktiv(conn, True)
    conn.commit()
    conn.close()

    asyncio.run(main.get_live(_FakeReq()))

    conn = get_connection(db_path)
    bestand = get_messeverkehr_positions(conn)
    conn.close()
    assert bestand == [], "GET /api/live hat die Simulation fortgeschrieben -- das darf nur der Poller"
