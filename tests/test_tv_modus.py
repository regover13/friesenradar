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
    # Nutzer 03.10.2026: nur ein oranger Schein -- kein harter Rahmen, kein weisser Saum.
    regel = re.search(r"html\.tv \*:focus \{([^}]*)\}", INDEX).group(1)
    assert "outline: none" in regel and "rgba(215,95,40" in regel
    assert "255,255,255" not in regel and "inset" not in regel


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
    # nachfassen, bis es stabil stimmt -- der gemerkte Reiter schaltet spaeter noch einmal um
    assert "stimmt < 4" in start and "getippt" in start


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
    {"callsign": "FRS7", "latitude": 54.0, "longitude": 9.0, "groundspeed": 0},      # steht
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
    # Wer rollt, zaehlt schon mit (Nutzer 03.10.2026: "sobald Bewegung")
    rollt = FLIEGER + [{"callsign": "FRS8", "latitude": 53.0, "longitude": 8.0, "groundspeed": 9}]
    assert _rundgang(rollt, "FRS49")["callsign"] == "FRS8"
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


def test_ebenen_liste_laesst_sich_mit_links_schliessen_und_haelt_die_pfeile():
    assert "leaflet-control-layers-expanded" in _funktion("_tvBereich")
    b = _funktion("_tvBewegen")
    assert "richtung === 'links' || richtung === 'rechts'" in b and "_tvZurueck()" in b
    assert "Links = schließen" in _funktion("_tvHinweis")


def test_ok_schaltet_ankreuzfelder():
    """Im Browser gemessen: Enter schaltet ein Ankreuzfeld nicht (nur die Leertaste)."""
    assert "/^(checkbox|radio)$/.test(ziel.type)" in _funktion("_tvTaste")


def test_fernsicht_und_historie_sind_schaltbar():
    b = _block()
    assert "zurueck=0" in b and "if (_tvHistorieAus ||" in b
    d = _funktion("_tvDiag")
    assert "if (!_tvDiagAn ||" in d and "/api/tv-diag" in d


def test_unsichtbare_vollbild_karte_ist_kein_bereich():
    """Fund am Fire TV 03.10.2026: Auf dem Live-Tab bewirkte keine Taste etwas -- die
    Vollbild-Klasse hing noch an der (nicht sichtbaren) Karte, der Bereich war leer."""
    b = _funktion("_tvBereich")
    assert "vollbild.getBoundingClientRect().width > 0" in b
    assert "_tvBereich().classList.contains('map-is-fullscreen')" in _funktion("_tvHinweis")


def test_haengendes_vollbild_wird_beim_naechsten_tastendruck_verlassen():
    taste = _funktion("_tvTaste")
    assert taste.index("_tvVollbildAufraeumen()") < taste.index("var t = e.key")
    assert "getBoundingClientRect().width > 0" in _funktion("_tvVollbildAufraeumen")


def test_keine_fallen_fremde_links_und_leeres_suchfeld():
    """Im Browser nachgestellt 03.10.2026: OK auf dem Leaflet-Link verliess die Seite; im
    leeren Suchfeld hingen Links/Rechts fest."""
    assert "el.host !== location.host" in _funktion("_tvKandidaten")
    assert "imTextfeld && ziel.value &&" in _funktion("_tvTaste")


def test_folgen_schaltet_den_echten_folgemodus_ein():
    """Nutzer 03.10.2026: Die Karte wurde nur ausgerichtet, der Folgemodus war nicht aktiv."""
    a = _funktion("_tvAusschnittAnwenden")
    assert "_movingMap = true; _naviTakt(true)" in a
    assert "_naviMerke" not in a, "nicht als Merker speichern -- der gilt auch fuer PC und Handy"


def test_rundgang_tempo():
    b = _block()
    assert "_TV_RUNDGANG_TAKT_MS = 30000" in b and "_TV_RUNDGANG_ZOOM = 12" in b and "_TV_RUNDGANG_SCHWENK_S = 10" in b


