from datetime import datetime, timedelta, timezone

import pytest

from app.database import init_db, get_connection, set_messeverkehr_anzahl_bereich
from app.messeverkehr import (
    advance_messeverkehr,
    bekannte_echte_callsigns,
    messeverkehr_fuer_anzeige,
    _freies_callsign,
    _historischen_flug_waehlen,
    _position_bei,
    _INTERNE_REPLAY_SPALTEN,
)

ZIEL_ANZAHL_FLUEGE = 3  # in den meisten Tests fest verdrahtet, s. set_messeverkehr_anzahl_bereich unten


@pytest.fixture
def conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    c = get_connection(db_path)
    # Deterministisch fuer Tests, die eine feste Anzahl erwarten -- der Bereich selbst wird in
    # test_anzahl_bereich_* eigens getestet.
    set_messeverkehr_anzahl_bereich(c, ZIEL_ANZAHL_FLUEGE, ZIEL_ANZAHL_FLUEGE)
    c.commit()
    yield c
    c.close()


def _pilot(conn, cid, name="Testpilot"):
    conn.execute(
        "INSERT OR IGNORE INTO pilots (cid, name, added_at) VALUES (?, ?, '2026-01-01T00:00:00Z')",
        (cid, name),
    )


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _seed_historischer_flug(conn, cid=500001, callsign="FRS500", departure="EDXW",
                             arrival="EDHL", dauer_min=20, schritte=5, ts0=None):
    """Legt einen abgeschlossenen echten Flug samt Track an -- Hoehe steigt dann sinkt,
    Geschwindigkeit variiert, damit ein Replay davon nachweislich NICHT gleichfoermig ist."""
    ts0 = ts0 or datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    ts1 = ts0 + timedelta(minutes=dauer_min)
    conn.execute(
        "INSERT INTO pilots (cid, name, added_at) VALUES (?, ?, ?)",
        (cid, "Testpilot", _iso(ts0)),
    )
    cur = conn.execute(
        "INSERT INTO flights (cid, callsign, aircraft_short, aircraft_icao, departure, "
        "arrival, route, flight_rules, cruise_tas, alternate, deptime, enroute_time, "
        "fuel_time, logon_time, logoff_time, duration_min) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, callsign, "C172", "C172", departure, arrival, "DCT", "V", "100",
         "EDXR", "1000", "0020", "0100", _iso(ts0), _iso(ts1), dauer_min),
    )
    flight_id = cur.lastrowid

    for i in range(schritte):
        anteil = i / (schritte - 1)
        ts = ts0 + timedelta(seconds=anteil * dauer_min * 60)
        alt = 0 if anteil in (0.0, 1.0) else int(500 + 2500 * (1 - abs(anteil - 0.5) * 2))
        gs = 0 if anteil in (0.0, 1.0) else 60 + int(40 * (1 - abs(anteil - 0.5) * 2))
        lat = 54.18 + (53.80 - 54.18) * anteil
        lon = 8.69 + (10.72 - 8.69) * anteil
        conn.execute(
            "INSERT INTO position_history (cid, callsign, latitude, longitude, altitude, "
            "groundspeed, heading, ts) VALUES (?,?,?,?,?,?,?,?)",
            (cid, callsign, lat, lon, alt, gs, 90, _iso(ts)),
        )
    conn.commit()
    return {"id": flight_id, "cid": cid, "callsign": callsign, "logon_time": _iso(ts0),
            "logoff_time": _iso(ts1)}


def test_advance_ohne_historie_erzeugt_nichts(conn):
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    assert ergebnis == []


def test_advance_erzeugt_fluege_aus_echter_historie(conn):
    _seed_historischer_flug(conn)
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    assert len(ergebnis) == ZIEL_ANZAHL_FLUEGE
    for flug in ergebnis:
        assert flug["cid"] < 0
        assert flug["departure"] == "EDXW"
        assert flug["arrival"] == "EDHL"
        assert flug["aircraft"] == "C172"
        assert flug["route"] == "DCT"
        assert flug["flight_rules"] == "V"
        assert flug["cruise_tas"] == "100"
        assert flug["alternate"] == "EDXR"


