"""Kopfzeile (Nutzer 03./04.10.2026): Name links, rechts Uhr und Zahnrad, bei Abriss davor
GETRENNT. Hilfe und Version stehen seit 04.10.2026 in der Fussleiste. Das Handy verteilt
ebenso (Name links, Zahnrad rechts); das Kniebrett bleibt unberuehrt."""
import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _block():
    start = INDEX.index("@media (min-width: 601px) {\n      html:not(.vr-panel) header { position: relative; }")
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
    assert '<div id="sse-badge" class="sse-badge disconnected">' in INDEX


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


def test_name_steht_links():
    assert "left: 18px" in _regel("header #userBox")


def test_beide_kaesten_gleich_hoch():
    m = re.search(r"header #sse-badge,\s*html:not\(\.vr-panel\) header #notif-btn \{([^}]*)\}", _block())
    assert m and "height: 32px" in m.group(1)


def _schmal():
    start = INDEX.index("@media (max-width: 600px) {\n      header { grid-template-columns: 1fr;")
    return INDEX[start:INDEX.index("/* Breite Bildschirme, nur Website", start)]


def test_handy_verteilt_wie_die_website():
    """Nutzer 04.10.2026: auch auf dem Handy Name links, Zahnrad und Version rechts -- die
    Zeile unter dem Logo nimmt dafuer die ganze Breite ein."""
    block = _schmal()
    zeile = re.search(r"html:not\(\.vr-panel\) header \.header-right \{([^}]*)\}", block)
    assert zeile, "Regel fuer die Zeile unter dem Logo fehlt"
    assert "justify-self: stretch" in zeile.group(1)
    assert "justify-content: flex-end" in zeile.group(1)
    name = re.search(r"html:not\(\.vr-panel\) header #userBox \{([^}]*)\}", block)
    assert name and "margin-right: auto" in name.group(1)


def test_handy_zahnrad_steht_ganz_rechts():
    """Wie auf der Website: erst die Version, dann das Zahnrad. Das Markup bleibt, die
    Reihenfolge kommt aus `order`."""
    zahnrad = re.search(r"html:not\(\.vr-panel\) header #notif-btn \{([^}]*)\}", _schmal())
    assert zahnrad and "order: 1" in zahnrad.group(1)
