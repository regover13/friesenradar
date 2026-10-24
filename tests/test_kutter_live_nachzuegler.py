"""Der Kutter-Kasten im Live-Tab bleibt nach dem Ende stehen, solange Ware an Bord ist.

24.10.2026: Um 21:00 UTC verschwand der Kasten, obwohl FRS174N noch mit 273,5 kg flog -- die
Wertung wartete richtig auf ihn, die Seite zeigte ihn nicht mehr.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _funktion(name):
    m = re.search(r"\nfunction " + name + r"\(.*?\n}\n", INDEX, re.S)
    assert m, name
    return m.group(0)


@pytest.mark.skipif(not shutil.which("node"), reason="node fehlt")
@pytest.mark.parametrize("k, im_kasten", [
    ({"dtstart": "2026-10-24T19:00:00Z", "dtend": "2026-10-24T21:00:00Z", "reserved_total_kg": 0}, True),
    ({"dtstart": "2026-10-24T19:00:00Z", "dtend": "2026-10-24T21:00:00Z", "reserved_total_kg": 273.5}, True),
    ({"dtstart": "2026-10-24T18:00:00Z", "dtend": "2026-10-24T20:00:00Z", "reserved_total_kg": 273.5}, True),
    ({"dtstart": "2026-10-24T18:00:00Z", "dtend": "2026-10-24T20:00:00Z", "reserved_total_kg": 0}, False),
    ({"dtstart": "2026-10-24T21:00:00Z", "dtend": "2026-10-24T23:00:00Z", "reserved_total_kg": 0}, False),
])
def test_kasten_bleibt_solange_ware_an_bord_ist(k, im_kasten):
    js = _funktion("_kutterImLiveTab") + (
        f"\nconsole.log(JSON.stringify(_kutterImLiveTab({json.dumps(k)}, '2026-10-24T20:30:00Z')));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) is im_kasten


def test_der_live_tab_nutzt_die_regel():
    start = INDEX.index("async function fetchKutterActive")
    rumpf = INDEX[start:INDEX.index("\n}\n", start)]
    assert ".filter(k => _kutterImLiveTab(k, now))" in rumpf


@pytest.mark.skipif(not shutil.which("node"), reason="node fehlt")
@pytest.mark.parametrize("dtend, text", [
    ("2026-10-24T21:00:00Z", "läuft gerade"),
    ("2026-10-24T20:00:00Z", "· Zeit um, Nachzügler unterwegs"),
])
def test_ueberschrift_nach_dem_ende(dtend, text):
    # Nach dem Ende steht der Kasten nur noch für Nachzügler mit Ware; „läuft gerade" stimmte
    # dann nicht mehr, „abgeschlossen" auch nicht -- die Wertung wartet (Nutzer 24.10.2026).
    js = _funktion("_kutterTitelZustand") + (
        f"\nconsole.log(JSON.stringify(_kutterTitelZustand({{dtend: '{dtend}'}}, '2026-10-24T20:30:00Z')));")
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == text


def test_der_kasten_nutzt_den_zustand():
    start = INDEX.index("function _kutterBannerBlock")
    assert "_kutterTitelZustand(d, " in INDEX[start:start + 800]
