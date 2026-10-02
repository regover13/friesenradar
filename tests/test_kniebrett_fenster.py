"""Fenster im Kniebrett: Der Schliessen-Knopf muss erreichbar sein (Nutzerfund 02.10.2026).

Im Kniebrett liegt die feste Leiste (z-index 999997) ueber den Fenstern (z-index 10000), und
der Zoom (1,35) blaeht `max-height: 85vh`/`88vh` auf rund 115 % des Bildschirms auf. Ein
zentriertes Fenster mit langem Inhalt schob seine Kopfzeile damit ueber den oberen Rand bzw.
unter die Leiste -- man kam aus Muster, Flugplan, Strecke & Co. nicht mehr heraus. Gemessen
(Playwright, 468/748/900 px Breite): alle sechs Fenster, Knopf bei y = -20 bis -42.

Vorbild ist der Hinweis-Stapel (`.panel-hinweis-stapel`, top: 72px): Fenster beginnen im
Kniebrett UNTER der Leiste und werden hoechstens so hoch wie der Platz darunter (`100%` statt
`vh` -- Prozent bezieht sich auf das Overlay und ist damit vom Zoom unabhaengig).
"""
import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _regel(selektor_muster):
    m = re.search(selektor_muster + r"[^{]*\{([^}]*)\}", INDEX)
    assert m, selektor_muster
    return m.group(1)


def test_overlays_beginnen_im_kniebrett_unter_der_leiste():
    r = _regel(r"html\.vr-panel \.fp-modal-overlay,\s*html\.vr-panel \.modal\b")
    assert "top: 72px" in r
    assert "align-items: flex-start" in r


def test_fenster_sind_hoechstens_so_hoch_wie_der_platz_darunter():
    r = _regel(r"html\.vr-panel \.fp-modal-box,\s*html\.vr-panel #ac-modal \.modal-box")
    assert "max-height: 100%" in r
    assert "vh" not in r, "vh wird im Kniebrett vom Zoom aufgeblaeht"


def test_jedes_fenster_ist_ein_erfasstes_overlay():
    # Kommt ein siebtes Fenster dazu, muss es eine der beiden Klassen tragen -- sonst gilt die
    # Regel oben nicht fuer es.
    ids = re.findall(r'<div id="([\w-]+-modal)" class="([^"]*)"', INDEX)
    assert len(ids) >= 6, ids
    for i, k in ids:
        assert "fp-modal-overlay" in k.split() or "modal" in k.split(), (i, k)
