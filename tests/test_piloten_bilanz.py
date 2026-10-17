"""Bilanz über der Flugliste eines Piloten (Wunsch aus der Gruppe, 14.10.2026).

Gerechnet wird in der Seite aus genau der Liste, die darunter steht -- so stimmen Bilanz und
Liste immer überein, auch nach „Alle Flüge laden“. Gezählt wird, was auch die Statistik zählt:
keine Flüge unter fremdem Rufzeichen, keine laufenden, keine Geisterflüge (0 min, kein Weg).
"""
import json
import pathlib
import shutil
import subprocess

import pytest

INDEX = pathlib.Path(__file__).resolve().parents[1].joinpath("app/static/index.html").read_text("utf-8")
_NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(_NODE is None, reason="node fehlt")


def _bilanz(fluege: list[dict]) -> dict:
    start = INDEX.index("// PILOTEN-BILANZ-ANFANG")
    ende = INDEX.index("// PILOTEN-BILANZ-ENDE")
    js = ("const _callsignPrefix = 'FRS';\nconst _LIVE_MAX_AGE_MS = 5 * 60 * 1000;\n"
          "function escHtml(s) { return String(s); }\n"
          + INDEX[INDEX.index("function _isLiveLeg"):INDEX.index("// Gemeinsame Zeilen-Logik")]
          + INDEX[start:ende]
          + "\nconst f = " + json.dumps(fluege) + ";\n"
          "console.log(JSON.stringify({b: _pilotBilanz(f), html: _pilotBilanzHtml(_pilotBilanz(f))}));")
    p = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def _vor_einer_minute():
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _flug(**kw):
    f = {"callsign": "FRS102", "source": "friesenspy", "duration_min": 60, "block_min": 70,
         "distance_nm": 100, "gps_departure": "EDDW", "gps_arrival": "EDXR",
         "aircraft": "P24", "aircraft_icao": "P24", "logon_time": "2026-10-10T10:00:00Z",
         "logoff_time": "2026-10-10T11:10:00Z"}
    f.update(kw)
    return f


def test_die_summen():
    b = _bilanz([_flug(), _flug(duration_min=30, block_min=40, distance_nm=50.4)])["b"]
    assert (b["fluege"], b["flugzeit"], b["blockzeit"], b["strecke"]) == (2, 90, 110, 150)
    assert b["schnitt"] == 45


def test_der_laengste_flug_mit_strecke():
    b = _bilanz([_flug(), _flug(duration_min=135, gps_departure="EDDK", gps_arrival="EDDS")])["b"]
    assert b["laengster"] == {"min": 135, "von": "EDDK", "nach": "EDDS"}


def test_verschiedene_plaetze_aus_start_und_landung():
    b = _bilanz([_flug(), _flug(gps_departure="EDXR", gps_arrival="EDDW"),
                 _flug(gps_departure="EDDW", gps_arrival="")])["b"]
    assert b["plaetze"] == 2


def test_das_meistgeflogene_muster():
    b = _bilanz([_flug(aircraft_icao="B105"), _flug(), _flug(), _flug(aircraft_icao="", aircraft="P24")])["b"]
    assert b["muster"] == {"code": "P24", "anzahl": 3}


def test_was_die_statistik_nicht_zaehlt_zaehlt_hier_auch_nicht():
    b = _bilanz([_flug(),
                 _flug(callsign="DLH123"),                                    # fremdes Rufzeichen
                 _flug(duration_min=0, distance_nm=0),                        # Geisterflug
                 _flug(gps_arrival="", logoff_time=None,                      # läuft gerade
                       last_pos_ts=_vor_einer_minute())])["b"]
    assert b["fluege"] == 1


def test_fluege_ohne_strecke_werden_benannt_statt_still_als_null_gezaehlt():
    """StatSim-Flüge ohne Spur haben noch keine Strecke. Die Summe wäre sonst zu niedrig,
    ohne dass es jemand merkt."""
    r = _bilanz([_flug(), _flug(source="statsim", distance_nm=0)])
    assert (r["b"]["strecke"], r["b"]["ohne_strecke"]) == (100, 1)
    assert "1 ohne Strecke" in r["html"]


def test_blockzeit_nur_aus_fluegen_die_eine_haben():
    b = _bilanz([_flug(), _flug(block_min=None)])["b"]
    assert b["blockzeit"] == 70


def test_ohne_gezaehlte_fluege_keine_bilanz():
    assert _bilanz([_flug(callsign="DLH1")])["html"] == ""


def test_die_bilanz_steht_ueber_der_liste():
    rumpf = INDEX[INDEX.index("function renderFlightsList"):INDEX.index("function _ordenHtml")]
    assert rumpf.index("_pilotBilanzHtml(_pilotBilanz(flights), cid, pilotName)") < rumpf.index("<table>")


def test_alle_acht_werte_stehen_im_kasten():
    html = _bilanz([_flug()])["html"]
    for titel in ("Flüge", "Flugzeit", "Blockzeit", "Strecke", "Schnitt", "Längster", "Plätze", "Muster"):
        assert f">{titel}<" in html
