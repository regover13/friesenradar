"""Kästen auf dem Live-Reiter.

Höhe (Nutzer 04.10.2026): Der leere Prefile-Kasten war höher als die Live-Positionen. Er ist
jetzt so niedrig wie der TeamSpeak-Kasten und wächst mit den Zeilen.

Verschieben und einklappen, je Gerät gemerkt (Nutzerwunsch 08.11.2026).

„TeamSpeak nach oben, Planung nach unten, Planung ausklappen“ -- die drei festen Kästen
(Live-Positionen, Geplant, Im TeamSpeak) lassen sich umsortieren und zuklappen. Die
Event-Kästen (Reddung, Bummel, Kutter) stehen immer davor und sind nicht beweglich.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")
README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")

node = pytest.mark.skipif(not shutil.which("node"), reason="node fehlt")


def _funktion(name):
    m = re.search(r"\nfunction " + name + r"\(.*?\n}\n", INDEX, re.S)
    assert m, name
    return m.group(0)


def _js(ausdruck, *funktionen):
    vorspann = re.search(r"\nconst _LK_STANDARD = .*?;\n", INDEX).group(0)
    js = vorspann + "".join(_funktion(f) for f in funktionen) + f"\nconsole.log(JSON.stringify({ausdruck}));"
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


@node
@pytest.mark.parametrize("roh, reihe, zu", [
    (None, ["live", "geplant", "ts"], []),                       # nichts gemerkt: heutiger Aufbau
    ("", ["live", "geplant", "ts"], []),
    ("ts,live,geplant|geplant", ["ts", "live", "geplant"], ["geplant"]),
    ("ts|", ["ts", "live", "geplant"], []),                      # fehlende hinten angehängt
    ("ts,quatsch,ts,live|quatsch,live", ["ts", "live", "geplant"], ["live"]),  # Unbekanntes und Doppeltes fällt weg
    ("kaputt ohne trenner", ["live", "geplant", "ts"], []),
])
def test_merker_lesen(roh, reihe, zu):
    out = _js(f"_lkLesen({json.dumps(roh)})", "_lkLesen")
    assert out == {"reihe": reihe, "zu": zu}


@node
def test_merker_schreiben_passt_in_den_serverspeicher():
    s = _js('_lkSchreiben({reihe: ["ts", "live", "geplant"], zu: ["live", "geplant", "ts"]})', "_lkSchreiben")
    assert s == "ts,live,geplant|live,geplant,ts"
    assert len(s) <= 200   # _PREFS_MAX_LAENGE in app/main.py


@node
@pytest.mark.parametrize("reihe, kasten, richtung, sichtbar, erwartet", [
    (["live", "geplant", "ts"], "ts", -1, ["live", "geplant", "ts"], ["live", "ts", "geplant"]),
    (["live", "geplant", "ts"], "live", -1, ["live", "geplant", "ts"], ["live", "geplant", "ts"]),   # oben: bleibt
    (["live", "geplant", "ts"], "ts", 1, ["live", "geplant", "ts"], ["live", "geplant", "ts"]),      # unten: bleibt
    # TeamSpeak ausgeblendet: Live springt mit einem Druck an Geplant vorbei, nicht unsichtbar hinter TS
    (["live", "ts", "geplant"], "live", 1, ["live", "geplant"], ["ts", "geplant", "live"]),
    (["live", "ts", "geplant"], "geplant", -1, ["live", "geplant"], ["geplant", "live", "ts"]),
])
def test_verschieben_ueberspringt_ausgeblendete(reihe, kasten, richtung, sichtbar, erwartet):
    out = _js(f"_lkVerschieben({json.dumps(reihe)}, {json.dumps(kasten)}, {richtung}, {json.dumps(sichtbar)})",
              "_lkVerschieben")
    assert out == erwartet


def test_drei_kaesten_im_behaelter_events_davor():
    beginn = INDEX.index('<div id="live-kaesten">')
    for banner in ("reddung-banner", "bummel-banner", "kutter-banner"):
        assert INDEX.index(f'id="{banner}"') < beginn
    for kasten in ("live", "geplant", "ts"):
        assert f'data-kasten="{kasten}"' in INDEX[beginn:beginn + 4000]


def test_teamspeak_titel_ueberschreibt_die_knoepfe_nicht():
    # renderTeamspeak setzt den Titel per innerHTML neu -- die Pfeile müssen daneben stehen.
    m = re.search(r'<span class="lk-titel" id="ts-panel-title">', INDEX)
    assert m


def test_aufklappen_zeichnet_die_live_liste_nach():
    # renderLiveTable zeichnet nur sichtbare Container; zugeklappt verpasste sie die Updates.
    assert "_liveZeichnen()" in _funktion("_lkUmschalten")


def test_merker_ueber_den_vorhandenen_speicher_und_nach_der_serverantwort():
    assert "_prefSchreib(_LK_KEY" in INDEX
    assert re.search(r"_prefsPromise\.then\(function \(\) \{\s*_lkAnwenden\(\);", INDEX)


def test_readme_beschreibt_es():
    assert "einklappen" in README and "Pfeil" in README


# --- Höhe der Kästen (04.10.2026) ---

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
