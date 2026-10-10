"""Die Verwaltung der Deichkontrolle (Eventtyp ``strecke``) — geprüft am Quelltext.

``admin.html`` hat im Test keine JS-Laufzeit. Geprüft wird deshalb an den Namen, die der Code
wirklich benutzt (``data-typ``, ids, Funktionsnamen, Endpunkt-Pfade), nicht an Bedientexten
oder Kommentaren: Kommentare werden vor der Suche entfernt.
"""
from __future__ import annotations

import re
from pathlib import Path

from app import strecke as st

ADMIN_PFAD = Path(__file__).resolve().parent.parent / "app" / "static" / "admin.html"
ADMIN = ADMIN_PFAD.read_text(encoding="utf-8")
_ROH = "\n".join(re.findall(r"<script>(.*?)</script>", ADMIN, re.S))
#: Das Skript ohne Kommentare — sonst fände eine Suche die Erklärung statt des Codes.
#: Zeilenkommentare nur am Zeilenanfang (nach Einrückung): `//` steht auch in Adressen.
SKRIPT = re.sub(r"(?m)^\s*//.*$", "", re.sub(r"/\*.*?\*/", "", _ROH, flags=re.S))
HTML = re.sub(r"<!--.*?-->", "", ADMIN, flags=re.S)

BASIS = "'/api/admin/strecke/events'"


def _rumpf(name: str) -> str:
    """Der Körper einer Funktion ``name`` — bis zur schließenden Klammer auf ihrer Ebene."""
    anfang = SKRIPT.index(f"function {name}(")
    auf = SKRIPT.index("{", SKRIPT.index(")", anfang))
    tiefe = 0
    for i in range(auf, len(SKRIPT)):
        if SKRIPT[i] == "{":
            tiefe += 1
        elif SKRIPT[i] == "}":
            tiefe -= 1
            if tiefe == 0:
                return SKRIPT[auf: i + 1]
    raise AssertionError(f"Funktion {name} ist nicht geschlossen")


# ------------------------------------------------------------- Knopf, Panel, Lader

def test_typ_knopf_und_panel_sind_da():
    assert len(re.findall(r'class="typ-btn[^"]*" data-typ="strecke"', HTML)) == 1
    assert HTML.count('id="typ-strecke"') == 1
    assert re.search(r'<div class="typ-panel" id="typ-strecke">', HTML)


def test_der_typ_hat_einen_lader():
    assert re.search(r"strecke:\s*function\s*\(\)\s*\{\s*loadStrecke\(\);", _rumpf("_typLader"))


def test_das_formular_hat_alle_felder():
    for feld in ("sk-name", "sk-dtstart", "sk-dtend", "sk-korridor", "sk-hoehe",
                 "sk-gsmax", "sk-gsmin", "sk-karte", "sk-vorschau", "sk-warnung",
                 "sk-zurueck-btn", "sk-leeren-btn", "sk-save-btn", "sk-liste"):
        assert HTML.count(f'id="{feld}"') == 1, feld
    # Start belegt das Ende vor — dasselbe Muster wie bei Bummel, Kutter und Reddung.
    assert re.search(r'id="sk-dtstart"[^>]*data-end="sk-dtend"', HTML)


def test_die_vorgaben_im_formular_sind_die_des_servers():
    for feld, wert in (("sk-korridor", st.VORGABE_KORRIDOR_M), ("sk-hoehe", st.VORGABE_HOEHE_FT),
                       ("sk-gsmax", st.VORGABE_GS_MAX_KT), ("sk-gsmin", st.VORGABE_GS_MIN_KT)):
        m = re.search(rf'<input[^>]*id="{feld}"[^>]*value="(\d+)"', HTML)
        assert m and float(m.group(1)) == wert, feld
        assert re.search(rf"'{feld}':\s*{int(wert)}\b", SKRIPT), f"{feld} fehlt in _SK_VORGABEN"