def test_schaltflaechen_gehen_in_die_ruhe_und_kommen_mit_einer_taste_zurueck():
    """Nutzer 03.10.2026: Schaltflaechen nach einer Zeit ausblenden, erst mit Tastendruck wieder."""
    b = _block()
    assert "_TV_RUHE_NACH_MS = 10000" in b
    taste = _funktion("_tvTaste")
    assert "_tvRuheBeenden()" in taste and taste.index("_tvRuheBeenden()") < taste.index("var t = e.key")
    assert re.search(r"html\.tv\.tv-ruhe \.map-is-fullscreen \.leaflet-control:not\(\.leaflet-control-attribution\)", INDEX)
    assert "tv-hinweis-bleibt" in _funktion("_tvHinweis")


def test_start_ohne_kartensteuerung():
    """Nutzer 03.10.2026: im Standard nicht die Kartensteuerung aktivieren."""
    start = _funktion("_tvStart")
    assert "_tvFokus(rk)" in start and "_tvFokus(karte.getContainer())" not in start


def test_rundgang_kommt_auf_der_aktuellen_position_an():
    """Nutzer 03.10.2026: Bei 10 s Schwenk fliegt das Flugzeug weiter -- die Karte muss dort
    ankommen, wo es dann ist, und es waehrend der Verweilzeit mitfuehren."""
    n = _funktion("_tvRundgangNachfuehren")
    assert "_tvRundgangSchwenkBis" in n and "panTo" in n and "_tvRundgangOrt(_tvRundgangLetzter)" in n
    assert "mapMarkers[callsign]" in _funktion("_tvRundgangOrt")
    assert "setInterval(_tvRundgangNachfuehren" in _funktion("_tvStart")


def test_nachfuehren_im_sekundentakt_ohne_gleiten():
    n = _funktion("_tvRundgangNachfuehren")
    assert "panTo(ort, { animate: false })" in n
    # nur schieben, wenn sich die Position wirklich geaendert hat
    assert "latLngToContainerPoint" in n and "< 3" in n
    assert "setInterval(_tvRundgangNachfuehren, 1000)" in _funktion("_tvStart")


def test_tv_modus_ohne_dauerlaufende_zierde():
    """Fund am Fire TV 03.10.2026: Die Scanline lief sichtbar ueber die Karte, das Bild ruckelte."""
    assert "html.tv .scanline { display: none !important; }" in INDEX
    assert "html.tv *, html.tv *::before, html.tv *::after { animation: none !important; }" in INDEX
    assert "html.tv body::before { display: none !important; }" in INDEX


def test_schwenk_hat_eine_kachel_unterlage():
    """Fund 03.10.2026 (gemessen mit der Kennung des Sticks): Beim Heraus- und Hereinzoomen des
    Schwenks stand sekundenlang nichts da -- die Kacheln sind nicht zwischenspeicherbar, und
    Leaflet laedt dort erst nach der Bewegung. Deshalb haelt der Rundgang Weg und Ziel in
    eigenen Kachel-Ebenen UNTER der Grundkarte vor."""
    assert "_tvKachelnVorladen" not in INDEX, "vorab geholte Bilder nuetzen nichts -- der Server schickt keine Cache-Angaben"
    u = _funktion("_tvUnterlage")
    assert "minNativeZoom: stufe, maxNativeZoom: stufe" in u and "e._update = function () {}" in u
    assert "feld.style.zIndex = 150" in u, "unter der Grundkarte (tilePane = 200)"
    v = _funktion("_tvUnterlageVorhalten")
    assert "_TV_RUNDGANG_ZOOM" in v and "_removeTile" in v
    schritt = _funktion("_tvRundgangSchritt")
    assert schritt.index("_tvUnterlageVorhalten(") < schritt.index("karte.flyTo(")
    assert "_tvUnterlageZeigen(karte, false)" in schritt, "die Flugkarte ist durchsichtig -- nach dem Schwenk muss die Unterlage weg"
    assert "keepBuffer = 4" in _funktion("_tvStart")
    assert "liveMap._fsGrundkarten = liveLayers" in INDEX


