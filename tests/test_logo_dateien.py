"""Logo-Dateien: Namen und Farbwerte wie in der zentralen Ablage (Repo friesenflieger-logo)."""
import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
LOGO = WURZEL / "app" / "static" / "logo"
INDEX = (WURZEL / "app" / "static" / "index.html").read_text(encoding="utf-8")


def test_dateinamen_folgen_der_gemeinsamen_benennung():
    """Name_Farbfassung[_s]: _s ist die Fassung ohne Inseln; so heissen sie auch beim Verein."""
    assert sorted(p.name for p in LOGO.iterdir()) == [
        "FriesenRadar_colored_s.svg", "FriesenRadar_symbol.svg",
        "FriesenRadar_symbol_maskable.svg", "FriesenRadar_white+red_s.svg"]


def test_seite_verweist_nur_auf_vorhandene_logo_dateien():
    verweise = set(re.findall(r"/static/logo/([^'\")\s]+)", INDEX))
    assert verweise == {"FriesenRadar_colored_s.svg", "FriesenRadar_white+red_s.svg"}
    for name in verweise:
        assert (LOGO / name).is_file(), name


def test_farbwerte_sind_die_der_richtlinien():
    """Blau 191d53, Rot 8a1b1b. Bis 08.10.2026 standen 201f52 und 8b1c1c in den Dateien."""
    for datei in LOGO.glob("*.svg"):
        farben = {f.lower() for f in re.findall(r"#[0-9a-fA-F]{3,6}\b", datei.read_text(encoding="utf-8"))}
        assert farben <= {"#191d53", "#8a1b1b", "#fff", "#ffffff"}, (datei.name, farben)
