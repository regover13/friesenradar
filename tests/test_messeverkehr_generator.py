from datetime import datetime, timedelta, timezone

import pytest

from app.database import init_db, get_connection, set_messeverkehr_anzahl_max
from app.messeverkehr import (
    advance_messeverkehr,
    bekannte_echte_callsigns,
    messeverkehr_fuer_anzeige,
    _freies_callsign,
    _historischen_flug_waehlen,
    _position_bei,
    _INTERNE_REPLAY_SPALTEN,
)

ZIEL_ANZAHL_FLUEGE = 3  # in den meisten Tests fest verdrahtet, s. set_messeverkehr_anzahl_max unten


@pytest.fixture
def conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    c = get_connection(db_path)
    # Deterministisch fuer Tests, die eine feste Anzahl erwarten -- die Zielzahl selbst wird in
    # test_anzahl_max_* eigens getestet.
    set_messeverkehr_anzahl_max(c, ZIEL_ANZAHL_FLUEGE)
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
    "online". Jetzt startet nur Slot 0 sofort, die UEBRIGEN Slots mit zufaelligem Vorsprung."""
    _seed_historischer_flug(conn, dauer_min=60, schritte=20)
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    jetzt_iso = jetzt.isoformat().replace("+00:00", "Z")
    erster = next(f for f in ergebnis if f["cid"] == -900000)  # Slot 0
    uebrige = [f for f in ergebnis if f["cid"] != -900000]
    assert erster["logon_time"] == jetzt_iso
    assert any(f["logon_time"] != jetzt_iso for f in uebrige), \
        "alle uebrigen Fluege gingen ebenfalls zur exakt selben Zeit online"


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

    fenster_von, fenster_bis = _iso(ts0), _iso(ts1)
    mitte = _position_bei(conn, 999, ts0 + timedelta(minutes=5), fenster_von, fenster_bis)
    assert mitte is not None
    assert abs(mitte["latitude"] - 50.5) < 1e-6
    assert abs(mitte["longitude"] - 9.0) < 1e-6
    assert abs(mitte["altitude"] - 2000) < 1e-6

    ausserhalb = _position_bei(conn, 999, ts1 + timedelta(minutes=1), fenster_von, fenster_bis)
    assert ausserhalb is None


def test_position_bei_kappt_unplausible_werte(conn):
    """Nutzerfund 27.09.2026 (Screenshot der Live-Liste): ein simulierter Flug zeigte
    7.295.605 ft und 129.601 kt, ein anderer 99.626 ft bei 0 kt. Die eigentliche Ursache war
    die fehlende Fensterung in _position_bei (s. test_position_bei_ueberschreitet_nie_das_
    flugfenster) -- diese Kappung ist eine zusaetzliche, ursachenunabhaengige Sicherung:
    selbst wenn position_history irgendwann echte Ausreisser enthaelt, werden Werte
    ausserhalb plausibler Flugzeug-Grenzen gekappt, nie ungeprueft ausgeliefert."""
    _pilot(conn, 998)
    ts0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    ts1 = ts0 + timedelta(minutes=10)
    conn.execute(
        "INSERT INTO position_history (cid, callsign, latitude, longitude, altitude, "
        "groundspeed, heading, ts) VALUES (?,?,?,?,?,?,?,?)",
        (998, "FRSY", 50.0, 8.0, 999999, 99999, 90, _iso(ts0)),
    )
    conn.execute(
        "INSERT INTO position_history (cid, callsign, latitude, longitude, altitude, "
        "groundspeed, heading, ts) VALUES (?,?,?,?,?,?,?,?)",
        (998, "FRSY", 51.0, 10.0, 999999, 99999, 270, _iso(ts1)),
    )
    conn.commit()

    position = _position_bei(conn, 998, ts0 + timedelta(minutes=5), _iso(ts0), _iso(ts1))
    assert position is not None
    assert 0 <= position["altitude"] <= 45000, position["altitude"]
    assert 0 <= position["groundspeed"] <= 500, position["groundspeed"]


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


def test_anzahl_max_wird_eingehalten(conn):
    """Admin-Wunsch 27.09.2026, vereinfacht: kein Min-Feld mehr -- die Zielzahl ist die
    konfigurierte Zahl selbst, in jedem Zyklus."""
    set_messeverkehr_anzahl_max(conn, 1)
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


def test_anzahl_max_erlaubt_null(conn):
    """max=0 muss das Feature effektiv leerlaufen lassen, ohne Fehler."""
    set_messeverkehr_anzahl_max(conn, 0)
    conn.commit()
    _seed_historischer_flug(conn)
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    assert ergebnis == []


def test_kopfstart_erster_pilot_startet_sofort_ohne_vorsprung(conn):
    """Nutzerwunsch 27.09.2026: 'der erste Pilot erscheint sofort, sonst weiss ich nicht, ob
    es wirklich an ist' -- nur die UEBRIGEN Fluege verteilen sich ueber die Staffelung."""
    _seed_historischer_flug(conn, dauer_min=60, schritte=20)
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    erster = next(f for f in ergebnis if f["cid"] == -900000)  # Slot 0
    assert erster["logon_time"] == jetzt.isoformat().replace("+00:00", "Z")