def test_logo_steht_oben_mittig_solange_die_schaltflaechen_ausgeblendet_sind():
    """Nutzer 03.10.2026: Sind die Schaltflaechen ausgeblendet, steht das FriesenRadar-Logo
    zentriert am oberen Rand -- in der Fassung der eingestellten Darstellung (hell/dunkel)."""
    start = _funktion("_tvStart")
    assert "logo.id = 'tv-logo'" in start
    regel = re.search(r"html\.tv \.tv-logo \{([^}]*)\}", INDEX).group(1)
    assert "left: 50%" in regel and "top:" in regel and "opacity: 0" in regel
    assert "pointer-events: none" in regel
    assert "friesenradar-weissrot.svg" in regel
    # Nutzer: "logo ohne hintergrund!!" -- keine Platte dahinter.
    assert "var(--" not in regel and "background-color" not in regel
    assert re.search(r"html\.hell\.tv \.tv-logo \{[^}]*friesenradar-farbig\.svg", INDEX)
    assert re.search(r"html\.tv\.tv-ruhe \.tv-logo \{[^}]*opacity: 1", INDEX)
    # Ausserhalb des TV-Modus gibt es das Element nicht zu sehen.
    assert re.search(r"\n    \.tv-hinweis, \.tv-logo \{ display: none; \}", INDEX)


def test_tv_modus_hat_einen_schalter_in_den_einstellungen():
    """Nutzer 03.10.2026: In den Einstellungen gibt es TV-Modus An/Aus -- damit schaltet man ihn
    an oder aus; der Parameter ?tv=1 geht weiter. Im Kniebrett und auf dem Handy ausgeblendet.
    Ein eigener Knopf auf der Karte ist dafuer NICHT vorgesehen."""
    assert INDEX.index('id="einst-design"') < INDEX.index('id="einst-tv"') < INDEX.index('id="panel-anzeige"')
    assert 'id="tv-an">An<' in INDEX and 'id="tv-aus">Aus<' in INDEX
    assert re.search(r"html\.vr-panel #einst-tv \{ display: none", INDEX)
    assert re.search(r"@media \(max-width: 600px\) \{\s*#einst-tv \{ display: none", INDEX)
    f = _funktion("_tvModusSetzen")
    assert "location.pathname + '?tv=1'" in f and ": location.pathname" in f and "rundgang" not in f
    e = _funktion("_tvSchalterEinrichten")
    assert "_tvModusSetzen(true)" in e and "_tvModusSetzen(false)" in e
    assert "tv-beenden" not in INDEX


def test_schalter_merkt_sich_das_geraet_nicht_das_konto():
    """Nutzer 03.10.2026: "An" bleibt auf DIESEM Geraet an (Browser-Speicher) -- nicht am Konto,
    sonst startete auch der PC im TV-Modus. Im Kniebrett und auf schmalen Bildschirmen wird der
    Merker nie ausgewertet; ?tv=1 schaltet unabhaengig davon ein."""
    kopf = INDEX[:INDEX.index("// HELLES DESIGN")]
    assert "localStorage.getItem('friesenradar_tv') === '1'" in kopf
    assert re.search(r"if \(!isPanel && \(qs\.get\('tv'\) === '1' \|\| \(tvMerker && !schmal\)\)\)", kopf)
    assert "(max-width: 600px)" in kopf
    f = _funktion("_tvModusSetzen")
    assert "localStorage.setItem('friesenradar_tv', '1')" in f
    assert "localStorage.removeItem('friesenradar_tv')" in f
    assert "_prefSchreib" not in f, "nicht ans Konto haengen"


def test_fuer_den_nutzer_heisst_es_rundflug():
    """Nutzer 03.10.2026: "benenne Rundgang in Rundflug um". Im Code bleiben die Bezeichner,
    der alte Adress-Parameter gilt weiter."""
    b = _block()
    assert "'Rundgang" not in b and "Rundgang'" not in b, "kein sichtbarer Text mehr mit dem alten Wort"
    assert "'▶ Rundflug'" in b and "'Rundflug ' + w.nr" in b
    assert "qs.get('rundflug') === '1' || qs.get('rundgang') === '1'" in _funktion("_tvStart")
