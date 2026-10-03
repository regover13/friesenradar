"""Kopfzeile auf breiten Bildschirmen (Nutzer 03.10.2026): Name links, LIVE vor Zahnrad,
Hilfe unter der Version in deren Schrift. Handy und Kniebrett bleiben unberuehrt."""
import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _block():
    start = INDEX.index("@media (min-width: 601px) {\n      html:not(.vr-panel) header { position: relative; }")
    return INDEX[start:INDEX.index("/* Kniebrett: Logo statt Schriftzug", start)]


def _regel(sel):
    m = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", _block())
    assert m, sel
    return m.group(1)


def test_alles_nur_fuer_die_website():
    for zeile in _block().splitlines():
        if "{" in zeile and zeile.strip().startswith(("html", "header", "#", ".")):
            assert zeile.strip().startswith("html:not(.vr-panel) header"), zeile


def test_live_steht_vor_dem_zahnrad():
    assert "grid-column: 1" in _regel("header #sse-badge ")
    assert "grid-column: 2" in _regel("header #notif-btn ")


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
