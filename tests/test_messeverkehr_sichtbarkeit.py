from app.database import init_db, get_connection, add_messeverkehr_erlaubt
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