def test_interne_replay_spalten_verlassen_nie_advance_messeverkehr(conn):
    _seed_historischer_flug(conn)
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    for flug in ergebnis:
        for spalte in _INTERNE_REPLAY_SPALTEN:
            assert spalte not in flug, f"{spalte} haette den Server nicht verlassen duerfen"


def test_messeverkehr_fuer_anzeige_ohne_interne_spalten(conn):
    from app.database import set_messeverkehr_aktiv
    _seed_historischer_flug(conn)
    set_messeverkehr_aktiv(conn, True)
    conn.commit()
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    for flug in messeverkehr_fuer_anzeige(conn):
        for spalte in _INTERNE_REPLAY_SPALTEN:
            assert spalte not in flug


def test_kopfstart_staffelt_die_logon_zeiten_beim_ersten_start(conn):
    """Nutzerfund 27.09.2026: alle drei Fluege gingen beim ersten Aktivieren gleichzeitig
    "online". Jetzt startet jeder Slot mit zufaelligem Vorsprung in seinem Quellflug."""
    _seed_historischer_flug(conn, dauer_min=60, schritte=20)
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    logon_zeiten = {f["logon_time"] for f in ergebnis}
    assert len(logon_zeiten) > 1, "alle Fluege gingen zur exakt selben Zeit online"


def test_advance_bewegt_sich_entlang_der_echten_spur_und_respawnt(conn):
    _seed_historischer_flug(conn, dauer_min=20, schritte=10)
    jetzt = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)  # deckt sich mit ts0
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    verfolgte_cid = ergebnis[0]["cid"]
    erste_logon_time = ergebnis[0]["logon_time"]
    erste_hoehe = ergebnis[0]["altitude"]

    hoehen = [erste_hoehe]
    respawnt = False
    for _ in range(200):
        jetzt = jetzt + timedelta(minutes=2)
        ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
        conn.commit()
        flug = next(f for f in ergebnis if f["cid"] == verfolgte_cid)
        if flug["logon_time"] != erste_logon_time:
            respawnt = True
            break
        hoehen.append(flug["altitude"])

    assert respawnt, "Flug ist nie angekommen (oder nie respawnt)"
    # Die Hoehe muss sich ueber den Flug veraendert haben (steigt dann sinkt) -- nicht
    # konstant wie beim alten, rein synthetischen Generator.
    assert max(hoehen) > min(hoehen) + 100, hoehen


def test_position_bei_interpoliert_linear(conn):
    _pilot(conn, 999)
    ts0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    ts1 = ts0 + timedelta(minutes=10)
    conn.execute(
        "INSERT INTO position_history (cid, callsign, latitude, longitude, altitude, "
        "groundspeed, heading, ts) VALUES (?,?,?,?,?,?,?,?)",
        (999, "FRSX", 50.0, 8.0, 1000, 100, 90, _iso(ts0)),
    )
    conn.execute(
        "INSERT INTO position_history (cid, callsign, latitude, longitude, altitude, "
        "groundspeed, heading, ts) VALUES (?,?,?,?,?,?,?,?)",
        (999, "FRSX", 51.0, 10.0, 3000, 120, 270, _iso(ts1)),
    )
    conn.commit()

    mitte = _position_bei(conn, 999, ts0 + timedelta(minutes=5))
    assert mitte is not None
    assert abs(mitte["latitude"] - 50.5) < 1e-6
    assert abs(mitte["longitude"] - 9.0) < 1e-6
    assert abs(mitte["altitude"] - 2000) < 1e-6

    ausserhalb = _position_bei(conn, 999, ts1 + timedelta(minutes=1))
    assert ausserhalb is None


def test_historischen_flug_waehlen_ignoriert_zu_kurze_und_zu_lange(conn):
    _seed_historischer_flug(conn, cid=1, callsign="FRS1", dauer_min=2, schritte=3)  # zu kurz
    _seed_historischer_flug(conn, cid=2, callsign="FRS2", dauer_min=40, schritte=5)  # passt
    gefunden = _historischen_flug_waehlen(conn)
    assert gefunden is not None
    assert gefunden["cid"] == 2


