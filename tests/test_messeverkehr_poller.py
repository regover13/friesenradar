from app.database import (
    init_db, get_connection, set_messeverkehr_aktiv,
)
from app.poller import _live_positions_mit_messeverkehr


def _conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return get_connection(db_path)


def _seed_historischer_flug(conn, cid=600001, callsign="FRS600"):
    """Minimaler echter Flug samt Track, seit der Replay-Umstellung (27.09.2026) Vorbedingung
    dafuer, dass advance_messeverkehr ueberhaupt etwas erzeugt."""
    from datetime import datetime, timedelta, timezone

    ts0 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    ts1 = ts0 + timedelta(minutes=20)
    iso = lambda dt: dt.isoformat().replace("+00:00", "Z")
    conn.execute("INSERT INTO pilots (cid, name, added_at) VALUES (?, 'Testpilot', ?)",
                 (cid, iso(ts0)))
    conn.execute(
        "INSERT INTO flights (cid, callsign, aircraft_short, departure, arrival, "
        "logon_time, logoff_time, duration_min) VALUES (?,?,?,?,?,?,?,?)",
        (cid, callsign, "C172", "EDXW", "EDHL", iso(ts0), iso(ts1), 20),
    )
    for i in range(5):
        ts = ts0 + timedelta(minutes=5 * i)
        conn.execute(
            "INSERT INTO position_history (cid, callsign, latitude, longitude, altitude, "
            "groundspeed, heading, ts) VALUES (?,?,?,?,?,?,?,?)",
            (cid, callsign, 54.0 + i * 0.1, 8.0 + i * 0.1, 1000 + i * 100, 90, 90, iso(ts)),
        )
    conn.commit()


def test_ohne_flag_bleibt_liste_unveraendert(tmp_path):
    conn = _conn(tmp_path)
    echte = [{"cid": 123, "callsign": "FRS1", "latitude": 1.0, "longitude": 2.0}]
    ergebnis = _live_positions_mit_messeverkehr(conn, echte)
    assert ergebnis == echte
    conn.close()


def test_mit_flag_werden_simulierte_fluege_markiert_beigemischt(tmp_path):
    conn = _conn(tmp_path)
    _seed_historischer_flug(conn)
    set_messeverkehr_aktiv(conn, True)
    conn.commit()
    echte = [{"cid": 123, "callsign": "FRS1", "latitude": 1.0, "longitude": 2.0}]
    ergebnis = _live_positions_mit_messeverkehr(conn, echte)
    assert len(ergebnis) > len(echte)
    simulierte = [e for e in ergebnis if e.get("_messeverkehr")]
    assert len(simulierte) > 0
    assert all(e["cid"] < 0 for e in simulierte)
    conn.close()


def test_mischen_committet_seinen_schreibvorgang(tmp_path):
    """Final-Fix C1: Ohne eigenen commit() verwirft conn.close() das DELETE/INSERT aus
    advance_messeverkehr -- der simulierte Bestand bliebe bei jedem Zyklus leer und jeder
    Aufruf wuerfelt drei neue Fluege. Beweis: NACH dem Mischen die Verbindung schliessen, NEU
    oeffnen und pruefen, dass der Bestand tatsaechlich auf der Platte steht."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    conn = get_connection(db_path)
    _seed_historischer_flug(conn)
    set_messeverkehr_aktiv(conn, True)
    conn.commit()
    _live_positions_mit_messeverkehr(conn, [])
    conn.close()

    from app.database import get_messeverkehr_positions
    frische_verbindung = get_connection(db_path)
    bestand = get_messeverkehr_positions(frische_verbindung)
    frische_verbindung.close()
    assert len(bestand) > 0, "Messeverkehr wurde nicht committet -- geht beim Schliessen verloren"


def test_friesen_snapshot_wird_vor_dem_mischen_gesetzt():
    """Final-Fix I1: friesen_snapshot speist die Kniebrett-Positionsrueckmeldung
    (_kniebrett_kandidaten in app/main.py), die ueber die ungefilterte bruegge-SSE-Nachricht
    an ALLE Verbindungen geht. Enthielte der Snapshot eine simulierte (negative) CID, liesse
    sich darueber eine erfundene Position an jede Verbindung ausliefern -- der positions-Filter
    in main.py greift dort nicht (er filtert nur type=='positions', nicht type=='bruegge').
    Textbasierte Regressionsprobe nach dem Muster von test_traffic_snapshot_bleibt_von_
    messeverkehr_getrennt: die Snapshot-Zeile muss VOR dem Mischen stehen und darf nicht auf
    die gemischte Liste zeigen."""
    import inspect
    import app.poller as poller_modul

    quelltext = inspect.getsource(poller_modul)
    snapshot_pos = quelltext.index("self.friesen_snapshot = list(live_positions)")
    mischen_pos = quelltext.index("_live_positions_mit_messeverkehr(conn, live_positions)",
                                   snapshot_pos - 200)
    assert snapshot_pos < mischen_pos, (
        "friesen_snapshot wird NACH dem Mischen gesetzt -- kann simulierten Verkehr enthalten"
    )
    # Der Broadcast darf NICHT dieselbe Variable senden wie der Snapshot uebernommen hat --
    # sonst waere die Reihenfolge oben wirkungslos, weil beide auf dasselbe Objekt zeigen.
    broadcast_zeile = next(z for z in quelltext.splitlines()
                           if 'broadcast_sse({"type": "positions"' in z)
    assert "broadcast_positions" in broadcast_zeile, broadcast_zeile


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
