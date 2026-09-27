from datetime import datetime, timedelta, timezone

import pytest

from app.database import init_db, get_connection
from app.messeverkehr import advance_messeverkehr, MESSEVERKEHR_FLUGPLAETZE, ZIEL_ANZAHL_FLUEGE


@pytest.fixture
def conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    c = get_connection(db_path)
    yield c
    c.close()


def test_advance_ohne_bestand_erzeugt_neue_fluege(conn):
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    assert len(ergebnis) == ZIEL_ANZAHL_FLUEGE
    for flug in ergebnis:
        assert flug["cid"] < 0
        assert flug["callsign"].startswith("FRS")
        assert flug["departure"] in MESSEVERKEHR_FLUGPLAETZE
        assert flug["arrival"] in MESSEVERKEHR_FLUGPLAETZE
        assert flug["departure"] != flug["arrival"]


def test_advance_vermeidet_kollision_mit_echtem_callsign(conn):
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    belegt = {f"FRS{800 + i}" for i in range(ZIEL_ANZAHL_FLUEGE)}
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=belegt)
    conn.commit()
    callsigns = {f["callsign"] for f in ergebnis}
    assert callsigns.isdisjoint(belegt)


def test_advance_bewegt_bestehenden_flug_weiter(conn):
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    erster = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    start_lat = erster[0]["latitude"]
    start_lon = erster[0]["longitude"]

    spaeter = jetzt + timedelta(seconds=15)
    zweiter = advance_messeverkehr(conn, spaeter, echte_callsigns=set())
    conn.commit()
    gleicher_flug = next(f for f in zweiter if f["cid"] == erster[0]["cid"])
    assert (gleicher_flug["latitude"], gleicher_flug["longitude"]) != (start_lat, start_lon)


def test_advance_haelt_bestand_konstant_ueber_viele_zyklen(conn):
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    for i in range(50):
        ergebnis = advance_messeverkehr(conn, jetzt + timedelta(seconds=15 * i),
                                          echte_callsigns=set())
        conn.commit()
        assert len(ergebnis) == ZIEL_ANZAHL_FLUEGE