# ------------------------------------------------------------------- Endpunkte

def test_die_liste_wird_geholt():
    assert f"api('GET', {BASIS})" in _rumpf("loadStrecke")


def test_anlegen_und_aendern_gehen_an_ihre_endpunkte():
    rumpf = _rumpf("skSpeichern")
    assert f"{BASIS[:-1]}/' + _skEditingId" in rumpf        # POST …/{id}
    assert re.search(r":\s*" + re.escape(BASIS) + r"\s*;", rumpf)   # POST … (neu)
    assert "api('POST', pfad, koerper)" in rumpf
    for feld in ("name", "dtstart", "dtend", "punkte", "korridor_m", "hoehe_max_ft",
                 "gs_max_kt", "gs_min_kt"):
        assert re.search(rf"\b{feld}:", rumpf), f"{feld} wird nicht geschickt"
    assert "localToIso(dtstart)" in rumpf


def test_gelaendehoehen_holen_ruft_seinen_endpunkt():
    assert f"api('POST', {BASIS[:-1]}/' + id + '/grund')" in _rumpf("skGrundHolen")
    # Der Knopf erscheint nur, wenn die Höhen fehlen — an `grund_da` gebunden.
    rumpf = _rumpf("loadStrecke")
    assert "ev.grund_da" in rumpf and "skGrundHolen(" in rumpf


def test_loeschen_geht_ueber_die_passwort_bestaetigung():
    rumpf = _rumpf("skLoeschen")
    bestaetigt = rumpf.index("confirmCritical(")
    geloescht = rumpf.index(f"api('DELETE', {BASIS[:-1]}/' + id)")
    assert bestaetigt < geloescht, "erst bestätigen, dann löschen"
    assert "if (!ok) return;" in rumpf[bestaetigt:geloescht]
    assert "confirm(" not in rumpf.replace("confirmCritical(", "")


def test_fehlermeldungen_des_servers_werden_gezeigt():
    assert ".detail" in _rumpf("_skFehler") and "toast(" in _rumpf("_skFehler")
    for name in ("skSpeichern", "skGrundHolen", "skLoeschen"):
        assert "_skFehler(res" in _rumpf(name), name


# ---------------------------------------------------------------- Die Vorschau

def test_die_vorschau_teilt_wie_der_server():
    """Sollänge 2 × Korridor, aufgerundet, mindestens 1 — wie ``abschnitt_anzahl``."""
    rumpf = _rumpf("_skTeilung")
    assert re.search(r"2\s*\*\s*korridorM\s*/\s*1000", rumpf)
    assert re.search(r"Math\.max\(\s*1\s*,\s*Math\.ceil\(", rumpf)
    assert "_skLaengeKm(punkte)" in rumpf


def test_die_grenzen_der_vorschau_sind_die_des_servers():
    for name, wert in (("_SK_ABSCHNITTE_MAX", st.ABSCHNITTE_MAX), ("_SK_PUNKTE_MAX", st.PUNKTE_MAX),
                       ("_SK_KORRIDOR_MIN_M", st.KORRIDOR_MIN_M),
                       ("_SK_KORRIDOR_MAX_M", st.KORRIDOR_MAX_M)):
        m = re.search(rf"\b{name}\s*=\s*(\d+)\b", SKRIPT)
        assert m and float(m.group(1)) == wert, name


def test_ueber_der_grenze_wird_gewarnt_statt_gespeichert():
    vorschau = _rumpf("_skVorschau")
    assert re.search(r"t\.anzahl\s*>\s*_SK_ABSCHNITTE_MAX", vorschau)
    assert re.search(r"knopf\.disabled\s*=", vorschau)
    speichern = _rumpf("skSpeichern")
    grenze = re.search(r"t\.anzahl\s*>\s*_SK_ABSCHNITTE_MAX", speichern)
    assert grenze and grenze.start() < speichern.index("api('POST'")


