"""Kontrast der Textfarben in beiden Designs (Spec helles Design, Schritt 4)."""
import re
from pathlib import Path

import pytest

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _block(selektor):
    m = re.search(re.escape(selektor) + r"\s*\{(.*?)\}", INDEX, re.S)
    assert m, selektor
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", m.group(1)))


def _lum(h):
    h = h.strip().lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _kontrast(a, b):
    x, y = sorted([_lum(a), _lum(b)], reverse=True)
    return (x + 0.05) / (y + 0.05)


DUNKEL = _block(":root")
HELL_EIGEN = _block("html.hell")
HELL = {**DUNKEL, **HELL_EIGEN}

TEXT = ("--text-bright", "--text-label", "--green", "--cyan", "--red")
FLAECHEN = ("--bg-panel", "--bg-panel-2")


@pytest.mark.parametrize("text", TEXT)
@pytest.mark.parametrize("flaeche", FLAECHEN)
def test_hell_ist_lesbar(text, flaeche):
    assert _kontrast(HELL[text], HELL[flaeche]) >= 4.5, (text, flaeche)


@pytest.mark.parametrize("flaeche", FLAECHEN)
def test_friesenorange_reicht_fuer_hervorhebungen(flaeche):
    # FriesenOrange #D75F28 hat auf Weiss 3,6:1 -- unter 4,5:1 fuer Fliesstext, ueber 3:1
    # fuer Hervorhebungen. --amber ist nur Hervorhebung (Zeit, Rang 1, LIVE, Hinweise);
    # Nutzerentscheidung 01.10.2026: Markenfarbe vor erfundenem Dunkelorange.
    assert _kontrast(HELL["--amber"], HELL[flaeche]) >= 3.0


def test_hell_palette_ist_die_des_forums():
    assert HELL["--bg-body"].upper() == "#9FC7F8"
    assert HELL["--bg-panel"].upper() == "#FBFBFB"
    assert HELL["--bg-panel-2"].upper() == "#F1F8FF"
    assert HELL["--text-bright"].upper() == "#2B3C5A"
    assert HELL["--text-label"].upper() == "#536482"
    assert HELL["--green"].upper() == "#191D53"   # Friesen-Navy, Nutzerentscheidung 01.10.2026
    assert HELL["--cyan"].upper() == "#D31141"
    assert HELL["--red"].upper() == "#BC2A4D"
    assert HELL["--amber"].upper() == "#D75F28"   # FriesenOrange, s. Global Constraints
    assert HELL["--green-rgb"].replace(" ", "") == "25,29,83"


@pytest.mark.parametrize("text", ("--text-bright", "--green"))
def test_hell_text_direkt_auf_dem_grund(text):
    assert _kontrast(HELL[text], HELL["--bg-body"]) >= 4.5, text


# Die Karte schaltet nicht mit (Spec Punkt 2): Die Leaflet-Ebenen, auf denen gezeichnet
# wird, bekommen im Hellen die DUNKLEN Variablenwerte zurueck. Popups und Bedienelemente
# (popup-pane, control-container) liegen nicht darin und schalten mit.
_KARTENEBENEN = (".leaflet-tile-pane", ".leaflet-overlay-pane", ".leaflet-shadow-pane",
                 ".leaflet-marker-pane", ".leaflet-tooltip-pane", ".karten-legende-flz")


def _rueckstellblock():
    css = re.sub(r"/\*.*?\*/", "", INDEX, flags=re.S)
    m = re.search(r"(html\.hell \.leaflet-tile-pane,[^{]*)\{([^}]*)\}", css)
    assert m, "Rueckstellblock fehlt"
    return m.group(1), dict(re.findall(r"(--[\w-]+):\s*([^;]+);", m.group(2)))


def test_karte_schaltet_nicht_mit():
    kopf, werte = _rueckstellblock()
    for ebene in _KARTENEBENEN:
        assert "html.hell " + ebene in kopf, ebene
    # Jede Variable, die html.hell umstellt, kommt hier mit ihrem dunklen Wert zurueck.
    for name in HELL_EIGEN:
        assert werte.get(name, "").replace(" ", "") == DUNKEL[name].replace(" ", ""), name


def test_dunkle_werte_unveraendert():
    assert DUNKEL["--bg-body"] == "#04080f"
    assert DUNKEL["--green"] == "#2d9cdb"
    assert DUNKEL["--green-rgb"].replace(" ", "") == "45,156,219"
    assert DUNKEL["--schleier-rgb"].replace(" ", "") == "4,8,15"
    assert DUNKEL["--schatten-rgb"].replace(" ", "") == "0,0,0"


def test_kopfzeile_hat_im_hellen_eine_flaeche():
    assert re.search(r"html\.hell header,\s*html\.hell \.tab-nav \{[^}]*background: var\(--bg-panel\)", INDEX)


# Helle Schriftfarben, die nur auf dunklem Grund lesbar sind. Steht eine davon in einer
# Oberflaechen-Regel (nicht Karte), braucht dieselbe Regel eine html.hell-Fassung -- sonst
# steht im Hellen hellgelber oder hellblauer Text auf Weiss (Kutter-Feed, ICAO-Feld ...).
_HELLE_SCHRIFT = ("#cfe3f0", "#ffe6c2", "#b3ddff", "#e8a9a0", "#9fc9b6", "#ffd24a",
                  "#e0884a", "#e0a33e", "#19d3c5", "#8fb3cc", "#8aa0b8")
_KARTE_SEL = re.compile(r"aircraft-marker|traffic-|vrp|aip-marke|fse-platz|ground-marke|"
                        r"platzrunde|kompass|leaflet-tooltip|kachel")


def _regeln():
    css = INDEX[INDEX.index("\n  <style>\n"):INDEX.index("\n  </style>\n")]
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(" ".join(s.split()), r) for s, r in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def test_helle_schrift_hat_im_hellen_eine_gegenregel():
    regeln = _regeln()
    hell = " ".join(s for s, _ in regeln if s.startswith("html.hell"))
    offen = []
    for sel, rumpf in regeln:
        if sel.startswith(("html.hell", ":root")) or _KARTE_SEL.search(sel):
            continue
        for farbe in _HELLE_SCHRIFT:
            if re.search(r"(?<![-\w])color:\s*" + re.escape(farbe), rumpf, re.I):
                for glied in sel.split(","):
                    if "html.hell " + glied.strip() not in hell:
                        offen.append((glied.strip(), farbe))
    assert offen == [], offen


def test_leuchteffekte_sind_im_hellen_aus():
    # Leuchtschein und Scanlinie sind Effekte fuer dunklen Grund; auf Weiss wird aus dem
    # Leuchten ein dunkler Schmier und aus der Scanlinie eine wandernde graue Linie.
    assert re.search(r"html\.hell \.logo \{[^}]*text-shadow: none", INDEX)
    assert re.search(r"html\.hell \.scanline \{[^}]*display: none", INDEX)
