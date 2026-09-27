from app.database import (
    init_db, get_connection, set_messeverkehr_aktiv,
)
from app.poller import _live_positions_mit_messeverkehr


def _conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return get_connection(db_path)


def test_ohne_flag_bleibt_liste_unveraendert(tmp_path):
    conn = _conn(tmp_path)
    echte = [{"cid": 123, "callsign": "FRS1", "latitude": 1.0, "longitude": 2.0}]
    ergebnis = _live_positions_mit_messeverkehr(conn, echte)
    assert ergebnis == echte
    conn.close()


def test_mit_flag_werden_simulierte_fluege_markiert_beigemischt(tmp_path):
    conn = _conn(tmp_path)
    set_messeverkehr_aktiv(conn, True)
    conn.commit()
    echte = [{"cid": 123, "callsign": "FRS1", "latitude": 1.0, "longitude": 2.0}]
    ergebnis = _live_positions_mit_messeverkehr(conn, echte)
    assert len(ergebnis) > len(echte)
    simulierte = [e for e in ergebnis if e.get("_messeverkehr")]
    assert len(simulierte) > 0
    assert all(e["cid"] < 0 for e in simulierte)
    conn.close()


def test_traffic_snapshot_bleibt_von_messeverkehr_getrennt():
    """Review Focus: /api/traffic speist sich aus poller.traffic_snapshot, einer ANDEREN
    Quelle als live_positions. Textbasierte Regressionsprobe nach dem Muster von
    test_kutter_eventloop.py (CLAUDE.md) -- prueft, dass die Zeile, die traffic_snapshot setzt,
    NICHT ueber _live_positions_mit_messeverkehr laeuft."""
    import inspect
    import app.poller as poller_modul

    quelltext = inspect.getsource(poller_modul)
    zeilen = quelltext.splitlines()
    treffer = [z for z in zeilen if "traffic_snapshot" in z and "=" in z and "def " not in z]
    assert treffer, "keine Zuweisung an traffic_snapshot gefunden -- Testannahme pruefen"
    assert not any("_live_positions_mit_messeverkehr" in z for z in treffer)