def test_kopfstart_erster_pilot_kommt_trotz_verzoegertem_erstem_trackpunkt(conn):
    """Fable-Review 27.09.2026: In der Produktion liegt logon_time (VATSIM-Server-Zeit) fast
    immer VOR dem ersten aufgezeichneten position_history-Punkt -- der entsteht erst beim
    naechsten Poll-Zyklus, typischerweise 0-15s spaeter. Mit vorsprung_sek=0.0 fuer Slot 0
    verlangte _position_bei vorher einen Punkt EXAKT bei logon_time; den gibt es in Wirklichkeit
    praktisch nie -- Slot 0 waere beim Kopfstart nie zustande gekommen (und dasselbe traf jede
    Nachbesetzung, dort war vorsprung_sek schon vorher immer 0.0)."""
    cid, callsign = 500002, "FRS600"
    ts0 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    logon_time = _iso(ts0)
    logoff_time = _iso(ts0 + timedelta(minutes=60))
    conn.execute(
        "INSERT INTO pilots (cid, name, added_at) VALUES (?, ?, ?)",
        (cid, "Testpilot", logon_time),
    )
    conn.execute(
        "INSERT INTO flights (cid, callsign, aircraft_short, aircraft_icao, departure, "
        "arrival, route, flight_rules, cruise_tas, alternate, deptime, enroute_time, "
        "fuel_time, logon_time, logoff_time, duration_min) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, callsign, "C172", "C172", "EDXW", "EDHL", "DCT", "V", "100",
         "EDXR", "1000", "0020", "0100", logon_time, logoff_time, 60),
    )
    # Erster Track-Punkt liegt bewusst 18s NACH logon_time -- der reale Poll-Verzug.
    for versatz_sek in (18, 3540):
        ts = ts0 + timedelta(seconds=versatz_sek)
        conn.execute(
            "INSERT INTO position_history (cid, callsign, latitude, longitude, altitude, "
            "groundspeed, heading, ts) VALUES (?,?,?,?,?,?,?,?)",
            (cid, callsign, 54.0, 8.5, 1000, 90, 90, _iso(ts)),
        )
    conn.commit()

    jetzt = ts0  # exakt logon_time -- der kritische Grenzfall
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    assert len(ergebnis) == ZIEL_ANZAHL_FLUEGE, "Slot 0 (oder ein anderer) fehlt beim Kopfstart"


def test_kopfstart_nachbesetzung_startet_ebenfalls_sofort(conn):
    """Die Staffelung gilt nur fuer den allerersten Schwarm -- eine Nachbesetzung (ein Flug
    ist angekommen, kopfstart=False fuer diesen Slot) erscheint wie bisher sofort."""
    set_messeverkehr_anzahl_max(conn, 1)
    conn.commit()
    _seed_historischer_flug(conn, dauer_min=15, schritte=5)
    jetzt = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)  # deckt sich mit ts0
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    erste_logon_time = ergebnis[0]["logon_time"]

    respawnt_bei = None
    for _ in range(200):
        jetzt = jetzt + timedelta(minutes=1)
        ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
        conn.commit()
        if ergebnis[0]["logon_time"] != erste_logon_time:
            respawnt_bei = jetzt
            break
    assert respawnt_bei is not None, "Flug ist nie angekommen (oder nie respawnt)"
    assert ergebnis[0]["logon_time"] == respawnt_bei.isoformat().replace("+00:00", "Z")


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


