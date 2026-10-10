# -*- coding: utf-8 -*-
"""Die Mitglieder-Ansicht der Deichkontrolle (Eventtyp `strecke`, Spec 2026-10-10, Abschnitt 12).

Reine Funktionen werden in node ausgefuehrt (herausgeschnitten aus index.html), alles andere
an Bezeichnern im Code geprueft -- Funktionsnamen, ids, Eigenschaftsnamen, Endpunkt-Pfade --,
nie an Kommentaren oder freiem Text.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
INDEX = (WURZEL / "app" / "static" / "index.html").read_text(encoding="utf-8")
_NODE = shutil.which("node")


def _funktion(name: str) -> str:
    """Den Quelltext einer Funktion auf oberster Ebene -- bis zur ersten `}` in Spalte 0."""
    m = re.search(rf"^(async )?function {re.escape(name)}\(", INDEX, flags=re.M)
    assert m, f"function {name} fehlt"
    return INDEX[m.start():INDEX.index("\n}\n", m.start()) + 3]


def _ohne_kommentare(text: str) -> str:
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))


def _konstante(name: str) -> str:
    """Eine `const`-Deklaration auf oberster Ebene, bis zum Semikolon."""
    m = re.search(rf"^const {re.escape(name)} = ", INDEX, flags=re.M)
    assert m, f"const {name} fehlt"
    return INDEX[m.start():INDEX.index(";", m.start()) + 1]


def _node(quelltext: str, ausdruck: str):
    skript = quelltext + "\nconsole.log(JSON.stringify(" + ausdruck + "));"
    erg = subprocess.run([_NODE, "-e", skript], capture_output=True, text=True, timeout=20)
    assert erg.returncode == 0, erg.stderr
    return json.loads(erg.stdout.strip().splitlines()[-1])


_SKRIPT = _ohne_kommentare(INDEX[INDEX.rindex("<script>", 0, INDEX.index("const _STRECKE_NAME")):])


# --- Name und Zeichen ---------------------------------------------------------------------

def test_name_und_zeichen_stehen_an_einer_stelle():
    """Arbeitsname: Er muss sich in einem Handgriff aendern lassen. Ausserhalb der beiden
    Konstanten steht er im Skript nirgends als Zeichenkette, und im festen Text der Seite nur
    als Platzhalter, den `_streckeNamenEinsetzen` fuellt."""
    assert "'Deichkontrolle'" in _konstante("_STRECKE_NAME")
    assert "🌊" in _konstante("_STRECKE_ZEICHEN")
    ohne = _SKRIPT.replace(_konstante("_STRECKE_NAME"), "").replace(_konstante("_STRECKE_ZEICHEN"), "")
    assert "Deichkontrolle" not in ohne
    assert "🌊" not in ohne
    seite = re.sub(r"<script\b.*?</script>", "", INDEX, flags=re.S)
    seite = re.sub(r"<!--.*?-->", "", re.sub(r"<style\b.*?</style>", "", seite, flags=re.S), flags=re.S)
    assert "Deichkontrolle" not in seite and "🌊" not in seite
    assert "data-strecke-name" in seite
    assert "[data-strecke-name]" in _funktion("_streckeNamenEinsetzen")
    assert re.search(r"^_streckeNamenEinsetzen\(\);", INDEX, flags=re.M)


def test_die_ebene_der_live_karte_heisst_wie_der_eventtyp():
    assert "addOverlay(_streckeGruppe, _STRECKE_NAME)" in _funktion("_streckeKarteAbgleichen")


# --- Takt und Abfrage ---------------------------------------------------------------------

def test_beide_endpunkte_werden_abgefragt():
    assert "fetch('/api/strecke/events')" in _ohne_kommentare(_funktion("_streckeTakt"))
    assert "fetch('/api/strecke/events/' + id + '/stand')" in _ohne_kommentare(
        _funktion("_streckeStandHolen"))
    assert "fetch('/api/strecke/events')" in _ohne_kommentare(_funktion("fetchFriesenEvents"))


def test_der_takt_ist_in_imtakt_gehuellt_und_haelt_einen_aussetzer_aus():
    assert "setInterval(_imTakt(_streckeTakt), 30000)" in INDEX
    assert not re.search(r"setInterval\(_streckeTakt\s*,", INDEX)
    assert "_streckeTakt();" in _funktion("alleDatenNeuLaden")
    rumpf = _ohne_kommentare(_funktion("_streckeTakt"))
    fang = rumpf.index("catch")
    assert rumpf.index("return", fang) < rumpf.index("_streckeBannerZeigen()")


def test_die_zustaende_stehen_vor_dem_ersten_aufruf():
    """Ein `let`/`const` hinter dem ersten Aufruf auf oberster Ebene legt die ganze Seite lahm,
    und `node --check` merkt es nicht."""
    erster = INDEX.index("\n_streckeTakt();")
    for name in ("_streckeListe", "_streckeTaktNr", "_streckeOffenId", "_streckeGruppe",
                 "_streckeFarbwahlJetzt", "_streckeKarte"):
        m = re.search(rf"^let {name} = ", INDEX, flags=re.M)
        assert m and m.start() < erster, name
    for name in ("_STRECKE_NAME", "_STRECKE_ZEICHEN", "_STRECKE_FARBWAHL_KEY", "_STRECKE_PALETTE",
                 "_streckeStand", "_streckeStandNr", "_streckeZeichnung"):
        m = re.search(rf"^const {name} = ", INDEX, flags=re.M)
        assert m and m.start() < erster, name
    assert INDEX.index("\n_streckeNamenEinsetzen();") > INDEX.index("const _STRECKE_NAME")


def test_laeuft_sagt_der_server_nicht_die_uhr_des_geraets():
    """Im Kniebrett ist die Uhr des Geraets die des Sim-PCs."""
    for name in ("_streckeTakt", "_streckeBannerZeigen", "_streckeZuZeigen", "_streckeAnsichtZeigen",
                 "_streckeStandHolen", "_streckeKarteAbgleichen"):
        rumpf = _ohne_kommentare(_funktion(name))
        assert "Date.now" not in rumpf and "new Date" not in rumpf, name
    assert ".laeuft" in _funktion("_streckeZuZeigen")
    assert ".laeuft" in _funktion("_streckeBannerZeigen")


def test_eine_spaete_antwort_ueberschreibt_keine_juengere():
    assert "nr !== _streckeTaktNr" in _funktion("_streckeTakt")
    assert "_streckeStandNr.get(id) !== nr" in _funktion("_streckeStandHolen")


# --- Eventliste, Ansicht, Direktlink ------------------------------------------------------

def test_die_eventliste_fuehrt_den_typ_mit_kurzstand_und_oeffnet_seine_ansicht():
    holen = _ohne_kommentare(_funktion("fetchFriesenEvents"))
    assert "is_strecke: 1" in holen and "_streckeId: r.id" in holen
    assert "_streckeKurz: _streckeStandText(r)" in holen
    liste = _ohne_kommentare(_funktion("renderFriesenEvents"))
    assert "ev.is_strecke" in liste and "_STRECKE_NAME" in liste and "ev._streckeKurz" in liste
    assert "openStreckeDetail(ev._streckeId)" in liste
    assert "ev._streckeId != null" in _funktion("_eventKey")


def test_die_ansicht_hat_ihre_bausteine():
    block = INDEX[INDEX.index('<div id="strecke-results"'):INDEX.index('<div class="panel-title">Event-Analyse')]
    for stueck in ('id="strecke-title"', 'id="strecke-content"', 'id="strecke-umschalter"',
                   'id="strecke-karte"', 'id="strecke-piloten"',
                   'onclick="copyStreckeShareHeader(this)"'):
        assert stueck in block, stueck
    events = INDEX[INDEX.index('<div id="tab-events"'):]
    assert events.index('id="reddung-results"') < events.index('id="strecke-results"') < events.index('id="events-results"')
    live = INDEX[INDEX.index('<div id="tab-live"'):INDEX.index('<div id="tab-karte"')]
    assert 'id="strecke-banner"' in live
    zeigen = _ohne_kommentare(_funktion("_streckeAnsichtZeigen"))
    for stueck in ("_streckeBalken(r)", "_streckeStandText(r)", "_streckeRegelnHtml(r)",
                   "_streckePilotenHtml(r, wahl)"):
        assert stueck in zeigen, stueck


def test_die_pilotenliste_steht_im_scrollbaren_wrapper():
    rumpf = _funktion("_streckePilotenHtml")
    assert '<div class="table-scroll"><table>' in rumpf
    assert "pilotLinkHtml(" in rumpf and "strecke-punkt" in rumpf


def test_die_bruegge_pflicht_steht_in_der_ansicht_mit_dem_weg_zum_download():
    rumpf = _ohne_kommentare(_funktion("_streckeBrueggeHtml"))
    assert 'href="/download"' in rumpf
    # Im Kniebrett gibt es keine Links -- dort die Adresse als Text.
    assert "_PANEL_MODUS" in rumpf and "radar.friesenflieger.de/download" in rumpf
    assert "_streckeBrueggeHtml()" in _funktion("_streckeRegelnHtml")
    assert "r.ohne_grund" in _funktion("_streckeRegelnHtml")


def test_der_direktlink_oeffnet_die_ansicht_und_teilen_kopiert_ihn():
    assert "setUrlState({ tab: 'events', strecke: Number(id) })" in _funktion("openStreckeDetail")
    start = INDEX[INDEX.index("const reddungId = p.get('reddung');"):]
    start = start[:start.index("const icao = p.get('icao');")]
    assert "p.get('strecke')" in start and "await openStreckeDetail(Number(streckeId))" in start
    assert "#tab=events&strecke=${_streckeOffenId}" in _funktion("copyStreckeShareHeader")
    assert 'html.vr-panel [onclick*="copyStreckeShareHeader"]' in INDEX   # im Kniebrett kein Kopieren


def test_die_scrollregel_enthaelt_den_typ():
    rumpf = _ohne_kommentare(_funktion("renderEventsResults"))
    m = re.search(r"if \((.+?)\) \{?\s*results\.scrollIntoView", rumpf)
    assert m and "_streckeOffenId == null" in m.group(1)


def test_jede_andere_ansicht_schliesst_die_strecke_und_umgekehrt():
    for name in ("openBummel", "openReddungDetail", "_prefillEventForm"):
        assert "_streckeZu();" in _funktion(name), name
    kutter = INDEX[INDEX.index("let _kutterOpenId = null;"):INDEX.index("let _reddungListe = [];")]
    assert "_streckeZu();" in kutter
    oeffnen = _funktion("openStreckeDetail")
    assert "_reddungZu();" in oeffnen and "_kutterOpenId = null;" in oeffnen and "_activeBummel = null;" in oeffnen
    assert "_streckeOffenId = null;" in _funktion("_streckeZu")


# --- Umschalter und Merker ----------------------------------------------------------------

def test_der_umschalter_und_sein_merker_existieren():
    block = INDEX[INDEX.index('<div id="strecke-umschalter"'):INDEX.index('<div id="strecke-karte"')]
    assert "streckeFarbwahlSetzen('eine')" in block and "streckeFarbwahlSetzen('pilot')" in block
    assert "'friesenspy_strecke_farbe'" in _konstante("_STRECKE_FARBWAHL_KEY")
    assert "_prefSchreib(_STRECKE_FARBWAHL_KEY" in _funktion("streckeFarbwahlSetzen")
    assert "_prefLies(_STRECKE_FARBWAHL_KEY)" in _funktion("_streckeFarbwahl")


_WAHL = "let _streckeFarbwahlJetzt = null; const _STRECKE_FARBWAHL_KEY = 'k';"


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_im_kniebrett_gilt_die_vorgabe_und_nichts_wird_gemerkt():
    """Dort haelt kein Speicher: Auch ein (zufaellig vorhandener) Merker zaehlt nicht, und
    das Umschalten schreibt keinen."""
    js = (_WAHL + "let geschrieben = 0; const _PANEL_MODUS = true;"
          "function _prefLies() { return 'pilot'; } function _prefSchreib() { geschrieben++; }"
          "function _streckeAllesNeuZeichnen() {}"
          + _funktion("_streckeFarbwahl") + _funktion("streckeFarbwahlSetzen"))
    assert _node(js, "_streckeFarbwahl()") == "eine"
    assert _node(js, "(streckeFarbwahlSetzen('pilot'), [_streckeFarbwahl(), geschrieben])") == ["pilot", 0]


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_im_browser_wird_die_wahl_gemerkt_und_wieder_gelesen():
    js = (_WAHL + "let merker = null; const _PANEL_MODUS = false;"
          "function _prefLies(k) { return merker; } function _prefSchreib(k, w) { merker = w; }"
          "function _streckeAllesNeuZeichnen() {}"
          + _funktion("_streckeFarbwahl") + _funktion("streckeFarbwahlSetzen"))
    assert _node(js, "_streckeFarbwahl()") == "eine"                 # Vorgabe ohne Merker
    assert _node(js, "(streckeFarbwahlSetzen('pilot'), merker)") == "pilot"
    assert _node(js.replace("let merker = null", "let merker = 'pilot'"), "_streckeFarbwahl()") == "pilot"


# --- Rechnen fuer die Karte ---------------------------------------------------------------

_PALETTE = _konstante("_STRECKE_PALETTE") + "const _STRECKE_FARBE_AB = '#D75F28';"


def _abschnitte(sorten: list) -> str:
    """Eine gerade Strecke; je Eintrag ein Abschnitt: None = offen, sonst (cid, ts)."""
    teile = []
    for i, s in enumerate(sorten):
        cid, ts = (None, None) if s is None else s
        teile.append({"nr": i, "linie": [[54.0, 9.0 + i * 0.01], [54.0, 9.0 + (i + 1) * 0.01]],
                      "cid": cid, "ts": ts})
    return json.dumps(teile)


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_die_farbe_folgt_dem_ersten_treffer_und_bleibt():
    js = _PALETTE + _funktion("_streckeFarben")
    frueh = _abschnitte([(7, "2026-10-10T18:05:00Z"), (3, "2026-10-10T18:01:00Z"), None])
    f1 = _node(js, f"[..._streckeFarben({frueh})]")
    palette = _node(_PALETTE, "_STRECKE_PALETTE")
    assert f1 == [[3, palette[0]], [7, palette[1]]]
    # Ein dritter Pilot kommt dazu, und Pilot 7 holt einen FRUEHEREN Abschnitt der Strecke zu
    # einem SPAETEREN Zeitpunkt: Niemand wechselt die Farbe.
    spaeter = _abschnitte([(7, "2026-10-10T18:05:00Z"), (3, "2026-10-10T18:01:00Z"),
                           (9, "2026-10-10T18:20:00Z"), (7, "2026-10-10T18:30:00Z")])
    f2 = dict(map(tuple, _node(js, f"[..._streckeFarben({spaeter})]")))
    assert f2[3] == palette[0] and f2[7] == palette[1] and f2[9] == palette[2]
    assert len(set(palette)) == len(palette) >= 8


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_wenige_pfade_ein_zug_je_zusammenhaengendem_stueck():
    """2.000 Abschnitte duerfen nicht 2.000 Elemente werden: Offenes ist EINE Liste von Zuegen,
    Abgeflogenes eine je Farbe; benachbarte Abschnitte derselben Sorte verschmelzen."""
    js = _PALETTE + _funktion("_streckeFarben") + _funktion("_streckeLaeufe")
    s = _abschnitte([(1, "a"), (1, "b"), None, None, None, (2, "c"), (1, "d")])
    eine = _node(js, f"(() => {{ const l = _streckeLaeufe({s}, null); "
                     "return [l.offen.map(z => z.length), [...l.farbig].map(e => [e[0], e[1].map(z => z.length)])]; })()")
    assert eine == [[4], [["#D75F28", [3, 3]]]]
    pilot = _node(js, f"(() => {{ const s = {s}; const l = _streckeLaeufe(s, _streckeFarben(s)); "
                      "return [l.offen.length, [...l.farbig.values()].map(z => z.map(q => q.length))]; })()")
    assert pilot == [1, [[3, 2], [2]]]
    viele = ("Array.from({length: 2000}, (_, i) => ({nr: i, linie: [[54, 9 + i * 0.001], "
             "[54, 9 + (i + 1) * 0.001]], cid: i % 2 ? null : 1 + i % 5, ts: 't'}))")
    anzahl = _node(js, f"(() => {{ const s = {viele}; const l = _streckeLaeufe(s, _streckeFarben(s)); "
                       "return 1 + l.farbig.size; })()")
    assert anzahl <= 9


def test_gezeichnet_wird_als_svg_in_gebuendelten_pfaden():
    rumpf = _ohne_kommentare(_funktion("_streckeZeichnen"))
    assert "L.canvas" not in rumpf and "renderer:" not in rumpf
    assert rumpf.count("L.polyline(") == 4          # Band, Offenes, Tipp-Faenger, je Farbe einer
    assert "_streckeLaeufe(" in rumpf and "dashArray" in rumpf
    assert "karte.on('zoomend'" in rumpf            # die echte Breite haengt am Massstab
    assert "_streckeBandBreite(" in _funktion("_streckeBandAnpassen")
    for karte in ("_streckeKarteAbgleichen", "_streckeEventKarte"):
        assert "_streckeZeichnen(" in _funktion(karte) or "_streckeStandHolen(" in _funktion(karte)
    assert "_streckeZeichnen('live:' + id, _streckeGruppe, liveMap, d)" in _funktion("_streckeStandHolen")
    assert "_streckeZeichnen('event', _streckeKarte, _streckeKarte, d)" in _funktion("_streckeEventKarte")


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_das_band_hat_die_echte_breite():
    """500 m nach jeder Seite sind 1.000 m: Am Aequator bei Zoom 10 (152,87 m je Pixel) 6,54 px,
    je Zoomstufe das Doppelte, und auf 60° Breite wieder das Doppelte."""
    js = _funktion("_streckeBandBreite")
    assert _node(js, "_streckeBandBreite(500, 0, 10)") == pytest.approx(6.541, abs=0.01)
    assert _node(js, "_streckeBandBreite(500, 0, 11)") == pytest.approx(13.082, abs=0.02)
    assert _node(js, "_streckeBandBreite(500, 60, 10)") == pytest.approx(13.082, abs=0.02)
    assert _node(js, "_streckeBandBreite(500, 54, 3)") == 2      # nie duenner als sichtbar


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_der_tipp_findet_den_naechsten_abschnitt_und_nennt_pilot_und_uhrzeit():
    s = _abschnitte([(1, "2026-10-10T18:42:10Z"), None, None])
    js = ("function escHtml(t) { return String(t); }"
          + _funktion("_streckeNaechster") + _funktion("_streckeTippHtml"))
    assert _node(js, f"_streckeNaechster({s}, 54.004, 9.004).nr") == 0
    assert _node(js, f"_streckeNaechster({s}, 53.99, 9.027).nr") == 2
    d = '{"strecke": S, "je_pilot": [{"cid": 1, "name": "Anton"}], "vorbei_seit_s": null}'.replace("S", s)
    text = _node(js, f"(() => {{ const d = {d}; return [_streckeTippHtml(d, d.strecke[0]), _streckeTippHtml(d, d.strecke[1])]; }})()")
    assert "Abschnitt 1 von 3" in text[0] and "Anton" in text[0] and "18:42 UTC" in text[0]
    assert "Abschnitt 2 von 3" in text[1] and "Anton" not in text[1]
    assert "_streckeNaechster(" in _funktion("_streckeZeichnen")
    assert "_streckeTippHtml(" in _funktion("_streckeZeichnen")


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_zahlen_stehen_im_deutschen_format_und_die_vorgabe_kommt_aus_den_regeln():
    js = "".join(_funktion(n) for n in ("_streckeZahl", "_streckeKm", "_streckeStandText",
                                         "_streckeVorgabeText"))
    assert _node(js, "[_streckeZahl(1000, 0), _streckeZahl(1234567.25, 1), _streckeZahl(50.6, 1)]") == [
        "1.000", "1.234.567,3", "50,6"]
    regeln = '{"korridor_m": 750.0, "hoehe_max_ft": 1500.0, "gs_max_kt": 160.0, "gs_min_kt": 40.0}'
    satz = _node(js, f"_streckeVorgabeText({regeln})")
    assert satz == "höchstens 750 m neben der Strecke und höchstens 1.500 ft darüber, 40 bis 160 kt"
    stand = '{"anteil": 0.548, "km_abgedeckt": 50.6, "km_gesamt": 92.3}'
    assert _node(js, f"_streckeStandText({stand})") == "50,6 von 92,3 km · 55 %"
    lang = '{"anteil": 0.1, "km_abgedeckt": 123.4, "km_gesamt": 1234.0}'
    assert _node(js, f"_streckeStandText({lang})") == "123 von 1.234 km · 10 %"
