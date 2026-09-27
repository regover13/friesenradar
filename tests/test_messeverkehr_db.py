import sqlite3

import pytest

from app.database import (
    init_db,
    get_connection,
    get_messeverkehr_positions,
    replace_messeverkehr_positions,
    cid_hat_messeverkehr_erlaubnis,
    list_messeverkehr_erlaubt,
    add_messeverkehr_erlaubt,
    remove_messeverkehr_erlaubt,
    ist_messeverkehr_aktiv,
    set_messeverkehr_aktiv,
)


@pytest.fixture
def conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    c = get_connection(db_path)
    yield c
    c.close()


def test_messeverkehr_positions_leer_ohne_daten(conn):
    assert get_messeverkehr_positions(conn) == []


def test_replace_messeverkehr_positions_ersetzt_bestand(conn):
    flug = {
        "cid": -1, "callsign": "FRS801", "aircraft": "C172",
        "departure": "EDXW", "arrival": "EDHL", "latitude": 54.1,
        "longitude": 8.3, "altitude": 3500, "groundspeed": 110,
        "heading": 90, "logon_time": "2026-11-21T10:00:00Z",
        "updated_at": "2026-11-21T10:05:00Z", "name": "Messe-Friese 1",
    }
    replace_messeverkehr_positions(conn, [flug])
    conn.commit()
    rows = get_messeverkehr_positions(conn)
    assert len(rows) == 1
    assert rows[0]["cid"] == -1
    assert rows[0]["callsign"] == "FRS801"

    replace_messeverkehr_positions(conn, [])
    conn.commit()
    assert get_messeverkehr_positions(conn) == []


def test_messeverkehr_positions_erzwingt_negative_cid(conn):
    flug = {
        "cid": 5, "callsign": "FRS802", "aircraft": "C172",
        "departure": "EDXW", "arrival": "EDHL", "latitude": 54.1,
        "longitude": 8.3, "altitude": 3500, "groundspeed": 110,
        "heading": 90, "logon_time": "2026-11-21T10:00:00Z",
        "updated_at": "2026-11-21T10:05:00Z", "name": "Messe-Friese 2",
    }
    with pytest.raises(ValueError, match="cid"):
        replace_messeverkehr_positions(conn, [flug])


def test_erlaubnis_ohne_eintrag_ist_false(conn):
    assert cid_hat_messeverkehr_erlaubnis(conn, 123456) is False


def test_erlaubnis_none_cid_ist_false(conn):
    assert cid_hat_messeverkehr_erlaubnis(conn, None) is False


def test_add_list_remove_messeverkehr_erlaubt(conn):
    add_messeverkehr_erlaubt(conn, 123456, "Tobias")
    conn.commit()
    assert cid_hat_messeverkehr_erlaubnis(conn, 123456) is True
    eintraege = list_messeverkehr_erlaubt(conn)
    assert len(eintraege) == 1
    assert eintraege[0]["cid"] == 123456
    assert eintraege[0]["hinzugefuegt_von"] == "Tobias"

    remove_messeverkehr_erlaubt(conn, 123456)
    conn.commit()
    assert cid_hat_messeverkehr_erlaubnis(conn, 123456) is False
    assert list_messeverkehr_erlaubt(conn) == []


def test_messeverkehr_aktiv_default_false(conn):
    assert ist_messeverkehr_aktiv(conn) is False


def test_set_messeverkehr_aktiv(conn):
    set_messeverkehr_aktiv(conn, True)
    conn.commit()
    assert ist_messeverkehr_aktiv(conn) is True
    set_messeverkehr_aktiv(conn, False)
    conn.commit()
    assert ist_messeverkehr_aktiv(conn) is False
