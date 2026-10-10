# -*- coding: utf-8 -*-
"""Objektgruppen streuen (app/gruppen.py) -- die sechs Anforderungen aus der Spec, Abschnitt 15."""
import math

import pytest

from app import gruppen
from app.geo import haversine


def _abstaende_m(objekte):
    return [haversine(a["lat"], a["lon"], b["lat"], b["lon"]) * 1000.0
            for i, a in enumerate(objekte) for b in objekte[i + 1:]]


def test_derselbe_startwert_ergibt_dieselbe_lage():
    a = gruppen.streuen(54.1, 8.9, 5, 15, 10, 40, "abc")
    b = gruppen.streuen(54.1, 8.9, 5, 15, 10, 40, "abc")
    assert a == b


def test_die_lage_haengt_nicht_an_der_python_fassung():
    """Festgehaltene Werte: Aendern sie sich, stuenden nach einem Update andere Objekte im
    Simulator als die gespeicherte Lage sagt."""
    lage = gruppen.streuen(54.0, 9.0, 3, 3, 10, 20, "fest")
    assert lage == [{"lat": 54.0, "lon": 9.0, "kurs": 268.5},
                    {"lat": 53.9998356, "lon": 8.9999888, "kurs": 179.2},
                    {"lat": 53.9997977, "lon": 8.9998088, "kurs": 270.7}]


def test_ein_anderer_startwert_ergibt_eine_andere_lage():
    a = gruppen.streuen(54.1, 8.9, 8, 8, 10, 40, "eins")
    b = gruppen.streuen(54.1, 8.9, 8, 8, 10, 40, "zwei")
    assert a != b


def test_die_menge_liegt_zwischen_mindest_und_hoechstmenge_und_schwankt():
    mengen = {len(gruppen.streuen(54.1, 8.9, 4, 9, 10, 40, f"s{i}")) for i in range(60)}
    assert min(mengen) >= 4 and max(mengen) <= 9
    assert len(mengen) > 1


def test_kein_objekt_steht_naeher_als_der_mindestabstand():
    for i in range(20):
        objekte = gruppen.streuen(54.1, 8.9, 20, 30, 15, 40, f"s{i}")
        assert min(_abstaende_m(objekte)) >= 15 * 0.995     # Kugel gegen Ebene


def test_auch_dicht_gepackt_kommt_die_volle_menge_ohne_unterschreitung():
    """Mindest- gleich Hoechstabstand laesst kaum Platz -- die Menge stimmt trotzdem."""
    objekte = gruppen.streuen(54.1, 8.9, 60, 60, 20, 20, "eng")
    assert len(objekte) == 60
    assert min(_abstaende_m(objekte)) >= 20 * 0.995


def test_jedes_objekt_haengt_im_hoechstabstand_an_einem_anderen():
    """Ein Haufen, keine verstreuten Einzelstuecke."""
    objekte = gruppen.streuen(54.1, 8.9, 25, 25, 10, 50, "haufen")
    for i, a in enumerate(objekte):
        naechster = min(haversine(a["lat"], a["lon"], b["lat"], b["lon"]) * 1000.0
                        for j, b in enumerate(objekte) if j != i)
        assert naechster <= 50 * 1.005


def test_eine_gruppe_darf_aus_einem_objekt_bestehen():
    objekte = gruppen.streuen(54.1, 8.9, 1, 1, 10, 40, "baake")
    assert objekte == [{"lat": 54.1, "lon": 8.9, "kurs": objekte[0]["kurs"]}]


def test_richtung_gewuerfelt_oder_fest():
    frei = gruppen.streuen(54.1, 8.9, 10, 10, 10, 40, "x")
    assert len({o["kurs"] for o in frei}) > 1
    assert all(0.0 <= o["kurs"] < 360.0 for o in frei)
    fest = gruppen.streuen(54.1, 8.9, 10, 10, 10, 40, "x", richtung=270)
    assert {o["kurs"] for o in fest} == {270.0}


def test_eine_feste_richtung_aendert_die_lage_nicht():
    frei = gruppen.streuen(54.1, 8.9, 10, 10, 10, 40, "x")
    fest = gruppen.streuen(54.1, 8.9, 10, 10, 10, 40, "x", richtung=90)
    assert [(o["lat"], o["lon"]) for o in frei] == [(o["lat"], o["lon"]) for o in fest]


