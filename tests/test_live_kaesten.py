"""Kaesten auf dem Live-Reiter (Nutzer 04.10.2026): Der leere Prefile-Kasten war hoeher als die
Live-Positionen. Er ist jetzt so niedrig wie der TeamSpeak-Kasten und waechst mit den Zeilen."""
import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def test_leerer_prefile_kasten_ist_so_niedrig_wie_teamspeak():
    m = re.search(r"#prefiles-content \.empty-state,\s*#ts-content \.empty-state \{([^}]*)\}", INDEX)
    assert m, "Regel fuer die niedrigen Leerzustaende fehlt"
    assert "padding: 0" in m.group(1)


def test_prefile_liste_hat_keine_feste_hoehe():
    """Mehrere Flugplaene: Die Tabelle bestimmt die Hoehe, nichts deckelt sie."""
    for regel in re.findall(r"#prefiles-content[^{]*\{([^}]*)\}", INDEX):
        assert "max-height" not in regel and not re.search(r"(?<!-)height:", regel)
    js = INDEX[INDEX.index("function renderPrefiles("):INDEX.index("function renderTeamspeak(")]
    assert '<div class="live-table-wrap"><table>' in js