def test_die_laenge_rechnet_mit_dem_kilometer_je_grad_des_servers():
    from app import abdeckung
    m = re.search(r"\b_SK_KM_JE_GRAD_LAT\s*=\s*([\d.]+)", SKRIPT)
    assert m and float(m.group(1)) == abdeckung._KM_JE_GRAD_LAT
    assert "_skMittlereBreite(punkte)" in _rumpf("_skLaengeKm")


def test_das_band_wird_beim_zoomen_neu_gerechnet():
    assert re.search(r"\.on\('zoomend',\s*_skLinieNachziehen\)", _rumpf("_skKarteAufbauen"))
    assert "_skBandBreitePx(" in _rumpf("_skLinieNachziehen")
    breite = _rumpf("_skBandBreitePx")
    assert "getZoom()" in breite and re.search(r"2\s*\*\s*korridorM\s*/\s*mProPx", breite)


def test_der_korridor_wirkt_sofort_auf_die_vorschau():
    assert re.search(r"addEventListener\('input',\s*_skLinieNachziehen\)", _rumpf("_skVerdrahten"))
    assert re.search(r"(?m)^\s*_skVerdrahten\(\);", SKRIPT)


# ------------------------------------------------------------------- Die Karte

def test_punkte_lassen_sich_ziehen_entfernen_und_zuruecknehmen():
    zeichnen = _rumpf("_skZeichnen")
    assert re.search(r"draggable:\s*true", zeichnen)
    assert "marke.on('drag'" in zeichnen and "_skPunktMenue(i)" in zeichnen
    assert "skPunktEntfernen(i)" in _rumpf("_skPunktMenue")
    assert "_skPunkte.splice(i, 1)" in _rumpf("skPunktEntfernen")
    assert "_skPunkte.push(" in _rumpf("_skKarteAufbauen")
    verdrahten = _rumpf("_skVerdrahten")
    assert "an('sk-zurueck-btn', skLetzterZurueck)" in verdrahten
    assert "an('sk-leeren-btn', skLeeren)" in verdrahten


def test_bearbeiten_laedt_die_strecke_und_passt_die_karte_ein():
    rumpf = _rumpf("skEdit")
    assert "_skPunkte = (ev.punkte || [])" in rumpf
    assert "_skFormOeffnen()" in rumpf
    assert "_skEinpassen()" in _rumpf("_skFormOeffnen")
    assert "fitBounds(" in _rumpf("_skEinpassen")


# ----------------------------------------------- Warnung vor dem Verwerfen des Stands

def test_vor_dem_verwerfen_des_stands_wird_gewarnt():
    rumpf = _rumpf("skSpeichern")
    warnung = rumpf.index("_skRechenwerteGeaendert(altEv, koerper)")
    assert warnung < rumpf.index("api('POST'"), "die Warnung muss VOR dem Speichern kommen"
    assert "altEv.laeuft" in rumpf and "altEv.vorbei_seit_s" in rumpf
    assert "showModal(" in rumpf[warnung:rumpf.index("api('POST'")]


def test_der_name_allein_loest_die_warnung_nicht_aus():
    rumpf = _rumpf("_skRechenwerteGeaendert")
    for feld in ("korridor_m", "hoehe_max_ft", "gs_max_kt", "gs_min_kt", "dtstart", "dtend", "punkte"):
        assert feld in rumpf, feld
    assert "name" not in rumpf


# -------------------------------------------------------------------- Die Liste

def test_die_liste_steht_im_scrollbaren_wrapper():
    rumpf = _rumpf("loadStrecke")
    assert '<div class="table-wrap"><table id="sk-tabelle">' in rumpf
    for feld in ("ev.laenge_km", "st.abschnitte", "st.km_abgedeckt", "st.km_gesamt", "st.anteil"):
        assert feld in rumpf, feld
    assert "skEdit(" in rumpf and "skLoeschen(" in rumpf
