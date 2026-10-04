"""Kopfzeile (Nutzer 03./04.10.2026): Logo mittig, rechts Uhr und Zahnrad, bei Abriss davor
GETRENNT. Hilfe und Version stehen in der Fussleiste, der Name samt Abmelden im Zahnradmenue.
Auf dem Handy steht das Zahnrad rechts neben dem Logo; das Kniebrett bleibt unberuehrt."""
import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _block():
    start = INDEX.index("@media (min-width: 601px) {\n      html:not(.vr-panel) header .header-right {")
    return INDEX[start:INDEX.index("/* Verbindungsanzeige auf der Website nur bei Abriss", start)]


def _regel(sel):
    m = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", _block())
    assert m, sel
    return m.group(1)


def test_alles_nur_fuer_die_website():
    for zeile in _block().splitlines():
        if "{" in zeile and zeile.strip().startswith(("html", "header", "#", ".")):
            assert zeile.strip().startswith("html:not(.vr-panel) header"), zeile


def test_reihenfolge_getrennt_uhr_zahnrad():
    """Das Zahnrad steht ganz rechts; Version und Hilfe sind in die Fussleiste gezogen."""
    assert "grid-column: 1" in _regel("header #sse-badge ")
    assert "grid-column: 2" in _regel("header #utc-clock ")
    assert "grid-column: 3" in _regel("header #notif-btn ")
    assert "app-version" not in _block() and "help-btn" not in _block()


def test_verbindungskasten_nur_bei_abriss():
    """Verbunden ist der Normalfall und wird nicht angezeigt; nur das rote GETRENNT erscheint.
    Im Markup startet der Kasten als .disconnected -- bis die Verbindung steht, ist er also da."""
    assert "html:not(.vr-panel) header #sse-badge:not(.disconnected) { display: none; }" in INDEX
    assert '<div id="sse-badge" class="sse-badge disconnected sse-start">' in INDEX


def test_getrennt_blitzt_beim_laden_nicht_auf():
    """Bis die Verbindung zum ersten Mal steht, bleibt der Kasten weg -- sonst sprang die
    Kopfzeile auf dem Handy bei jedem Laden um eine Zeile. Steht sie nach ein paar Sekunden
    nicht, erscheint GETRENNT trotzdem."""
    assert "html:not(.vr-panel) header #sse-badge.sse-start { display: none; }" in INDEX
    js = INDEX[INDEX.index("function setSSEStatus("):INDEX.index("function connectSSE(")]
    assert "if (live) badge.classList.remove('sse-start');" in js
    assert re.search(r"setTimeout\(function \(\) \{[^}]*classList\.remove\('sse-start'\)[^}]*\}, 5000\)", js)


def _kopf():
    return INDEX[INDEX.index("<header>"):INDEX.index("</header>")]


def _fuss():
    start = INDEX.index("<footer")
    return INDEX[start:INDEX.index("</footer>", start)]


def test_hilfe_und_version_stehen_nicht_mehr_in_der_kopfzeile():
    kopf = _kopf()
    assert 'id="app-version"' not in kopf
    assert "HILFE" not in kopf and "help-btn" not in INDEX


def test_fussleiste_downloads_impressum_datenschutz_hilfe_version():
    """Nutzer 04.10.2026: Downloads - Impressum - Datenschutz - Hilfe - v16.0.0 Lichtblick."""
    fuss = _fuss()
    stellen = [fuss.index(t) for t in (
        '<a href="/download" style="color:var(--green);">Downloads</a>',
        '<a href="/impressum" style="color:var(--green);">Impressum</a>',
        '<a href="/datenschutz" style="color:var(--green);">Datenschutz</a>',
        '>Hilfe</a>',
        '<button id="app-version" class="app-version"',
    )]
    assert stellen == sorted(stellen)
    hilfe = re.search(r'<a href="https://github\.com/regover13/friesenradar#readme"[^>]*>Hilfe</a>', fuss)
    assert hilfe and 'target="_blank"' in hilfe.group(0) and 'rel="noopener"' in hilfe.group(0)
    assert INDEX.count('id="app-version"') == 1


