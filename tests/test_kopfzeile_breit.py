"""Kopfzeile auf breiten Bildschirmen (Nutzer 03.10.2026): Name links, LIVE vor Zahnrad,
Hilfe unter der Version in deren Schrift. Das Kniebrett bleibt unberuehrt; das Handy
verteilt seit 04.10.2026 ebenso (Name links, Zahnrad und Version rechts)."""
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
    assert "grid-column: 1" in _regel("header #sse-badge ")
    assert "grid-column: 2" in _regel("header #utc-clock ")
    assert "grid-column: 3" in _regel("header #notif-btn ")


def test_verbindungskasten_nur_bei_abriss():
    """Verbunden ist der Normalfall und wird nicht angezeigt; nur das rote GETRENNT erscheint.
    Im Markup startet der Kasten als .disconnected -- bis die Verbindung steht, ist er also da."""
    assert "html:not(.vr-panel) header #sse-badge:not(.disconnected) { display: none; }" in INDEX
    assert '<div id="sse-badge" class="sse-badge disconnected">' in INDEX


def test_hilfe_unter_der_version_in_derselben_schrift():
    version = _regel("header #app-version")
    hilfe = _regel("header .help-btn")
    assert "grid-column: 4" in version and "grid-row: 1" in version
    assert "grid-column: 4" in hilfe and "grid-row: 2" in hilfe
    basis = re.search(r"\n    \.app-version \{([^}]*)\}", INDEX).group(1)
    for eig in ["font-family: var(--text-mono)", "font-size: 0.7rem", "opacity: 0.55"]:
        assert eig in basis and eig in hilfe, eig
    assert "border: none" in hilfe


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
