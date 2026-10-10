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

def test_die_liste_sieht_aus_wie_die_der_reddung():
    """Nutzer, 10.10.2026: „das soll bei allen neuen Events so aussehen wie hier" -- Kopfzeile mit
    Abzeichen, Stand als Satz, Einzelheiten und die Knopfreihe Bearbeiten, Link, Push, Löschen."""
    rumpf = _rumpf("loadStrecke")
    assert 'class="list-row' in rumpf
    for feld in ("ev.laenge_km", "st.abschnitte", "st.km_abgedeckt", "st.km_gesamt", "st.anteil",
                 "st.je_pilot", "ev.korridor_m", "ev.push_enabled", "ev.farbe"):
        assert feld in rumpf, feld
    assert "badge-push-on" in rumpf and "badge-push-off" in rumpf and "_skZustand(ev)" in rumpf
    for knopf in ("skEdit(", "skCopyLink(", "skPush(", "skLoeschen("):
        assert knopf in rumpf, knopf


def test_push_und_link_haben_ihre_wege():
    assert "'/api/admin/strecke/events/' + id + '/push'" in _rumpf("skPush")
    assert "'/#tab=events&strecke=' + id" in _rumpf("skCopyLink")
    assert "_teilenUrsprung()" in _rumpf("skCopyLink")


def test_die_farbe_ist_eine_einstellung_im_formular():
    assert 'id="sk-farbe"' in ADMIN
    assert "skFarbeSetzen('eine')" in ADMIN and "skFarbeSetzen('pilot')" in ADMIN
    assert "farbe: _skFarbe" in _rumpf("skSpeichern")
    assert "skFarbeSetzen(ev.farbe)" in _rumpf("skEdit")
    assert "skFarbeSetzen('eine')" in _rumpf("_skFormSchliessen")


# ------------------------------------------------------------------ Fundstellen

def test_das_formular_hat_die_felder_der_fundstellen():
    for feld in ("sk-fundradius", "sk-fundhoehe", "sk-badge-name", "sk-modus",
                 "sk-fund-liste", "sk-fund-summe"):
        assert HTML.count(f'id="{feld}"') == 1, feld
    for feld, wert in (("sk-fundradius", st.VORGABE_FUND_RADIUS_M),
                       ("sk-fundhoehe", st.VORGABE_FUND_HOEHE_FT)):
        m = re.search(rf'<input[^>]*id="{feld}"[^>]*value="(\d+)"', HTML)
        assert m and float(m.group(1)) == wert, feld
        assert re.search(rf"'{feld}':\s*{int(wert)}\b", SKRIPT), f"{feld} fehlt in _SK_VORGABEN"


def test_die_grenzen_der_fundstellen_sind_die_des_servers():
    from app import database, gruppen
    for name, wert in (("_SK_FUNDSTELLEN_MAX", database.STRECKE_FUNDSTELLEN_MAX),
                       ("_SK_FUND_MENGE_MAX", gruppen.MENGE_MAX),
                       ("_SK_FUND_ABSTAND_MIN_M", gruppen.ABSTAND_MIN_M),
                       ("_SK_FUND_ABSTAND_MAX_M", gruppen.ABSTAND_MAX_M)):
        m = re.search(rf"\b{name}\s*=\s*(\d+)\b", SKRIPT)
        assert m and float(m.group(1)) == wert, name
    # Der Platz in der FriesenBrügge steht in app/main.py; als Text gelesen, ohne die App zu laden.
    main = (ADMIN_PFAD.parent.parent / "main.py").read_text(encoding="utf-8")
    soll = re.search(r"(?m)^_BRUEGGE_SOLL_MAX\s*=\s*(\d+)", main)
    hier = re.search(r"\b_SK_SOLL_MAX\s*=\s*(\d+)\b", SKRIPT)
    assert soll and hier and soll.group(1) == hier.group(1)
    pruefen = _rumpf("_skFundPruefen")
    for name in ("_SK_FUND_MENGE_MAX", "_SK_FUND_ABSTAND_MIN_M", "_SK_FUND_ABSTAND_MAX_M"):
        assert name in pruefen, name
    assert re.search(r"f\.menge_max\s*<\s*f\.menge_min", pruefen)
    assert re.search(r"f\.abstand_max_m\s*<\s*f\.abstand_min_m", pruefen)


def test_der_klickmodus_schaltet_auf_derselben_karte_um():
    assert "skModusSetzen('strecke')" in HTML and "skModusSetzen('fund')" in HTML
    assert re.search(r"_skModus\s*=\s*wahl === 'fund' \? 'fund' : 'strecke'", _rumpf("skModusSetzen"))
    karte = _rumpf("_skKarteAufbauen")
    modus = karte.index("_skModus === 'fund'")
    assert "skFundNeu(" in karte[modus:karte.index("_skPunkte.push(")], \
        "im Fundstellen-Modus darf der Klick keinen Streckenpunkt anhängen"
    assert "L.map(" in karte and karte.count("L.map(") == 1
    assert "skModusSetzen('strecke')" in _rumpf("_skFormSchliessen")


