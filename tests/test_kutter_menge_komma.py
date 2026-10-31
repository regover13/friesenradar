"""Frachtmengen im Admin: auch krumme Werte und Kommazahlen (31.10.2026).

Das Feld hatte die Schrittweite 10: 24 kg ließ der Browser nicht zu, und jede solche Zeile
blockierte das Speichern des ganzen Events. Dazu rundete das Bearbeiten die Menge (aus 0,4 wurde
0, die Zeile fiel beim Speichern weg) und löschte das Symbol jeder Ware außerhalb des Katalogs.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.transport_stacks import derive_stacks

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
ADMIN = (STATIC / "admin.html").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


def _funktion(quelle, name):
    m = re.search(r"\n\s*function " + name + r"\(.*?\n\s*}\n", quelle, re.S)
    assert m, name
    return m.group(0)


def test_das_mengenfeld_ist_ein_textfeld_mit_eigener_pruefung():
    # type="number" verschluckt das Komma, wenn der Browser nicht auf Deutsch läuft: Aus 2,5 wurde
    # in der Probe still 25 (31.10.2026). Das Feld darf daran nicht hängen.
    m = re.search(r'<input[^>]*class="ke-c-kg"[^>]*>', ADMIN)
    assert m and 'type="text"' in m.group(0) and 'inputmode="decimal"' in m.group(0)
    assert 'pattern="' in m.group(0)


@pytest.mark.skipif(not shutil.which("node"), reason="node fehlt")
@pytest.mark.parametrize("ein, aus", [
    ("2,5", 2.5), ("2.5", 2.5), ("24", 24), (" 24,3 ", 24.3), ("0,4", 0.4), ("", None),
    ("1.000", None), ("1,25", None), ("abc", None), ("-3", None), ("2,5,1", None),
])
def test_die_menge_wird_mit_komma_und_punkt_richtig_gelesen(ein, aus):
    js = _funktion(ADMIN, "_keMenge") + f"\nconsole.log(JSON.stringify(_keMenge({json.dumps(ein)})));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == aus


def test_bearbeiten_rundet_die_menge_nicht():
    assert "keCargoRow(c.name, Math.round(c.target_kg)" not in ADMIN
    assert re.search(r"keCargoRow\(c\.name, c\.target_kg, c\.departure, c\)", ADMIN)


def test_speichern_behaelt_das_symbol_einer_ware_ausserhalb_des_katalogs():
    rumpf = _funktion(ADMIN, "keCollectCargo")
    assert "_keZeilenBestand(r, name)" in rumpf
    bestand = _funktion(ADMIN, "_keZeilenBestand")
    assert "origName" in bestand and "origEmoji" in bestand and "origMax" in bestand


@pytest.mark.skipif(not shutil.which("node"), reason="node fehlt")
@pytest.mark.parametrize("kg, text", [
    (2.5, "2,5 kg"), (0.4, "0,4 kg"), (24, "24 kg"), (273.5, "274 kg"), (0, "0 kg"), (10000, "10 t"),
])
def test_kleine_kommamengen_stehen_unverfaelscht_da(kg, text):
    js = _funktion(INDEX, "_kfmtT") + f"\nconsole.log(JSON.stringify(_kfmtT({kg})));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == text


def _lauf(mengen):
    manifest = [{"name": n, "target_kg": kg, "departure": "EDWY", "added_at": "2026-01-01T10:00:00Z"}
                for n, kg in mengen]
    ev = [
        {"ts": "2026-01-01T10:01:00Z", "kind": "login", "cid": 1, "airport": "EDWY", "capacity_kg": 292.0},
        {"ts": "2026-01-01T10:05:00Z", "kind": "takeoff", "cid": 1, "airport": None, "capacity_kg": 292.0},
        {"ts": "2026-01-01T10:30:00Z", "kind": "landing", "cid": 1, "airport": "EDWG", "capacity_kg": 292.0},
    ]
    return derive_stacks(manifest=manifest, events=ev, destination="EDWG", loading_airports={"EDWY"})


def test_kommamengen_kommen_vollstaendig_an():
    r = _lauf([("A", 2.5), ("B", 0.1), ("C", 0.2)])
    am_ziel = r["stacks"]["EDWG"]
    assert am_ziel["A"] == pytest.approx(2.5)
    assert am_ziel["B"] + am_ziel["C"] == pytest.approx(0.3)
    assert sum(r["stacks"]["EDWY"].values()) == pytest.approx(0.0)
