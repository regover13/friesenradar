"""Das Logo in der Kopfzeile fuehrt zur Homepage der FriesenFlieger (Wunsch aus dem Verein,
08.10.2026) -- wie im Forum. Im TV-Modus nicht: Dort wuerde ein Druck auf der Fernbedienung
den Fernseher aus FriesenRadar hinaustragen."""
import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _logo():
    return re.search(r'<a class="logo"[^>]*>.*?</a>', INDEX, re.S)


def test_logo_ist_ein_link_zur_homepage():
    m = _logo()
    assert m, "Das Logo in der Kopfzeile muss ein Link sein"
    assert 'href="https://friesenflieger.de"' in m.group(0)
    assert m.group(0).count("<img") == 2, "beide Logo-Fassungen bleiben im Link"


def test_logo_link_hat_eine_beschriftung():
    assert 'title="Zur Homepage der FriesenFlieger"' in _logo().group(0)


def test_im_tv_modus_ist_das_logo_kein_link():
    assert re.search(r"html\.tv a\.logo\s*\{[^}]*pointer-events:\s*none", INDEX)
    assert "document.querySelector('a.logo').removeAttribute('href')" in INDEX