def test_eine_neue_fundstelle_bekommt_vorgaben_und_sofort_die_vorschau():
    rumpf = _rumpf("skFundNeu")
    assert "_SK_FUNDSTELLEN_MAX" in rumpf
    for feld in ("menge_min", "menge_max", "abstand_min_m", "abstand_max_m"):
        assert f"{feld}: _SK_FUND_VORGABE.{feld}" in rumpf, feld
    assert re.search(r"richtung:\s*null", rumpf) and "_skLetzteArt" in rumpf
    assert "_skFundVorschau(f, true)" in rumpf
    m = re.search(r"_SK_FUND_VORGABE\s*=\s*\{([^}]*)\}", SKRIPT)
    assert m and re.sub(r"\s", "", m.group(1)) == "menge_min:5,menge_max:8,abstand_min_m:8,abstand_max_m:20"


def test_die_vorschau_kommt_vom_server_und_haelt_den_startwert():
    rumpf = _rumpf("_skFundVorschau")
    assert "api('POST', '/api/admin/strecke/streuen', koerper)" in rumpf
    # Nur „neu würfeln“ lässt den Startwert weg -- sonst bleibt der bisherige.
    assert re.search(r"if \(neuWuerfeln \|\| !koerper\.startwert\) delete koerper\.startwert;", rumpf)
    assert "f.startwert = d.startwert" in rumpf and "f.menge = d.menge" in rumpf
    assert "f.objekte" in rumpf and "lauf !== f.anfrage" in rumpf
    # Geänderte Angaben holen sie entprellt und mit dem bisherigen Startwert neu.
    eingabe = _rumpf("_skFundEingabe")
    assert "setTimeout(" in eingabe and "_skFundVorschau(f, false)" in eingabe
    assert "_skFundVorschau(f, true)" in _rumpf("_skFundKlick")      # der Knopf „Neu würfeln“
    verdrahten = _rumpf("_skVerdrahten")
    assert "addEventListener('input', _skFundEingabe)" in verdrahten
    assert "addEventListener('click', _skFundKlick)" in verdrahten


def test_fundstellen_gehen_ganz_und_mit_startwert_im_koerper_mit():
    rumpf = _rumpf("skSpeichern")
    assert "fundstellen: _skFundstellen.map(_skFundAngaben)" in rumpf
    for feld, quelle in (("fund_radius_m", "sk-fundradius"), ("fund_hoehe_ft", "sk-fundhoehe")):
        assert re.search(rf"{feld}:\s*_rdZahl\('{quelle}'", rumpf), feld
    assert re.search(r"badge_name:\s*document\.getElementById\('sk-badge-name'\)", rumpf)
    angaben = _rumpf("_skFundAngaben")
    for feld in ("lat", "lon", "art", "menge_min", "menge_max", "abstand_min_m",
                 "abstand_max_m", "richtung", "startwert"):
        assert re.search(rf"\b{feld}:\s*f\.{feld}\b", angaben), f"{feld} wird nicht geschickt"
    # Der Ort einer geladenen Fundstelle bleibt, wie er kam -- gerundet gälte sie als neu.
    laden = _rumpf("_skFundAusServer")
    assert "lat: Number(z.lat), lon: Number(z.lon)" in laden and "toFixed" not in laden
    assert "startwert: z.startwert" in laden


def test_bearbeiten_laedt_fundstellen_und_die_neuen_felder():
    rumpf = _rumpf("skEdit")
    assert "_skFundstellen = (ev.fundstellen || []).map(_skFundAusServer)" in rumpf
    for feld, quelle in (("sk-fundradius", "ev.fund_radius_m"), ("sk-fundhoehe", "ev.fund_hoehe_ft"),
                         ("sk-badge-name", "ev.badge_name")):
        assert f"setz('{feld}', {quelle})" in rumpf, feld
    zu = _rumpf("_skFormSchliessen")
    assert "_skFundstellen = []" in zu and "'sk-badge-name'" in zu


def test_die_arten_kommen_aus_der_bruegge_und_nur_anforderbare():
    rumpf = _rumpf("_skArtenLaden")
    assert "api('GET', '/api/admin/bruegge/arten')" in rumpf
    assert "_bgArtenAlle" in rumpf, "die schon geladene Liste der Brügge-Verwaltung mitbenutzen"
    assert re.search(r"filter\(function \(a\) \{ return a\.anforderbar; \}\)", rumpf)
    liste = _rumpf("_skFundListe")
    assert "escH(a.art)" in liste and "escH(a.bedeutung || a.art)" in liste
    assert "_skArtenLaden()" in _rumpf("_skFormOeffnen")


def test_die_liste_der_fundstellen_hat_felder_und_knoepfe():
    liste = _rumpf("_skFundListe")
    for feld in ("art", "menge_min", "menge_max", "abstand_min_m", "abstand_max_m", "richtung"):
        assert f"'{feld}'" in liste or f'data-feld="{feld}"' in liste, feld
    for tat in ("wuerfeln", "weg"):
        assert f'data-tat="{tat}"' in liste, tat
    stand = _rumpf("_skFundStand")
    assert "f.gefunden_am" in stand and "escH(f.gefunden_name" in stand
    assert "_skFundKern(f) !== f.ur" in stand          # Hinweis: der Fund geht verloren
    assert "skFundEntfernen(f.schluessel)" in _rumpf("_skFundKlick")
    assert "_skFundstellen.splice(i, 1)" in _rumpf("skFundEntfernen")