def test_die_streuung_ist_in_metern_gleich_weit_nach_ost_wie_nach_nord():
    """Am 54. Breitengrad ist ein Grad Laenge nur gut halb so lang wie ein Grad Breite."""
    objekte = gruppen.streuen(54.0, 9.0, 60, 60, 20, 60, "rund")
    nord = max(abs(o["lat"] - 54.0) for o in objekte) * 111_320.0
    ost = max(abs(o["lon"] - 9.0) for o in objekte) * 111_320.0 * math.cos(math.radians(54.0))
    assert 0.4 < nord / ost < 2.5


@pytest.mark.parametrize("angaben, wort", [
    ((0, 5, 10, 40), "mindestens ein Objekt"),
    ((5, 4, 10, 40), "Höchstmenge"),
    ((1, gruppen.MENGE_MAX + 1, 10, 40), "Höchstens"),
    ((1, 5, 0, 40), "Mindestabstand"),
    ((1, 5, 50, 40), "Höchstabstand"),
    ((1, 5, 10, 5000), "Höchstabstand"),
    (("x", 5, 10, 40), "ganze Zahl"),
    ((1, 5, "x", 40), "Zahl"),
])
def test_unsinnige_angaben_werden_mit_einem_satz_abgelehnt(angaben, wort):
    with pytest.raises(ValueError, match=wort):
        gruppen.pruefen(*angaben)


def test_startwerte_sind_frisch():
    assert gruppen.startwert() != gruppen.startwert()


@pytest.mark.parametrize("angaben", [
    (3, 3, 10, float("nan")), (3, 3, float("nan"), 40), (3, 3, 10, float("inf")),
    (float("nan"), 3, 10, 40), (3, float("inf"), 10, 40), (3, 3, 10, "nan"),
])
def test_nan_und_unendlich_kommen_nicht_durch(angaben):
    """Mit NaN ist jeder Vergleich falsch -- die Grenzen griffen nicht, und ``streuen`` liefe in
    eine Endlosschleife (Befund vom 10.10.2026)."""
    with pytest.raises(ValueError):
        gruppen.pruefen(*angaben)


@pytest.mark.parametrize("richtung", [float("nan"), float("inf"), "nan"])
def test_eine_richtung_muss_endlich_sein(richtung):
    with pytest.raises(ValueError, match="Richtung"):
        gruppen.pruefen(3, 3, 10, 40, richtung)


def test_ein_unlesbarer_ort_wird_abgelehnt():
    for lat in (float("nan"), None, "abc"):
        with pytest.raises(ValueError, match="Ort"):
            gruppen.streuen(lat, 9.0, 3, 3, 10, 40, "x")


def test_eine_halbe_menge_wird_nicht_still_abgerundet():
    with pytest.raises(ValueError, match="ganze Zahl"):
        gruppen.pruefen(5.9, 9, 10, 40)
    assert gruppen.pruefen(5.0, "9", 10, 40)[:2] == (5, 9)


def test_auch_im_ausweichpfad_haengt_jedes_objekt_an_einem_anderen():
    """Dicht gepackt (Mindest- gleich Hoechstabstand) findet der Wuerfel oft keinen Platz; das
    Objekt haengt sich dann an den Rand. Vorher ging es von der Mitte nach aussen und landete bis
    zum Anderthalbfachen des Hoechstabstands vom naechsten Nachbarn (Befund vom 10.10.2026)."""
    for menge, abstand in ((60, 1), (10, 10), (40, 5)):
        for i in range(120):
            objekte = gruppen.streuen(54.1, 8.9, menge, menge, abstand, abstand, f"s{i}")
            assert len(objekte) == menge
            for k, a in enumerate(objekte):
                naechster = min(haversine(a["lat"], a["lon"], b["lat"], b["lon"]) * 1000.0
                                for j, b in enumerate(objekte) if j != k)
                assert abstand * 0.97 <= naechster <= abstand * 1.03, (menge, abstand, i)


def test_die_objekte_bleiben_auf_der_karte():
    for lat, lon in ((90.0, 10.0), (-90.0, 10.0), (10.0, 179.9999), (10.0, -179.9999)):
        for o in gruppen.streuen(lat, lon, 30, 30, 5, 6, "rand"):
            assert -90.0 <= o["lat"] <= 90.0 and -180.0 <= o["lon"] <= 180.0
