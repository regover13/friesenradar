"""Der Admin laedt seine Listen bei jedem Klick neu (Nutzer, 27.09.2026).

Am Reddung-Abend fehlte der Knopf „Aufnahme freigeben": Die Liste war vor der Aufnahme
geladen, und jeder Klick auf „Events" oder „Reddung" schaltete nur um -- `_geladen` hatte
sich gemerkt, dass schon einmal geladen war. Nur ein Neuladen des Browsers haette geholfen.

Ausgenommen sind Bereiche, deren Lader Eingabefelder fuellen oder Handler anhaengen
(Betrieb, Mitteilungen): Dort kostete ein Neuladen halb getippte Eingaben.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ADMIN = (Path(__file__).resolve().parents[1] / "app" / "static" / "admin.html").read_text(encoding="utf-8")
_NODE = shutil.which("node")


def _funktion(name: str) -> str:
    m = re.search(rf"^    (async )?function {re.escape(name)}\(", _ADMIN, flags=re.M)
    assert m, f"function {name} fehlt"
    return _ADMIN[m.start():_ADMIN.index("\n    }\n", m.start()) + 7]


def test_ein_event_typ_laedt_bei_jedem_oeffnen():
    typ = _funktion("typOeffnen")
    assert "_geladen" not in typ
    assert "_typLader(typ)" in typ


def test_nur_bereiche_mit_formularen_laden_einmal():
    m = re.search(r"const _EINMAL_LADEN = new Set\(\[([^\]]*)\]\)", _ADMIN)
    assert m
    assert sorted(re.findall(r"'(\w+)'", m.group(1))) == ["betrieb", "mitteilungen"]
    tab = _funktion("tabOeffnen")
    assert "_EINMAL_LADEN.has(tab)" in tab


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_die_reddung_liste_frischt_sich_nur_auf_wenn_es_etwas_zu_sehen_gibt():
    js = """
      let geladen = 0; function loadReddung() { geladen++; }
      let _tabAktiv, _typAktiv, _rdEvents; const document = {hidden: false};
      const jetzt = Date.parse('2026-09-27T18:50:00Z'); Date.now = () => jetzt;
    """ + _funktion("_rdLaeuft") + _funktion("_rdLaeuftEines") + _funktion("_rdTaktSchritt") + """
      const laeuft = [{dtstart: '2026-09-27T17:50:00Z', dtend: '2026-09-27T20:00:00Z'}];
      const vorbei = [{dtstart: '2026-09-26T17:50:00Z', dtend: '2026-09-26T20:00:00Z'}];
      const faelle = [
        ['events', 'reddung', laeuft, false],   // offen, laeuft -> auffrischen
        ['events', 'reddung', vorbei, false],   // nichts laeuft
        ['events', 'kutter', laeuft, false],    // andere Ansicht
        ['bruegge', 'reddung', laeuft, false],  // anderer Bereich
        ['events', 'reddung', laeuft, true],    // Tab im Hintergrund
      ];
      const out = faelle.map(([tab, typ, ev, versteckt]) => {
        _tabAktiv = tab; _typAktiv = typ; _rdEvents = ev; document.hidden = versteckt;
        const vorher = geladen; _rdTaktSchritt(); return geladen - vorher;
      });
      console.log(JSON.stringify(out));
    """
    erg = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert erg.returncode == 0, erg.stderr
    assert json.loads(erg.stdout.strip().splitlines()[-1]) == [1, 0, 0, 0, 0]


def test_der_takt_laeuft_alle_dreissig_sekunden():
    assert re.search(r"setInterval\(_rdTaktSchritt, 30000\)", _ADMIN)