def test_bekannte_echte_callsigns_liest_alle_quellen(conn):
    _pilot(conn, 1)
    conn.execute(
        "INSERT INTO flights (cid, callsign, logon_time) VALUES (1, 'FRS1', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO live_positions (cid, callsign) VALUES (2, 'FRS2')"
    )
    conn.execute(
        "INSERT INTO statsim_cache (statsim_id, cid, callsign, logon_time, fetched_at) "
        "VALUES (1, 3, 'FRS3', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO forum_callsign (callsign, cid, updated_at) VALUES ('FRS4', 4, '2026-01-01T00:00:00Z')"
    )
    conn.commit()
    ergebnis = bekannte_echte_callsigns(conn)
    assert {"FRS1", "FRS2", "FRS3", "FRS4"} <= ergebnis


def test_freies_callsign_meidet_belegte(conn):
    belegt = {f"FRS{n}" for n in range(2, 300)}
    kandidat = _freies_callsign(belegt)
    assert kandidat not in belegt


def test_freies_callsign_streut_ueber_viele_aufrufe():
    """Nutzerfund 27.09.2026: das feste Muster 800/810/820 fiel selbst als Kennzeichnung auf.
    Jetzt zufaellig -- ueber genug Aufrufe entsteht KEIN festes Muster."""
    ergebnisse = {_freies_callsign(set()) for _ in range(60)}
    assert len(ergebnisse) > 15, ergebnisse


def test_anzahl_bereich_wird_eingehalten_und_bleibt_stabil(conn):
    """Admin-Wunsch 27.09.2026: min/max gleichzeitiger Fluege einstellbar. Einmal je
    Aktivierung gewuerfelt, danach stabil (kein Flackern durch Neuwuerfeln bei jedem Zyklus)."""
    set_messeverkehr_anzahl_bereich(conn, 1, 1)
    conn.commit()
    _seed_historischer_flug(conn, dauer_min=60, schritte=10)
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    erster = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    assert len(erster) == 1

    for _ in range(5):
        jetzt = jetzt + timedelta(seconds=15)
        weiterer = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
        conn.commit()
        assert len(weiterer) == 1


def test_anzahl_bereich_erlaubt_null(conn):
    """min=max=0 muss das Feature effektiv leerlaufen lassen, ohne Fehler."""
    set_messeverkehr_anzahl_bereich(conn, 0, 0)
    conn.commit()
    _seed_historischer_flug(conn)
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    assert ergebnis == []


def test_staffelung_minuten_ist_konfigurierbar(conn):
    from app.database import set_messeverkehr_staffelung_minuten

    set_messeverkehr_staffelung_minuten(conn, 0)
    conn.commit()
    _seed_historischer_flug(conn, dauer_min=60, schritte=10)
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    # Mit 0 Minuten Staffelung starten alle Fluege ohne Vorsprung -- alle logon_time == jetzt.
    logon_zeiten = {f["logon_time"] for f in ergebnis}
    assert logon_zeiten == {jetzt.isoformat().replace("+00:00", "Z")}


def test_ausschluss_callsigns_werden_gemieden(conn):
    from app.database import set_messeverkehr_ausschluss_callsigns

    set_messeverkehr_ausschluss_callsigns(conn, ["FRS7", "FRS8", "FRS9"])
    conn.commit()
    belegt = bekannte_echte_callsigns(conn)
    assert {"FRS7", "FRS8", "FRS9"} <= belegt
    for _ in range(60):
        assert _freies_callsign(belegt) not in {"FRS7", "FRS8", "FRS9"}


def test_freies_callsign_nie_einstellig_und_nie_vierstellig():
    """Nutzerwunsch 27.09.2026: keine einstelligen (wirken wie sehr alte/bekannte
    Gruendungsmitglieder-Callsigns) und keine vierstelligen (bei FRS gibt es das nicht)."""
    for _ in range(200):
        kandidat = _freies_callsign(set())
        zahl = "".join(c for c in kandidat[3:] if c.isdigit())
        assert 2 <= len(zahl) <= 3, kandidat


def test_freies_callsign_manchmal_mit_n_suffix():
    """Nutzerwunsch 27.09.2026: reale Callsigns tragen manchmal ein 'N' am Ende (Neu-Friese,
    siehe Flugschule: verlieren es nach dem Checkflug). Soll ab und zu vorkommen, nicht immer
    und nicht nie."""
    ergebnisse = [_freies_callsign(set()) for _ in range(200)]
    mit_n = [k for k in ergebnisse if k.endswith("N")]
    assert 10 < len(mit_n) < 100, len(mit_n)
