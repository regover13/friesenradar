# -*- coding: utf-8 -*-
"""Wie schnell, wie hoch? Die Regeln des Abends als Schilder im Reddung-Block (28.09.2026).

Nutzer: „Ich werde im Event ständig gefragt, wie schnell, wie hoch darf ich fliegen?" Prominent
die Suchgrenzen als Schilder wie auf der Autobahn (Höchstgeschwindigkeit, Höhe), klein darunter
die Regeln zum Finden und Aufnehmen -- alles aus den Parametern des Events, nicht fest verdrahtet.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import app.main as main
from app import reddung as rd
from tests.test_reddung_api import SEKTOR, _anlegen, _laufend, db  # noqa: F401  (Fixture)

_INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")
_NODE = shutil.which("node")


def test_die_regeln_kommen_aus_den_parametern():
    ev = {"gs_max_kt": 120, "gs_min_kt": 40, "hoehe_max_ft": 1500, "fund_radius_m": 300,
          "fund_hoehe_ft": 800, "aufnahme_radius_m": 250, "aufnehmen_noetig": 1, "landung_noetig": 0}
    r = rd.regeln(ev)
    assert (r["gs_max_kt"], r["gs_min_kt"], r["hoehe_max_ft"]) == (120, 40, 1500)
    assert (r["fund_radius_m"], r["fund_hoehe_ft"], r["aufnahme_radius_m"]) == (300, 800, 250)
    assert r["aufnehmen_noetig"] is True and r["landung_noetig"] is False
    assert r["schwebe_gs_kt"] == rd.SCHWEBE_GS_KT


def test_ohne_eintrag_gelten_die_vorgaben():
    r = rd.regeln({})
    assert (r["gs_max_kt"], r["gs_min_kt"], r["hoehe_max_ft"]) == (140, 30, 2000)
    assert (r["fund_radius_m"], r["fund_hoehe_ft"], r["aufnahme_radius_m"]) == (150, 1000, 150)


def test_die_regeln_stehen_in_der_oeffentlichen_liste_und_verraten_keinen_ort(db):
    _anlegen(**_laufend(), havarist_lat=53.72, havarist_lon=7.25, havarist_grund_ft=1864.0)
    eintrag = main.reddung_events()[0]
    assert eintrag["regeln"]["gs_max_kt"] == 140
    text = json.dumps(eintrag["regeln"])
    for geheim in ("53.72", "7.25", "1864", "lat", "lon", "grund"):
        assert geheim not in text, geheim


def _funktion(name):
    m = re.search(rf"^(async )?function {re.escape(name)}\(", _INDEX, flags=re.M)
    assert m, name
    return _INDEX[m.start():_INDEX.index("\n}\n", m.start()) + 3]


def _render(regeln):
    js = _funktion("escHtml") + _funktion("_reddungSchild") + _funktion("_reddungRegelnHtml") + f"""
      console.log(JSON.stringify(_reddungRegelnHtml({{regeln: {json.dumps(regeln)}}})));
    """
    erg = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert erg.returncode == 0, erg.stderr
    return json.loads(erg.stdout.strip().splitlines()[-1])


_BASIS = {"gs_max_kt": 140, "gs_min_kt": 30, "hoehe_max_ft": 2000, "fund_radius_m": 300,
          "fund_hoehe_ft": 1000, "aufnahme_radius_m": 150, "aufnehmen_noetig": True,
          "landung_noetig": True, "schwebe_gs_kt": 30}


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_die_schilder_zeigen_geschwindigkeit_und_hoehe():
    html = _render(_BASIS)
    assert html.count("<svg") == 2, "zwei Schilder"
    assert ">140<" in html and ">2000<" in html
    assert "ft AGL" in html and "kt" in html
    assert "ab 30 kt" in html, "die Untergrenze klein dazu"


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_klein_darunter_finden_und_aufnehmen_mit_landung():
    html = _render(_BASIS)
    klein = html[html.index('class="reddung-regeln-klein"'):]
    assert "300 m" in klein and "1000 ft AGL" in klein
    assert "Landung" in klein and "Full Stop" in klein and "150 m" in klein


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_schwebend_heisst_unter_dreissig_knoten():
    klein = _render({**_BASIS, "landung_noetig": False})
    assert "Schwebeflug" in klein and "unter 30 kt" in klein and "Full Stop" not in klein


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_ohne_aufnehmen_steht_das_dabei():
    klein = _render({**_BASIS, "aufnehmen_noetig": False})
    assert "Kein Aufnehmen" in klein and "Full Stop" not in klein


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_ohne_regeln_steht_nichts():
    js = _funktion("escHtml") + _funktion("_reddungSchild") + _funktion("_reddungRegelnHtml") + """
      console.log(JSON.stringify(_reddungRegelnHtml({})));
    """
    erg = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert json.loads(erg.stdout.strip().splitlines()[-1]) == ""


def test_live_block_und_reddung_ansicht_zeigen_die_regeln():
    block = _funktion("_reddungBannerBlock")
    assert "if (!fertig) html += _reddungRegelnHtml(r)" in block
    bilanz = _funktion("_reddungBilanzHtml")
    assert "if (!vorbei) html += _reddungRegelnHtml(r)" in bilanz



def test_die_regeln_tragen_keine_msl_hoehe():
    """MSL minus AGL ergäbe die Geländehöhe am Wrack -- und die verrät die Lage (Nutzer,
    28.09.2026: „Doch ohne MSL. Die Angabe verrät die Höhe des Wracks!"). Auch nicht, wenn
    das Gelände bekannt ist."""
    r = rd.regeln({"havarist_grund_ft": 1864.3, "hoehe_max_ft": 2000, "fund_hoehe_ft": 1000})
    assert not [k for k in r if "msl" in k.lower()], r
    assert 1864.3 + 2000 not in r.values() and 1864.3 + 1000 not in r.values()
