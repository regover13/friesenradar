"""Einstellungsmenue: Zahnrad ueberall, Design-Schalter (Spec helles Design)."""
import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _knopf():
    return re.search(r'<button id="notif-btn"[^>]*>', INDEX).group(0)


def test_zahnrad_auf_der_website_statt_glocke():
    assert 'class="emoji-icon notif-glocke-web"' not in INDEX
    assert re.search(r"(?m)^\s*\.notif-zahnrad-panel \{[^}]*display: inline-block", INDEX)
    assert 'title="Einstellungen"' in _knopf()


def test_knopf_ist_ohne_vapid_sichtbar():
    # Review Focus 4
    assert " hidden" not in _knopf()
    assert "document.getElementById('notif-btn').hidden = false;" not in INDEX


def test_menue_heisst_ueberall_einstellungen():
    assert '<div class="notif-panel-title">Einstellungen</div>' in INDEX


def test_design_schalter_sind_knoepfe_keine_checkbox():
    block = INDEX[INDEX.index('id="einst-design"'):INDEX.index('id="panel-anzeige"')]
    assert 'id="design-dunkel"' in block and 'id="design-hell"' in block
    assert "checkbox" not in block
    assert block.count('class="panel-abschnitt-titel"') == 1  # "Anzeige"


def test_anzeige_nur_einmal_ueberschrieben():
    # Review Focus 5: #panel-anzeige hat keine eigene Ueberschrift mehr.
    anzeige = INDEX[INDEX.index('<div id="panel-anzeige"'):INDEX.index('<div id="panel-notif"')]
    assert "panel-abschnitt-titel" not in anzeige


def test_benachrichtigungen_ueberschrift_nur_mit_push():
    assert 'id="notif-web-titel"' in INDEX
    # Dieselben sieben wie in der html.vr-panel-Liste (Z. 819-825) plus die Ueberschrift.
    for teil in ("#notif-web-titel", "#notif-enabled-row", "#notif-filter", "#notif-ios-hint",
                 "#notif-blocked-hint", "#notif-install-btn", "#notif-reset-btn",
                 "#visibility-section"):
        assert re.search(r"\.notif-panel:not\(\.mit-push\) " + re.escape(teil) + r"\b", INDEX), teil
    assert "classList.add('mit-push')" in INDEX
    assert "html.vr-panel #notif-web-titel" in INDEX


def test_design_knopf_im_kniebrett_44px():
    assert re.search(r"html\.vr-panel \.design-knopf \{[^}]*min-height: 44px", INDEX)


def test_schalter_folgt_dem_design():
    assert "_designHaken.push(_designSchalterAnzeigen);" in INDEX
    assert "_designSetzen('hell')" in INDEX and "_designSetzen('dunkel')" in INDEX