def test_pilotenname_endet_immer_auf_heimatflugplatz(conn):
    """Nutzerfund 27.09.2026 (Screenshot der Live-Liste): echte Namen bei FriesenSpy tragen
    IMMER den Heimatflugplatz (ICAO) am Ende, z.B. "Tobias EDKB" -- manchmal nur Vorname,
    aber nie ohne den Platz. Ohne den Platz fielen die erfundenen Namen sofort auf."""
    _seed_historischer_flug(conn)
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    for flug in ergebnis:
        teile = flug["name"].split()
        assert len(teile) >= 2, flug["name"]
        heimat = teile[-1]
        assert len(heimat) == 4 and heimat.isalpha() and heimat.isupper(), flug["name"]


def test_advance_stuerzt_nicht_bei_zeilen_ohne_replay_buchhaltung(conn):
    """PRODUKTIONSVORFALL 27.09.2026: Nach dem Umstieg auf Historien-Replay lagen in
    messeverkehr_flights noch Zeilen aus dem alten, rein synthetischen Generator -- ohne
    quelle_cid/quelle_logon_time/quelle_logoff_time (NULL). _fortschreiben() rief darauf
    _als_datetime(None) auf und riss den KOMPLETTEN Poll-Zyklus jede 15s ab (nicht nur den
    Messeverkehr) -- Traceback: "AttributeError: 'NoneType' object has no attribute
    'replace'". Live-Notfallmassnahme war, die Tabelle leerzuraeumen; dieser Test bindet die
    eigentliche Ursache: eine Zeile ohne Replay-Buchhaltung darf advance_messeverkehr nicht
    zum Absturz bringen, sondern muss wie ein "angekommener" Flug behandelt werden (respawnt)."""
    _seed_historischer_flug(conn)
    from app.database import replace_messeverkehr_positions

    alte_zeile = {
        "cid": -900000, "callsign": "FRS999", "aircraft": "C172",
        "departure": "EDXW", "arrival": "EDHL", "latitude": 54.1, "longitude": 8.3,
        "altitude": 3500, "groundspeed": 110, "heading": 90,
        "logon_time": "2026-09-27T10:00:00Z", "updated_at": "2026-09-27T10:00:00Z",
        "name": "Alter Generator",
        # quelle_flight_id/quelle_cid/quelle_logon_time/quelle_logoff_time bewusst NICHT
        # gesetzt -- genau der Zustand nach dem Schema-Umstieg.
    }
    replace_messeverkehr_positions(conn, [alte_zeile])
    conn.commit()

    jetzt = datetime(2026, 9, 27, 10, 0, 30, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())  # darf NICHT werfen
    conn.commit()
    assert len(ergebnis) >= 1
    # Der respawnte Flug hat eine neue logon_time, nicht die alte -- klarer Beweis, dass er
    # tatsaechlich neu erzeugt und nicht einfach durchgereicht wurde.
    assert all(f["logon_time"] != "2026-09-27T10:00:00Z" for f in ergebnis)


def test_advance_liefert_dieselbe_reihenfolge_wie_get_messeverkehr_positions(conn):
    """Nutzerfund 27.09.2026: die simulierten Piloten wechselten staendig ihre Position in
    der Live-Liste. Ursache: advance_messeverkehr() (speist den SSE-Broadcast) gab die Fluege
    in Slot-Reihenfolge zurueck, get_messeverkehr_positions() (speist den REST-Fallback und
    die Erstladung) in `ORDER BY cid` -- GENAU entgegengesetzt bei den fest vergebenen
    negativen CIDs. Beide Kanaele fuettern dieselbe Tabelle, das Flip-Flop zwischen den zwei
    Reihenfolgen sah wie eine staendige Umsortierung aus. Beide Wege muessen dieselbe
    Reihenfolge liefern."""
    _seed_historischer_flug(conn)
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    von_advance = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    from app.database import get_messeverkehr_positions
    von_lesend = get_messeverkehr_positions(conn)

    assert [f["cid"] for f in von_advance] == [f["cid"] for f in von_lesend]


