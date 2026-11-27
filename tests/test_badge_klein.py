"""Badges in Forengröße (27.11.2026): ?px= an allen drei Forum-Badges, Kopier-Knöpfe mit 128 px."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
INDEX = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _rumpf(name):
    m = re.search(r"\ndef " + name + r"\(.*?(?=\n@app\.|\ndef |\nasync def )", MAIN, re.S) or \
        re.search(r"\nasync def " + name + r"\(.*?(?=\n@app\.|\ndef |\nasync def )", MAIN, re.S)
    assert m, name
    return m.group(0)


def test_alle_drei_forum_badges_kennen_px():
    for name in ("get_transport_badge", "get_bummel_badge", "get_reddung_badge"):
        r = _rumpf(name)
        assert "px: int | None = None" in r, name
        assert "_badge_klein(png, px, path)" in r, name
        assert "_badge_px(px)" in r, name


def test_kopier_knoepfe_haengen_128_px_an():
    for adresse in ("/api/bummel/race/${raceId}/badge/${cid}.png",
                    "/api/transport/event/${eventId}/badge/${cid}.png",
                    "/api/reddung/events/${eventId}/badge/${cid}.png"):
        assert f"[img]${{_teilenUrsprung()}}{adresse}?px=128[/img]" in INDEX, adresse


def test_grenzen():
    import app.main as main
    assert main._badge_px(None) is None
    assert main._badge_px(256) is None          # Originalgröße braucht keine Rechnung
    assert main._badge_px(128) == 128
    assert main._badge_px(1) == 32
    assert main._badge_px(5000) is None
