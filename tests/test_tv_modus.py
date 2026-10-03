"""TV-Modus (?tv=1): FriesenRadar mit der Fernbedienung bedienen (Fire TV, Fully Kiosk).

Pfeiltasten springen raeumlich zwischen den Bedienelementen, OK loest aus, Zurueck schliesst.
Liegt der Fokus auf der Karte, verschieben die Pfeile die Karte (Leaflet macht das selbst).
Ausserhalb von html.tv darf sich nichts aendern -- Website, Handy und Kniebrett bleiben."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _block():
    start = INDEX.index("//  TV-MODUS (?tv=1)")
    return INDEX[start:INDEX.index("//  ENDE TV-MODUS", start)]


def _funktion(name):
    b = _block()
    start = b.index("function " + name + "(")
    return b[start:b.index("\n}\n", start) + 3]


def _wahl(von, kandidaten, richtung):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js nicht verfuegbar")
    js = _funktion("_tvNaechstes") + "process.stdout.write(String(_tvNaechstes(%s, %s, %s)));" % (
        json.dumps(von), json.dumps(kandidaten), json.dumps(richtung))
    return int(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout)


def R(x, y, w=100, h=40):
    return {"x": x, "y": y, "w": w, "h": h}


def test_kopfskript_setzt_die_klasse_nur_mit_tv_1():
    kopf = INDEX[:INDEX.index("</script>")]
    assert "qs.get('tv') === '1'" in kopf and "classList.add('tv')" in kopf


def test_rechts_nimmt_das_naechste_in_der_zeile_nicht_das_schraeg_darunter():
    # vier Reiter nebeneinander, darunter ein Knopf
    k = [R(110, 0), R(220, 0), R(120, 200)]
    assert _wahl(R(0, 0), k, "rechts") == 0


def test_runter_bevorzugt_was_darunter_liegt_auch_wenn_etwas_seitlich_naeher_ist():
    k = [R(110, 0), R(0, 300)]
    assert _wahl(R(0, 0), k, "unten") == 1


def test_nichts_in_der_richtung_gibt_minus_eins():
    assert _wahl(R(0, 0), [R(110, 0)], "links") == -1
    assert _wahl(R(0, 0), [], "unten") == -1


def test_listenzeilen_untereinander_in_derselben_spalte():
    # Kartensymbole am rechten Rand dreier Zeilen: runter bleibt in der Spalte
    k = [R(900, 60, 30, 30), R(900, 120, 30, 30), R(100, 60, 200, 30)]
    assert _wahl(R(900, 0, 30, 30), k, "unten") == 0


def test_alles_haengt_an_der_klasse_tv():
    b = _block()
    assert "function _tvAn()" in b
    for name in ["_tvTaste", "_tvZurueck"]:
        rumpf = _funktion(name)
        assert "if (!_tvAn()) return" in rumpf, name
    # Fokusrahmen und Hinweis nur im TV-Modus
    for m in re.finditer(r"\n\s*([^\n{}]*:focus[^\n{]*)\{", INDEX):
        if "tv" in m.group(1):
            assert m.group(1).strip().startswith("html.tv"), m.group(1)
    assert re.search(r"html\.tv [^{]*:focus[^{]*\{[^}]*outline:\s*4px solid", INDEX)


def test_klickbares_ohne_knopf_wird_fokussierbar():
    b = _block()
    for sel in [".td-map-btn", ".td-callsign-link", ".pilot-link", "[onclick]"]:
        assert sel in b, sel
    assert "setAttribute('tabindex', '0')" in b


def test_auf_der_karte_gehoeren_die_pfeile_der_karte():
    rumpf = _funktion("_tvTaste")
    assert "leaflet-container" in rumpf
    # +/- und die Spultasten der Fernbedienung zoomen
    assert "MediaFastForward" in rumpf and "MediaRewind" in rumpf


def test_zurueck_schliesst_ebenen_und_fenster():
    rumpf = _funktion("_tvZurueck")
    assert "leaflet-control-layers-expanded" in rumpf
    assert "Escape" in rumpf
    # Fully Kiosk meldet "Zurueck" nicht als Taste, sondern geht in der Historie zurueck
    assert "popstate" in _block() and "pushState" in _block()


def test_seite_rollt_mit_und_start_im_kartenvollbild():
    b = _block()
    assert "scrollIntoView" in b
    start = _funktion("_tvStart")
    assert 'data-tab="karte"' in start and "map-fullscreen-btn" in start


def test_kein_neuer_sprachumfang_fuer_das_kniebrett():
    """Dieselbe Datei laedt Coherent GT (Chrome 49) -- der Block muss dort wenigstens parsen."""
    b = re.sub(r"//[^\n]*", "", _block())
    assert "?." not in b and "??" not in b and "=>" not in b
    assert ".forEach(" not in b.replace("Array.prototype.forEach.call(", "")


def _ausschnitt(piloten, cid):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js nicht verfuegbar")
    js = _funktion("_tvAusschnittWahl") + "process.stdout.write(JSON.stringify(_tvAusschnittWahl(%s, %s)));" % (
        json.dumps(piloten), json.dumps(cid))
    return json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout)


def test_ausschnitt_folgt_dem_eigenen_flugzeug():
    """Nutzer 03.10.2026: wenn online, das eigene Flugzeug im Folgemodus."""
    p = [{"cid": 1, "latitude": 53.5, "longitude": 8.1}, {"cid": 7, "latitude": 28.3, "longitude": -81.4}]
    assert _ausschnitt(p, 7) == {"art": "folgen", "lat": 28.3, "lon": -81.4}


def test_ausschnitt_zeigt_sonst_die_friesen_ueber_deutschland():
    p = [{"cid": 1, "latitude": 53.5, "longitude": 8.1}, {"cid": 2, "latitude": 48.3, "longitude": 11.8},
         {"cid": 3, "latitude": 28.3, "longitude": -81.4}]       # Florida zaehlt nicht mit
    w = _ausschnitt(p, 99)
    assert w["art"] == "gruppe" and w["grenzen"] == [[48.3, 8.1], [53.5, 11.8]]


def test_ausschnitt_ohne_friesen_ueber_deutschland_ist_deutschland():
    for p in ([], [{"cid": 3, "latitude": 28.3, "longitude": -81.4}], [{"cid": 4, "latitude": 0, "longitude": 0}]):
        w = _ausschnitt(p, None)
        assert w["art"] == "deutschland" and w["grenzen"][0][0] < 48 and w["grenzen"][1][0] > 54


def test_handgriff_haelt_den_ausschnitt_und_fester_ausschnitt_schaltet_das_nachfuehren_ab():
    assert "_tvHandZuletzt = Date.now()" in _funktion("_tvTaste")
    assert "_TV_HAND_PAUSE_MS" in _funktion("_tvAusschnittAnwenden")
    start = _funktion("_tvStart")
    assert start.index("mitte.length === 2") < start.index("setInterval(_tvAusschnittAnwenden")


def test_karte_ist_kein_sprungziel_zurueck_fuehrt_auf_sie():
    """Im Browser gemessen: Als Sprungziel fing die Karte jeden Pfeil ab -- man kam von den
    Knoepfen nie weiter. Jetzt: OK verlaesst die Karte, Zurueck fuehrt auf sie."""
    assert "leaflet-container')) continue" in _funktion("_tvKandidaten")
    z = _funktion("_tvZurueck")
    assert "_tvFokus(karteEl)" in z


def _rundgang(piloten, letzter):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js nicht verfuegbar")
    js = _funktion("_tvRundgangWahl") + "process.stdout.write(JSON.stringify(_tvRundgangWahl(%s, %s)));" % (
        json.dumps(piloten), json.dumps(letzter))
    return json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout)


FLIEGER = [
    {"callsign": "FRS49", "latitude": 53.5, "longitude": 8.1, "groundspeed": 110},
    {"callsign": "FRS123", "latitude": 28.3, "longitude": -81.4, "groundspeed": 170},
    {"callsign": "FRS7", "latitude": 54.0, "longitude": 9.0, "groundspeed": 0},      # steht am Boden
    {"callsign": "FRS217", "latitude": 53.7, "longitude": 7.4, "groundspeed": 95},
]


def test_rundgang_schaltet_der_reihe_nach_durch_und_beginnt_von_vorn():
    """Nutzer 03.10.2026: die fliegenden Friesen im Vollbild nach und nach durchschalten."""
    folge, letzter = [], None
    for _ in range(4):
        w = _rundgang(FLIEGER, letzter)
        letzter = w["callsign"]
        folge.append(letzter)
    assert folge == ["FRS123", "FRS217", "FRS49", "FRS123"]
    assert _rundgang(FLIEGER, None)["von"] == 3 and _rundgang(FLIEGER, "FRS123")["nr"] == 2


def test_rundgang_nimmt_stehende_nur_wenn_niemand_fliegt():
    am_boden = [{"callsign": "FRS7", "latitude": 54.0, "longitude": 9.0, "groundspeed": 0}]
    assert _rundgang(am_boden, None)["callsign"] == "FRS7"
    assert _rundgang([], None) is None
    assert _rundgang([{"callsign": "X", "latitude": 0, "longitude": 0, "groundspeed": 100}], None) is None


def test_rundgang_ist_schaltbar_und_haelt_bei_handgriff_an():
    b = _block()
    assert "MediaPlayPause" in _funktion("_tvTaste")
    assert "rundgang" in _funktion("_tvStart")
    schritt = _funktion("_tvRundgangSchritt")
    assert "_TV_HAND_PAUSE_MS" in schritt and "flyTo" in schritt
    # Laeuft der Rundgang, fuehrt der Ausschnitt nicht dazwischen
    assert "_tvRundgangAn" in _funktion("_tvAusschnittAnwenden")
    assert 'id = \'tv-rundgang\'' in b or 'id="tv-rundgang"' in b


def test_zurueck_beendet_die_app_nicht():
    """Nutzerfund 03.10.2026 auf dem Fire TV: Zurueck beendete die App. Ein beim Laden angelegter
    Historien-Eintrag wird vom Browser uebersprungen; die Eintraege muessen bei Tastendruck
    entstehen, einer je Druck."""
    taste = _funktion("_tvTaste")
    assert taste.index("_tvHistorieAuflegen()") < taste.index("var t = e.key")
    auflegen = _funktion("_tvHistorieAuflegen")
    assert "pushState" in auflegen and "_TV_HISTORIE_MAX" in auflegen
    start = _funktion("_tvStart")
    assert "pushState" not in start and "_tvHistorieTiefe--" in start