def test_position_bei_ueberschreitet_nie_das_flugfenster(conn):
    """PRODUKTIONSVORFALL 27.09.2026: _position_bei suchte in der GESAMTEN
    position_history-Historie eines Piloten, nicht nur im Zeitfenster des gewaehlten Fluges.
    Bei einer Aufzeichnungsluecke griff die Suche in einen VOELLIG ANDEREN, zeitlich weit
    entfernten Flug desselben Piloten -- Nutzerfund: "FRS122 ist mal schnell von Florida an
    die Elfenbeinkueste". Diese beiden Punkte hier simulieren genau das: ein Flug in
    Deutschland (Fenster), und Wochen spaeter ein voellig anderer, weit entfernter Flug
    DESSELBEN cid ausserhalb des Fensters. Die Suche darf NIE ueber die Fenstergrenzen
    hinausgreifen."""
    _pilot(conn, 997)
    fenster_von = datetime(2026, 8, 5, 17, 0, 0, tzinfo=timezone.utc)
    fenster_bis = datetime(2026, 8, 5, 18, 0, 0, tzinfo=timezone.utc)
    # Einziger Punkt INNERHALB des Fensters (Deutschland).
    conn.execute(
        "INSERT INTO position_history (cid, callsign, latitude, longitude, altitude, "
        "groundspeed, heading, ts) VALUES (?,?,?,?,?,?,?,?)",
        (997, "FRSZ", 51.13, 13.77, 2000, 100, 90, _iso(fenster_von)),
    )
    # Weit entfernter Punkt WOCHEN SPAETER, ausserhalb des Fensters (Elfenbeinkueste).
    conn.execute(
        "INSERT INTO position_history (cid, callsign, latitude, longitude, altitude, "
        "groundspeed, heading, ts) VALUES (?,?,?,?,?,?,?,?)",
        (997, "FRSZ", 5.0, -4.0, 3000, 150, 90, _iso(fenster_bis + timedelta(days=20))),
    )
    conn.commit()

    # Zeitpunkt liegt NACH dem letzten Punkt IM Fenster -> muss als "angekommen" gelten
    # (None), NICHT den weit entfernten Punkt ausserhalb des Fensters heranziehen.
    # fenster_von/fenster_bis als ISO-Text, wie es die echten Aufrufer immer tun (logon_time/
    # logoff_time kommen als TEXT-Spalten aus der DB) -- ein rohes datetime-Objekt wuerde
    # sqlite3s eigenen (abweichenden) Adapter nehmen statt _iso(), und die Textvergleiche in
    # der SQL-Abfrage koennten leise danebengehen.
    ergebnis = _position_bei(conn, 997, fenster_von + timedelta(minutes=30),
                             _iso(fenster_von), _iso(fenster_bis))
    assert ergebnis is None, ergebnis


def test_historischen_flug_waehlen_nur_deutsche_strecken(conn):
    """Nutzerwunsch 27.09.2026: die simulierten Fluege sollen in Deutschland stattfinden --
    kein KEVB->KMCO (Florida) mehr. Nur Fluege mit deutschem Start UND Ziel (ICAO-Praefix ED)
    kommen als Vorlage infrage."""
    conn.execute(
        "INSERT INTO pilots (cid, name, added_at) VALUES (5, 'X', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO flights (cid, callsign, departure, arrival, logon_time, logoff_time, "
        "duration_min) VALUES (5, 'FRS5', 'KEVB', 'KMCO', '2026-01-01T10:00:00Z', "
        "'2026-01-01T10:30:00Z', 30)"
    )
    for i in range(2):
        conn.execute(
            "INSERT INTO position_history (cid, callsign, latitude, longitude, altitude, "
            "groundspeed, heading, ts) VALUES (5, 'FRS5', 28.0, -81.0, 1000, 100, 90, ?)",
            (f"2026-01-01T10:0{i}:00Z",),
        )
    _seed_historischer_flug(conn, cid=6, callsign="FRS6", departure="EDXW", arrival="EDHL")
    conn.commit()

    for _ in range(10):
        gefunden = _historischen_flug_waehlen(conn)
        assert gefunden is not None
        assert gefunden["departure"].startswith("ED"), gefunden
        assert gefunden["arrival"].startswith("ED"), gefunden
