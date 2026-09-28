"""Das Nachspiel-Werkzeug (scripts/reddung_nachspielen.py) bildet den echten Abend nach.

Gesichert am 28.09.2026: die FriesenReddung „Verschollen in der Eifel" vom 27.09.2026,
anonymisiert (tests/fixtures/reddung_2026-09-27_eifel.json). Nachgespielt mit dem echten
Poller muss dasselbe herauskommen wie am Abend -- sonst taugt das Werkzeug nicht, um neue
Funktionen ohne Simulator zu prüfen. Toleranz eine Minute: Die Brügge meldete im Sekundentakt,
der Datensatz hat nur VATSIM-Punkte (alle ~15 s).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

_WURZEL = Path(__file__).resolve().parents[1]
_FIXTURE = _WURZEL / "tests" / "fixtures" / "reddung_2026-09-27_eifel.json"


def _werkzeug():
    spec = importlib.util.spec_from_file_location(
        "reddung_nachspielen", _WURZEL / "scripts" / "reddung_nachspielen.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod          # dataclasses sucht das Modul dort
    spec.loader.exec_module(mod)
    return mod


def _zeit(zeile_ts: str) -> datetime:
    return datetime.strptime(zeile_ts, "%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(scope="module")
def gestern():
    w = _werkzeug()
    daten = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    sz = next(s for s in w.szenarien(daten) if s.name == "gestern")
    return w.spielen(daten, sz), daten


def _eintrag(bericht, praefix):
    return [t for _, t in bericht.zeitleiste if t.startswith(praefix)]


def test_der_datensatz_ist_anonym():
    text = _FIXTURE.read_text(encoding="utf-8")
    daten = json.loads(text)
    assert all(p["cid"] >= 91001 and p["callsign"].startswith("FRS9") for p in daten["piloten"])
    assert "name" not in json.dumps(daten["piloten"])


def test_fund_aufnahme_und_einlieferung_wie_am_abend(gestern):
    bericht, daten = gestern
    echt = daten["echt"]
    rz = {p["cid"]: p["callsign"] for p in daten["piloten"]}
    gef = _eintrag(bericht, "gefunden: ")[0].split()
    assert gef[2] == rz[echt["gefunden"]["cid"]]
    assert abs((_zeit(gef[1]) - _zeit(echt["gefunden"]["ts"])).total_seconds()) <= 60
    aufg = [e.split() for e in _eintrag(bericht, "aufgenommen: 2")]
    assert aufg[0][2] == rz[echt["erste_aufnahme"]["cid"]], "zuerst der, der danach abstürzte"
    assert aufg[-1][2] == rz[echt["aufgenommen"]["cid"]], "nach der Freigabe der Retter"
    ein = _eintrag(bericht, "eingeliefert: ")[0].split()
    assert ein[2] == rz[echt["eingeliefert"]["cid"]] and ein[-1] == echt["eingeliefert"]["icao"]
    assert abs((_zeit(ein[1]) - _zeit(echt["eingeliefert"]["ts"])).total_seconds()) <= 60


def test_das_wrack_steht_fuer_alle_simulatoren_und_die_fackel_wechselt_die_farbe(gestern):
    bericht, _ = gestern
    stufen = [t for t in _eintrag(bericht, "im Simulator: ") if "fackel=" in t]
    farben = [t.split("fackel=")[1].split(",")[0] for t in stufen]
    assert farben[:3] == ["rauch_signalorange", "rauch_hellblau", "rauch_signalorange"]
    assert farben[-1] == "rauch_signalrot"
    assert all("licht=licht" in t for t in stufen), "Licht am Fuß jeder Fackel"
    assert all("havarist=flugzeug_echo" in t for t in stufen), "eine Zeile für alle Simulatoren"
