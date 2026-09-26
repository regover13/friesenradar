"""Die Flugliste eines Piloten darf nicht quadratisch mit seinen Flügen wachsen.

Bis 15.23.0 bekam jede Metrik-Hilfsfunktion (Flugzeit, Blockzeit, Distanz, Einrollen) für
JEDEN erkannten Flug die GESAMTE Positionsliste des Zeitraums und filterte sich ihr Fenster
selbst heraus. Bei einem Vielflieger (104 Flüge, 17.700 Positionen in 30 Tagen) kostete das
rund 2 s je Aufruf der Piloten-Details (Nutzer, 26.09.2026). Seitdem bekommt jede nur den
Ausschnitt, den sie ohnehin betrachtet — die Ergebnisse bleiben dieselben.
"""
from __future__ import annotations

import app.database as db
from app import geo

EDDK = geo.icao_to_coords("EDDK")
EDDW = geo.icao_to_coords("EDDW")


def _flug(stunde: int) -> list[dict]:
    """Ein Flug EDDK -> EDDW mit Rollen, Steigflug, Reise, Landung und Einrollen."""
    h = f"2026-07-02T{stunde:02d}"
    return [
        {"latitude": EDDK[0], "longitude": EDDK[1], "altitude": 302, "groundspeed": 0, "ts": f"{h}:00:00Z"},
        {"latitude": EDDK[0], "longitude": EDDK[1], "altitude": 302, "groundspeed": 8, "ts": f"{h}:02:00Z"},
        {"latitude": EDDK[0], "longitude": EDDK[1], "altitude": 1500, "groundspeed": 80, "ts": f"{h}:06:00Z"},
        {"latitude": 52.0, "longitude": 8.0, "altitude": 5000, "groundspeed": 110, "ts": f"{h}:20:00Z"},
        {"latitude": 53.0, "longitude": 8.7, "altitude": 500, "groundspeed": 90, "ts": f"{h}:38:00Z"},
        {"latitude": EDDW[0], "longitude": EDDW[1], "altitude": 10, "groundspeed": 0, "ts": f"{h}:44:00Z"},
        {"latitude": EDDW[0], "longitude": EDDW[1], "altitude": 10, "groundspeed": 10, "ts": f"{h}:46:00Z"},
        {"latitude": EDDW[0], "longitude": EDDW[1], "altitude": 10, "groundspeed": 0, "ts": f"{h}:48:00Z"},
        {"latitude": EDDW[0], "longitude": EDDW[1], "altitude": 10, "groundspeed": 0, "ts": f"{h}:52:00Z"},
    ]


def test_die_hilfsfunktionen_sehen_nur_ihren_ausschnitt(monkeypatch):
    positionen = _flug(8) + _flug(12) + _flug(16)
    gesehen: dict[str, list[int]] = {}

    def beobachten(name):
        echt = getattr(db, name)

        def huelle(positions, *a, **k):
            gesehen.setdefault(name, []).append(len(positions))
            return echt(positions, *a, **k)
        monkeypatch.setattr(db, name, huelle)

    for name in ("_air_seconds", "_distance_nm_positions", "_leg_block_seconds", "_extend_block_end"):
        beobachten(name)

    out = db._gps_flights_for_positions(positionen, plan_rows=[], source="statsim")

    assert len(out) == 3
    for name, laengen in gesehen.items():
        assert len(laengen) == 3, name
        assert max(laengen) < len(positionen), (name, laengen)


def test_die_ergebnisse_bleiben_dieselben():
    """Gegenprobe gegen die alte Art: jede Hilfsfunktion mit der vollen Liste."""
    positionen = _flug(8) + _flug(12) + _flug(16)
    out = db._gps_flights_for_positions(positionen, plan_rows=[], source="statsim")
    for f in out:
        assert f["duration_min"] == db._air_seconds(positionen, f["logon_time"], f["logoff_time"]) // 60
        assert f["distance_nm"] == db._distance_nm_positions(positionen, f["logon_time"], f["logoff_time"])
    assert [(f["departure"], f["arrival"]) for f in out] == [("EDDK", "EDDW")] * 3