def test_fundstellen_stehen_auf_der_karte_mit_objekten_und_fundradius():
    rumpf = _rumpf("_skFundZeichnen")
    assert "_rdZahl('sk-fundradius'" in rumpf and "L.circle(" in rumpf
    assert "L.circleMarker([o.lat, o.lon]" in rumpf
    assert re.search(r"draggable:\s*true", rumpf) and "_skFundMenue(f)" in rumpf
    ziehen = rumpf[rumpf.index("marke.on('dragend'"):]
    assert "_skFundVorschau(f, false)" in ziehen, "nach dem Ziehen: Vorschau mit gleichem Startwert"
    assert "skFundEntfernen(f.schluessel)" in _rumpf("_skFundMenue")
    assert "'sk-fund'" in _rumpf("_skFundIcon")
    assert re.search(r"\.sk-fund i[^{]*\{[^}]*#D75F28", ADMIN, re.S), "Marke in Friesen-Orange"
    assert re.search(r"radius\.addEventListener\('input',\s*_skFundZeichnen\)", _rumpf("_skVerdrahten"))


def test_die_summe_rechnet_rauch_und_licht_ein():
    rumpf = _rumpf("_skFundSumme")
    assert re.search(r"objekte \+ _SK_FUND_BEIWERK \* n", rumpf) and "_SK_SOLL_MAX" in rumpf
    assert re.search(r"\b_SK_FUND_BEIWERK\s*=\s*2\b", SKRIPT)
    assert "f.menge" in rumpf and "'sk-fund-summe'" in rumpf
    speichern = _rumpf("skSpeichern")
    assert speichern.index("_skFundSumme() > _SK_SOLL_MAX") < speichern.index("api('POST'")


def test_fundradius_fundhoehe_fundstellen_und_badge_sind_keine_rechenwerte():
    """Fundradius und Fundhöhe gelten ab dem Speichern für das, was noch offen ist; der Server
    verwirft dafür nichts (`_STRECKE_OHNE_RECHNUNG`), also darf die Verwaltung auch nicht warnen."""
    from app.database import _STRECKE_OHNE_RECHNUNG
    rumpf = _rumpf("_skRechenwerteGeaendert")
    assert {"fund_radius_m", "fund_hoehe_ft"} <= _STRECKE_OHNE_RECHNUNG
    assert "'fund_radius_m'" not in rumpf and "'fund_hoehe_ft'" not in rumpf
    assert "fundstellen" not in rumpf and "badge" not in rumpf


def test_hoechstmenge_mal_hoechstabstand_ist_begrenzt_wie_auf_dem_server():
    from app.database import STRECKE_FUND_MENGE_MAL_ABSTAND_MAX
    assert f"const _SK_FUND_MENGE_MAL_ABSTAND_MAX = {STRECKE_FUND_MENGE_MAL_ABSTAND_MAX:g};" in SKRIPT
    assert "f.menge_max * f.abstand_max_m > _SK_FUND_MENGE_MAL_ABSTAND_MAX" in _rumpf("_skFundPruefen")
    vorgabe = re.search(r"const _SK_FUND_VORGABE = \{[^}]*menge_max: (\d+)[^}]*abstand_max_m: (\d+)", SKRIPT)
    assert int(vorgabe.group(1)) * int(vorgabe.group(2)) <= STRECKE_FUND_MENGE_MAL_ABSTAND_MAX


def test_eine_neue_fundstelle_beginnt_nicht_mit_der_ersten_art_des_alphabets():
    assert "const _SK_FUND_ART_VORGABE = 'seehund_kuh';" in SKRIPT
    assert "_SK_FUND_ART_VORGABE" in _rumpf("skFundNeu")


def test_ein_fund_der_verloren_geht_wird_eigens_gemeldet():
    # Ein Fund, der durch eine geänderte oder entfernte Fundstelle verloren geht, wird eigens gemeldet.
    speichern = _rumpf("skSpeichern")
    assert speichern.index("_skFundeVerloren(altEv)") < speichern.index("api('POST'")
    assert "_skFundKern(f) === f.ur" in _rumpf("_skFundeVerloren")


def test_die_liste_der_events_nennt_die_fundstellen():
    rumpf = _rumpf("loadStrecke")
    assert "<tr><td>Fundstellen</td><td>' + fundZeile" in rumpf
    for feld in ("st.fundstellen", "fs.gefunden", "x.funde", "ev.fund_radius_m", "ev.fund_hoehe_ft"):
        assert feld in rumpf, feld
    assert "' von ' + _skZahl(fundAnzahl) + ' gefunden'" in rumpf and "'keine'" in rumpf
    # Fundradius und Fundhöhe stehen in der Vorgabe nur, wenn es Fundstellen gibt.
    assert re.search(r"\(fundAnzahl\s*\?[^:]*ev\.fund_radius_m", rumpf, re.S)
