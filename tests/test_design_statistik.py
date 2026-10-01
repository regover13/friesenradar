"""Statistik-Diagramm folgt dem Design (Spec helles Design; Review Focus 3)."""
import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _chart():
    a = INDEX.index("function renderActivityChart(")
    return INDEX[a:INDEX.index("function renderStatsSummary(", a)]


def test_keine_festen_oberflaechenfarben_mehr():
    c = _chart()
    for alt in ("'#071525'", "'#6b9ab8'", "'#d4e8f5'", "rgba(45,156,219,0.05)", "rgba(45,156,219,0.07)"):
        assert alt not in c, alt
    assert "_themaFarbe('--bg-panel')" in c


def test_datenlinien():
    c = _chart()
    # Stunden laufen ueber --amber (dunkel #f0a500, identisch); #f0a500 haette auf Weiss 1,9:1.
    assert "'#f0a500'" not in c and "_themaFarbe('--amber')" in c
    # Dauer bleibt Friesenrot; Fluege (#00d4e0, 1,7:1 auf Weiss) bekommt --chart-fluege.
    assert "'#D31141'" in c
    assert "_themaFarbe('--chart-fluege')" in c


def test_umschalten_zeichnet_neu():
    assert "_aktivitaetZuletzt = { data: data, grouping: grouping };" in _chart()
    a = INDEX.index("function _aktivitaetNeuZeichnen(")
    rumpf = INDEX[a:INDEX.index("\n}", a)]
    assert "_activityChart.destroy()" in rumpf and "renderActivityChart(" in rumpf
    assert "_designHaken.push(_aktivitaetNeuZeichnen);" in INDEX