# --- Kein Endpunkt mit Flugberechnung blockiert die Event-Loop -----------------------------

import ast
import inspect
import textwrap

from app import main

# Die Aufrufe, die Fluege aus Positionen rechnen. Ueber den AST gesucht wie in
# tests/test_kutter_eventloop.py -- ein Name im Kommentar zaehlt sonst als Treffer.
_FLUGRECHNUNG = {"canonicalize_legs", "canonicalize_flights", "get_stats", "get_stats_activity"}


def _rechnet_fluege(fn) -> bool:
    try:
        baum = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError, SyntaxError):
        return False
    return any(isinstance(k, ast.Call)
               and (getattr(k.func, "id", None) or getattr(k.func, "attr", None)) in _FLUGRECHNUNG
               for k in ast.walk(baum))


def _flug_endpunkte() -> list:
    return [(getattr(r, "path", "?"), r.endpoint) for r in main.app.routes
            if getattr(r, "endpoint", None) is not None and _rechnet_fluege(r.endpoint)]


def test_die_suche_findet_die_flug_endpunkte():
    pfade = [p for p, _ in _flug_endpunkte()]
    assert "/api/pilots/{cid}/flights" in pfade and len(pfade) >= 7, pfade


def test_kein_flug_endpunkt_ist_eine_koroutine():
    """Ein ``async def`` ohne ``await`` rechnet in der Event-Loop: Solange die Flugliste
    eines Vielfliegers rechnet, stehen Live-Karte und alle anderen Nutzer (#16)."""
    koroutinen = [p for p, fn in _flug_endpunkte() if inspect.iscoroutinefunction(fn)]
    assert koroutinen == [], koroutinen


# --- Deep-Link: die Statistik laedt nur einmal ------------------------------------------------

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")
_NODE = shutil.which("node")


def _funktion(name: str) -> str:
    m = re.search(rf"^(async )?function {re.escape(name)}\(", _INDEX, flags=re.M)
    assert m, f"function {name} fehlt"
    return _INDEX[m.start():_INDEX.index("\n}\n", m.start()) + 3]


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_zwei_gleichzeitige_aufrufe_holen_die_statistik_einmal():
    """Der Tab-Klick in initFromUrl() laedt die Statistik, gleich danach wartet initFromUrl()
    selbst darauf (es braucht die Pilotenliste fuer den Drill-Down). Bis 15.23.0 gingen dafuer
    zwei Anfragen raus -- samt Spezial-Events und Aktivitaet doppelt (Nutzer, 26.09.2026)."""
    stubs = """
      let currentStatsCid = null, _statsSortBy = 'last_flight', _statsSortDir = 'desc';
      let _statsLaufend = null, abrufe = 0, gezeichnet = 0;
      const el = {value: '30', innerHTML: ''};
      const document = {getElementById: () => el};
      function getUrlState() { return new URLSearchParams('tab=statistiken'); }
      function setUrlState() {}
      function renderStatsTable() { gezeichnet++; }
      function fetchSpecialEventStats() {} function fetchTopMuster() {}
      async function fetch() { abrufe++; await new Promise(r => setTimeout(r, 20));
        return {status: 200, ok: true, json: async () => []}; }
    """
    js = stubs + _funktion("fetchStats") + _funktion("_fetchStatsLauf") + """
      (async () => {
        await Promise.all([fetchStats(), fetchStats()]);
        const erst = abrufe;
        await fetchStats();                        // spaeter: wieder ein frischer Abruf
        console.log(JSON.stringify([erst, abrufe, gezeichnet]));
      })();
    """
    erg = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert erg.returncode == 0, erg.stderr
    assert json.loads(erg.stdout.strip().splitlines()[-1]) == [1, 2, 2]


def test_der_laufende_abruf_steht_vor_dem_ersten_aufruf():
    assert _INDEX.index("let _statsLaufend") < _INDEX.index("\ninitFromUrl();")
