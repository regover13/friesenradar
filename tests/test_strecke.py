# -*- coding: utf-8 -*-
"""Die Parameter einer Deichkontrolle (``app/strecke.py``) -- Teilung, Geometrie, Höhen.

Spec: docs/superpowers/specs/2026-10-10-deichkontrolle-design.md.
"""
from __future__ import annotations

import json
import math

import pytest

from app import strecke as st
from app.abdeckung import abdeckung

LAT, LON = 53.72, 7.25
KM_LAT = 111.32
KM_LON = 111.32 * math.cos(math.radians(LAT))


def _ost(km):
    return LON + km / KM_LON


def _nord(km):
    return LAT + km / KM_LAT


def _ev(pts, **mehr):
    return {"punkte_json": json.dumps(pts), **mehr}


GERADE = [[LAT, LON], [LAT, _ost(10.0)]]            # 10 km nach Osten


def test_die_abschnittslaenge_ist_das_doppelte_des_korridors():
    ev = _ev(GERADE, korridor_m=500)
    anzahl, schritt = st.teilung(ev)
    assert anzahl == 10 and schritt == pytest.approx(1.0, rel=1e-3)
    assert len(st.ziele(ev)) == 10
    assert all(z[3] == pytest.approx(0.5) for z in st.ziele(ev))


def test_die_laenge_wird_gleichmaessig_verteilt_statt_einen_rest_zu_lassen():
    ev = _ev([[LAT, LON], [LAT, _ost(10.4)]], korridor_m=500)
    anzahl, schritt = st.teilung(ev)
    assert anzahl == 11 and schritt == pytest.approx(10.4 / 11, rel=1e-3)


def test_die_vorgaben_gelten_ohne_angabe():
    assert st.regeln({}) == {"korridor_m": 500.0, "hoehe_max_ft": 1000.0,
                             "gs_max_kt": 140.0, "gs_min_kt": 30.0}


def test_die_geometrie_folgt_den_knicken_der_strecke():
    """Ein Abschnitt, der über einen geklickten Punkt läuft, trägt diesen Punkt mit."""
    knick = [[LAT, LON], [LAT, _ost(1.5)], [_nord(1.5), _ost(1.5)]]     # 3 km mit Ecke
    ev = _ev(knick, korridor_m=500)
    geo = st.geometrie(ev)
    assert len(geo) == 3
    assert geo[0][0] == [pytest.approx(LAT), pytest.approx(LON)]
    assert len(geo[1]) == 3, "der mittlere Abschnitt läuft über die Ecke"
    assert geo[1][1] == [pytest.approx(LAT, abs=1e-6), pytest.approx(_ost(1.5), abs=1e-6)]
    assert geo[2][-1] == [pytest.approx(_nord(1.5), abs=1e-6), pytest.approx(_ost(1.5), abs=1e-6)]
    # Lückenlos: Jedes Stück beginnt, wo das vorige endet.
    for a, b in zip(geo, geo[1:]):
        assert a[-1] == b[0]


def test_ohne_gelaendehoehen_gibt_es_keine_hoehenregel():
    ev = _ev(GERADE, korridor_m=500)
    assert st.grund(ev) is None and st.hoehe_je_ziel(ev) is None


def test_gelaendehoehen_einer_anderen_teilung_gelten_nicht():
    """Korridor geändert, Höhen noch nicht neu geholt: lieber keine Regel als eine falsche."""
    ev = _ev(GERADE, korridor_m=500, grund_json=json.dumps([10.0] * 5))
    assert st.grund(ev) is None


def test_die_hoechsthoehe_ist_gelaende_plus_vorgabe_je_abschnitt():
    grund = [0.0, 0.0, 0.0, 0.0, 0.0, 5000.0, 5000.0, 5000.0, 5000.0, 5000.0]
    ev = _ev(GERADE, korridor_m=500, hoehe_max_ft=1000, grund_json=json.dumps(grund))
    g = st.hoehe_je_ziel(ev)
    assert g["a0"] == 1000.0 and g["a9"] == 6000.0


def _flug(alt_ft, versatz_km=0.0):
    """Von West nach Ost an der Strecke entlang, ein Punkt je Kilometer (Segmente über 6 km
    verwirft die Abdeckungsrechnung als Sprung)."""
    punkte = [(_nord(versatz_km), _ost(-0.5 + k), alt_ft, 100.0,
               "2026-10-10T18:%02d:%02d" % divmod(k * 20, 60) + "Z") for k in range(12)]
    return [(7, punkte)]


def test_wer_genau_auf_der_strecke_fliegt_deckt_sie_lueckenlos_ab():
    ev = _ev(GERADE, korridor_m=500, grund_json=json.dumps([0.0] * 10))
    erg = abdeckung(_flug(800.0), st.ziele(ev), st.fenster(ev), st.hoehe_je_ziel(ev))
    assert erg.anteil == 1.0


def test_wer_ausserhalb_des_korridors_fliegt_deckt_nichts_ab():
    ev = _ev(GERADE, korridor_m=500, grund_json=json.dumps([0.0] * 10))
    innen = abdeckung(_flug(800.0, 0.45), st.ziele(ev), st.fenster(ev), st.hoehe_je_ziel(ev))
    aussen = abdeckung(_flug(800.0, 0.55), st.ziele(ev), st.fenster(ev), st.hoehe_je_ziel(ev))
    assert innen.anteil == 1.0 and aussen.anteil == 0.0


def test_am_hang_zaehlt_nur_der_abschnitt_unter_dessen_grenze_man_bleibt():
    grund = [0.0] * 5 + [5000.0] * 5
    ev = _ev(GERADE, korridor_m=500, hoehe_max_ft=1000, grund_json=json.dumps(grund))
    erg = abdeckung(_flug(5500.0), st.ziele(ev), st.fenster(ev), st.hoehe_je_ziel(ev))
    assert sorted(erg.treffer) == ["a5", "a6", "a7", "a8", "a9"]


def test_die_box_umschliesst_die_strecke():
    ev = _ev([[53.0, 7.0], [54.0, 8.5], [53.5, 6.5]])
    assert st.box(ev) == (53.0, 6.5, 54.0, 8.5)


@pytest.mark.parametrize("pts, korridor, teil", [
    ([[LAT, LON]], 500, "mindestens zwei Punkte"),
    ([[LAT, LON], [LAT, LON]], 500, "derselben Stelle"),
    ([[LAT, LON], [95.0, LON]], 500, "außerhalb der Karte"),
    (GERADE, 10, "Korridor muss zwischen"),
    (GERADE, "viel", "Zahl"),
    ("unsinn", 500, "nicht lesbar"),
    ([[LAT, LON], [LAT, LON + 5.0]], 50, "höchstens 2000"),
])
def test_die_pruefung_sagt_in_einem_satz_was_nicht_geht(pts, korridor, teil):
    with pytest.raises(ValueError) as e:
        st.pruefen(pts, korridor)
    assert teil in str(e.value)


def test_die_pruefung_gibt_saubere_punkte_zurueck():
    assert st.pruefen([["53.5", 7], (54, "8.25")], 500) == [(53.5, 7.0), (54.0, 8.25)]