def test_version_nennt_erst_die_nummer_dann_den_namen():
    """In der Fussleiste ist die Nummer die Angabe und der Name der Zusatz. Solange die
    Version nicht geladen ist, steht auch kein Trennpunkt davor."""
    js = INDEX[INDEX.index("function _initVersionUI("):]
    js = js[:js.index("badge.addEventListener('click', openChangelogModal)")]
    assert js.index('class="app-version-nr"') < js.index('class="app-version-name"')
    assert re.search(r'<span id="app-version-trenner" hidden>[^<]*</span>\s*<button id="app-version"', _fuss())
    assert "app-version-trenner" in js


def test_name_steht_im_zahnradmenue_ganz_oben():
    """Nutzer 04.10.2026: Den Namen braucht die Kopfzeile nicht -- er steht im Zahnradmenue
    ganz oben, daneben Abmelden."""
    assert "userName" not in _kopf() and "userBox" not in INDEX
    menue = INDEX[INDEX.index('<div id="notif-panel"'):]
    konto = menue.index('<div id="einst-konto" hidden>')
    assert menue.index('class="notif-panel-title"') < konto < menue.index('<div id="einst-design">')
    assert menue.index('id="userName"') > konto
    assert INDEX.count('id="userName"') == 1


def test_abmelden_fragt_nach_und_nennt_das_forum():
    menue = INDEX[INDEX.index('<div id="einst-konto" hidden>'):INDEX.index('<div id="einst-design">')]
    assert '<button type="button" class="design-knopf" id="abmelden-btn" hidden>Abmelden</button>' in menue
    frage = menue[menue.index('<div id="abmelden-frage" hidden>'):]
    assert "auch vom Forum ab" in frage
    assert 'id="abmelden-ja"' in frage and 'id="abmelden-nein"' in frage
    assert '<form id="abmelden-form" method="post" action="/auth/forum/logout"' in frage
    # Der Knopf erscheint nur, wenn die Bruecke abmelden kann; abgeschickt wird erst nach "Ja".
    assert "getElementById('abmelden-btn').hidden = !d.kann_abmelden" in INDEX
    js = INDEX[INDEX.index("function _abmeldenEinrichten("):]
    js = js[:js.index("\n}\n")]
    ja = js[js.index("getElementById('abmelden-ja')"):]
    assert "getElementById('abmelden-form').submit()" in ja
    assert INDEX.count("abmelden-form').submit()") == 1


def test_kniebrett_zeigt_weder_name_noch_abmelden():
    assert "html.vr-panel #einst-konto { display: none !important; }" in INDEX


def test_beide_kaesten_gleich_hoch():
    m = re.search(r"header #sse-badge,\s*html:not\(\.vr-panel\) header #notif-btn \{([^}]*)\}", _block())
    assert m and "height: 32px" in m.group(1)


def _schmal():
    start = INDEX.index("@media (max-width: 600px) {\n      header { grid-template-columns: 1fr auto 1fr;")
    return INDEX[start:INDEX.index("/* Breite Bildschirme, nur Website", start)]


def test_handy_zahnrad_steht_rechts_neben_dem_logo():
    """Nutzer 04.10.2026: eine Zeile -- Logo mittig, Zahnrad rechts daneben. GETRENNT bekommt
    bei Abriss eine eigene Zeile darunter, neben dem Logo ist dafuer kein Platz."""
    block = _schmal()
    assert "display: contents" in re.search(r"html:not\(\.vr-panel\) header \.header-right \{([^}]*)\}", block).group(1)
    zahnrad = re.search(r"html:not\(\.vr-panel\) header #notif-btn \{([^}]*)\}", block).group(1)
    assert "grid-column: 3" in zahnrad and "grid-row: 1" in zahnrad and "justify-self: end" in zahnrad
    getrennt = re.search(r"html:not\(\.vr-panel\) header #sse-badge \{([^}]*)\}", block).group(1)
    assert "grid-column: 1 / -1" in getrennt and "grid-row: 2" in getrennt


def test_klick_auf_den_namen_schliesst_das_menue():
    """Der Name oeffnet die eigene Statistik -- das Menue darf danach nicht darueber stehen
    bleiben. Der allgemeine Schliess-Lauscher sieht den Klick nicht (er liegt im Menue, und
    der Namens-Klick haelt ihn in der Einfangphase an), deshalb schliesst _pilotLinkKlick selbst."""
    js = INDEX[INDEX.index("function _pilotLinkKlick("):]
    js = js[:js.index("\n}\n")]
    assert "el.closest('#notif-panel')" in js and ".hidden = true" in js
