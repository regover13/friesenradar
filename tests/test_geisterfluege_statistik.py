"""Geisterflüge zählen nirgends (16.9.2, Nutzer 17.10.2026).

FRS61 hatte in der Gesamtstatistik 83 Flüge, in seiner eigenen Ansicht 80: Die Flugliste
blendet Flüge mit 0 Minuten und höchstens 1 nm aus, der Server zählte sie mit. Darunter
derselbe abgebrochene Start doppelt, einmal von FriesenRadar und einmal von StatSim.
Alle Namen und Nummern sind erfunden.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app import database as db
from app.database import get_connection, init_db

CID = 1000001


def _vor(minuten: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minuten)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _flug(logon, dauer, nm, offen=False, cs="FRS61", typ="C172", **kw):
    f = {"cid": CID, "callsign": cs, "logon_time": logon,
         "logoff_time": None if offen else logon, "duration_min": dauer, "distance_nm": nm,
         "aircraft_icao": typ, "aircraft": typ, "source": "friesenspy", "connection_closed": 0}
    f.update(kw)
    return f


@pytest.fixture
def conn(tmp_path):
    p = str(tmp_path / "t.db")
    init_db(p)
    c = get_connection(p)
    yield c
    c.close()


@pytest.mark.parametrize("dauer, nm, offen, geist", [
    (0, 0, False, True), (0, 1.4, False, True), (0, None, False, True),
    (0, 1.5, False, False), (1, 0, False, False),
    (0, 0, True, True),             # erste Minute: zählt ohnehin noch nicht
])
def test_was_ein_geisterflug_ist(dauer, nm, offen, geist):
    assert db.ist_geisterflug(_flug(_vor(60), dauer, nm, offen)) is geist


def _speicher(conn, fluege):
    db._write_flight_cache_rows(conn, fluege, db._now_utc())
    conn.commit()


def test_die_gesamtstatistik_zaehlt_keine_geisterfluege(conn):
    _speicher(conn, [_flug(_vor(300), 45, 60), _flug(_vor(200), 0, 0),
                     _flug(_vor(100), 0, 0, source="statsim")])
    s = {x["cid"]: x for x in db.get_stats(conn, days=30)}[CID]
    assert s["flight_count"] == 1


def test_das_diagramm_zaehlt_keine_geisterfluege(conn):
    _speicher(conn, [_flug(_vor(300), 45, 60), _flug(_vor(200), 0, 0)])
    akt = db.get_stats_activity(conn, days=30)
    assert sum(p["flight_count"] for p in akt["data"]) == 1


def test_die_musterliste_zaehlt_keine_geisterfluege(conn):
    _speicher(conn, [_flug(_vor(300), 45, 60), _flug(_vor(200), 0, 0)])
    zeile = [m for m in db.all_type_stats_for_days(conn, 30) if m["code"] == "C172"]
    assert zeile and zeile[0]["fluege"] == 1


def _online(conn):
    conn.execute("INSERT INTO live_positions (cid, callsign) VALUES (?, 'FRS61')", (CID,))
    conn.commit()


def test_ein_alter_offener_flug_ohne_plan_zaehlt(conn):
    """FRS49, 12.09.2026: 84 Minuten ohne Flugplan, ohne Landung auf einem Platz. Bis 16.9.1
    galt er für immer als laufend und fehlte in der Gesamtstatistik."""
    _speicher(conn, [_flug(_vor(60 * 24 * 30), 84, 120, offen=True)])
    assert {x["cid"]: x for x in db.get_stats(conn, days=90)}[CID]["flight_count"] == 1


def test_nur_der_juengste_offene_flug_eines_piloten_online_laeuft(conn):
    _speicher(conn, [_flug(_vor(60 * 24 * 30), 84, 120, offen=True), _flug(_vor(20), 15, 20, offen=True)])
    _online(conn)
    s = {x["cid"]: x for x in db.get_stats(conn, days=90)}[CID]
    assert s["flight_count"] == 1 and s["total_duration_min"] == 84


def test_ein_gelandeter_flug_laeuft_nie(conn):
    _speicher(conn, [_flug(_vor(20), 15, 20, offen=True, gps_arrival="EDWG")])
    _online(conn)
    assert {x["cid"]: x for x in db.get_stats(conn, days=30)}[CID]["flight_count"] == 1


def test_alte_geisterfluege_im_bestand_werden_einmal_entfernt(tmp_path):
    """Der inkrementelle Lauf schreibt ältere Zeilen nie neu -- ohne das Aufräumen blieben
    sie für immer in der Jahresstatistik."""
    p = str(tmp_path / "alt.db")
    init_db(p)
    c = get_connection(p)
    for logon, dauer, nm in ((_vor(60 * 24 * 200), 0, 0), (_vor(60 * 24 * 201), 50, 70)):
        c.execute("INSERT INTO flight_cache (cid, callsign, logon_time, logoff_time, duration_min, "
                  "distance_nm, connection_closed, computed_at) VALUES (?, 'FRS61', ?, ?, ?, ?, 0, ?)",
                  (CID, logon, logon, dauer, nm, db._now_utc()))
    c.commit()
    c.close()
    init_db(p)
    c = get_connection(p)
    assert [r[0] for r in c.execute("SELECT duration_min FROM flight_cache")] == [50]


# --- Nachgelieferte ältere Flüge (365 Tage) -------------------------------------------------

def _statsim(sid, tage_alt):
    t = (datetime.now(timezone.utc) - timedelta(days=tage_alt)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return {"statsim_id": sid, "cid": CID, "callsign": "FRS61", "departure": "EDWG",
            "arrival": "EDWI", "aircraft": "C172", "logon_time": t, "logoff_time": t,
            "duration_min": 30}


def _vorgemerkt(conn):
    return db.get_app_setting(conn, db._FLIGHT_CACHE_VOLL_KEY) == "1"


def test_ein_nachgelieferter_alter_statsim_flug_merkt_den_vollen_lauf_vor(conn):
    """Bis 16.9.1 kam er erst mit dem nächsten Deploy in die Gesamtstatistik."""
    db.upsert_statsim_flights(conn, [_statsim(1, 100)])
    assert _vorgemerkt(conn)
    db.rebuild_flight_cache(conn, full=False)
    assert not _vorgemerkt(conn)


def test_ein_schon_bekannter_oder_frischer_flug_merkt_nichts_vor(conn):
    db.upsert_statsim_flights(conn, [_statsim(1, 100)])
    db.rebuild_flight_cache(conn, full=True)
    db.upsert_statsim_flights(conn, [_statsim(1, 100), _statsim(2, 1)])
    assert not _vorgemerkt(conn)


def test_ein_nachgeladener_alter_track_merkt_den_vollen_lauf_vor(conn):
    alt = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.save_statsim_positions(conn, 7, [{"latitude": 53.0, "longitude": 8.0, "ts": alt}])
    assert _vorgemerkt(conn)


def test_die_pilotenansicht_zaehlt_nur_was_im_zeitraum_startet(tmp_path, monkeypatch):
    """FRS131, 90 Tage: Ein Leg, das vor dem Beginn startete und danach landete, zählte nur in
    der Pilotenansicht."""
    from types import SimpleNamespace
    from app import main
    jetzt = datetime.now(timezone.utc)
    kurz_davor = (jetzt - timedelta(days=30, minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    drin = (jetzt - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(
        DB_PATH=str(tmp_path / "t.db"), STATSIM_API_KEY=""))
    monkeypatch.setattr(main, "canonicalize_legs", lambda conn, **kw: [
        {"logon_time": kurz_davor}, {"logon_time": drin}, {"logon_time": None}])
    init_db(str(tmp_path / "t.db"))
    import json
    antwort = json.loads(main.get_pilot_flights(CID, days=30).body)
    assert [f["logon_time"] for f in antwort] == [drin, None]


# --- Musterliste eines Piloten --------------------------------------------------------------

def test_die_musterliste_laesst_sich_auf_einen_piloten_eingrenzen(conn):
    andere = dict(_flug(_vor(300), 40, 50, typ="DR40"), cid=1000002)
    _speicher(conn, [_flug(_vor(300), 45, 60), _flug(_vor(200), 30, 40, typ="DR40"), andere])
    alle = {m["code"]: m["fluege"] for m in db.all_type_stats_for_days(conn, 30)}
    eigen = {m["code"]: m["fluege"] for m in db.all_type_stats_for_days(conn, 30, CID)}
    assert alle == {"C172": 1, "DR40": 2} and eigen == {"C172": 1, "DR40": 1}


import pathlib
INDEX = pathlib.Path(__file__).resolve().parents[1].joinpath("app/static/index.html").read_text("utf-8")


def test_das_feld_muster_oeffnet_die_musterliste_des_piloten():
    s = INDEX.index("function _pilotBilanzHtml(b, cid, name)")
    rumpf = INDEX[s:INDEX.index("// PILOTEN-BILANZ-ENDE", s)]
    assert "openTypesModal(_statsDays(), ${Number(cid)}," in rumpf
    assert "_pilotBilanzHtml(_pilotBilanz(flights), cid, pilotName)" in INDEX


def test_ueber_der_bilanz_stehen_angezeigt_gezaehlt_und_nicht_gezaehlt():
    s = INDEX.index("function renderFlightsList(")
    rumpf = INDEX[s:INDEX.index("// PILOTEN-BILANZ-ANFANG", s)]
    assert rumpf.index('<div class="piloten-zaehlung">') < rumpf.index("_pilotBilanzHtml(_pilotBilanz(flights)")
    assert "-Kennzeichen gezählt" in rumpf and "nicht gezählt" in rumpf
    assert "flights-panel-count" not in rumpf


def test_eine_chronologische_tabelle_mit_allen_fluegen():
    """Nutzer 18.10.2026: „In jedem Fall alle!!“ -- 16.9.3 hatte die nicht gezählten Flüge
    zugeklappt darunter gestellt und damit die Reihenfolge zerrissen."""
    s = INDEX.index("function renderFlightsList(")
    rumpf = INDEX[s:INDEX.index("// PILOTEN-BILANZ-ANFANG", s)]
    assert "for (const f of flights) {" in rumpf
    assert "nicht-gezaehlt" not in rumpf and "<details" not in rumpf


def test_nicht_gewertet_steht_in_einer_eigenen_spalte_vor_der_quelle():
    """Nutzer 18.10.2026: als eigene Spalte nach hinten, vor „Quelle“."""
    assert INDEX.count("<th>Track</th><th>Wertung</th><th>Quelle</th>") == 2
    s = INDEX.index("function _flightRowHtml(")
    rumpf = INDEX[s:INDEX.index("</tr>`;", s)]
    assert "<td>${trackCell}</td>\n    <td>${unscoredBadge}</td>\n    <td>${sourceTag}</td>" in rumpf
    assert "${unscoredBadge}</td>" not in rumpf.split("<td class=\"mono\">${escHtml(f.callsign")[1][:60]


def test_der_volle_aufbau_haelt_waehrend_der_rechnung_keine_schreibsperre(conn, monkeypatch):
    """Deploy 18.10.2026: Das Zurücksetzen der Vormerkung VOR der Rechnung öffnete die
    Transaktion, die Datenbank war rund 40 s für alle anderen gesperrt."""
    db.flight_cache_voll_vormerken(conn)
    conn.commit()
    gesehen = []
    monkeypatch.setattr(db, "canonicalize_legs", lambda c, **kw: gesehen.append(c.in_transaction) or [])
    db.rebuild_flight_cache(conn, full=False)
    assert gesehen == [False]
    assert not _vorgemerkt(conn)


def test_gewertete_fluege_heissen_in_der_spalte_friese():
    s = INDEX.index("const unscoredBadge = unscored")
    assert ">Friese</span>`;" in INDEX[s:s + 500]
