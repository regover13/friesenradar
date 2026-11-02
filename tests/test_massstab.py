"""Maßstab in nautischen Meilen unten links auf jeder Karte (Wunsch aus dem Forum, 02.11.2026).

Leaflets eigener Maßstab kennt nur km und Landmeilen. Gebraucht werden NM.
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
@pytest.mark.parametrize("meter, max_px, nm, text", [
    (185200, 100, 100, "100 NM"),      # genau 100 NM auf 100 px
    (370400, 100, 200, "200 NM"),
    (27780, 100, 10, "10 NM"),          # 15 NM auf 100 px -> 10 NM
    (1852, 100, 1, "1 NM"),
    (1389, 100, 0.5, "0,5 NM"),         # 0,75 NM -> 0,5 NM
    (300, 100, 0.1, "0,1 NM"),
])
def test_glatter_wert_und_passende_breite(meter, max_px, nm, text):
    js = _funktion("_nmMassstabWert") + f"\nconsole.log(JSON.stringify(_nmMassstabWert({meter}, {max_px})));"
    out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert out["nm"] == nm and out["text"] == text
    assert out["px"] == pytest.approx(max_px * nm * 1852 / meter, abs=1)
    assert 0 < out["px"] <= max_px


@pytest.mark.parametrize("karte", ["liveMap", "trackMap", "eventsMap"])
def test_jede_karte_hat_den_massstab(karte):
    assert f"_nmMassstab({karte});" in INDEX


def test_der_massstab_steht_ueber_dem_vollbild_knopf():
    # Der Vollbild-Knopf sitzt unten links absolut auf 10 px, die Ecke liegt darunter.
    assert re.search(r"\.leaflet-bottom\.leaflet-left \.nm-massstab \{[^}]*margin-bottom", INDEX)


def test_der_massstab_blendet_sich_nach_ein_paar_sekunden_aus():
    # Nutzer 02.11.2026: nicht dauerhaft über der Karte, vor allem im Kniebrett.
    rumpf = _funktion("_nmMassstab")
    assert "nm-sichtbar" in rumpf and "setTimeout" in rumpf and "clearTimeout" in rumpf
    assert re.search(r"\.nm-massstab \{[^}]*opacity: 0", INDEX)
    assert re.search(r"\.nm-massstab\.nm-sichtbar \{[^}]*opacity: 1", INDEX)
