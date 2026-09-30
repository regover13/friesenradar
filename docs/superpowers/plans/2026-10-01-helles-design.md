# Helles Design – Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FriesenSpy (Website und Kniebrett) bekommt ein umschaltbares helles Design in den
Forumsfarben; das Zahnrad ersetzt auf der Website die Glocke, der Schalter steht im Menü
„Einstellungen"; das dunkle Design bleibt nachweislich unverändert.

**Architecture:** Farben werden in `app/static/index.html` zu CSS-Variablen, deren dunkle Werte
exakt die bisherigen Literale sind; ein Block `html.hell { … }` überschreibt sie. Die Wahl ist
der Merker `friesenspy_theme` im vorhandenen Pref-System (`_prefLies`/`_prefSchreib`,
`/api/prefs`). Ein Vergleichswerkzeug belegt nach jedem Umbauschritt, dass das dunkle CSS nach
Einsetzen der Variablen Regel für Regel dem Ausgangsstand entspricht.

**Tech Stack:** Einzeldatei-Frontend (HTML/CSS/Vanilla-JS, ES2019 wegen Coherent GT/Chrome 49),
Leaflet, Chart.js, FastAPI-Backend (unverändert), pytest + node-Harness für JS-Ausschnitte,
Playwright/Chromium nur für Screenshots.

**Spec:** `docs/superpowers/specs/2026-10-01-helles-design-design.md`

## Global Constraints

- **Dunkles Design unverändert:** Jede Variable trägt im dunklen Design exakt den Wert, der vorher an der Stelle stand. Keine Vereinheitlichung ähnlicher Töne, keine zusammengelegten Transparenzstufen.
- **Abweichung von der Spec („Nebenbei repariert"):** Die undefinierten Variablen `--text-dim`, `--text`, `--color-label` werden **nicht** definiert — heute fällt die Eigenschaft dort auf den geerbten Wert zurück; eine Definition änderte das dunkle Design (Regel oben geht vor). `var(--blue, #2d9cdb)` wird zu `var(--green)` (identischer dunkler Wert).
- Helle Palette ausschließlich aus der Spec-Tabelle (Forumsfarben); Friesenrot `#D31141` in beiden Designs; nie Friesenrot direkt auf `#9FC7F8`.
- Fest bleiben: alles, was die Karte zeichnet (Linien, Marker, Platzrunden, Kutter, Reddung, Kompass), Tempo-/Höhenschilder, Emoji/Bilder.
- Kein `?.`/`??`, keine Checkbox, kein per `innerHTML` eingesetztes `<svg>` (Coherent GT).
- Merker: Schlüssel `friesenspy_theme`, Werte `dunkel` | `hell`, alles andere = `dunkel`.
- Nur `app/static/index.html` wird umgefärbt; `admin.html`, `efb.html`, Rechtstexte, Widget, Server-HTML bleiben.
- Version **15.32.0** (Nebenversion), CHANGELOG `"highlight": false`.
- Keine Datei anfassen, solange eine Test-Suite läuft (CLAUDE.md, „Tests").
- Tests: `/home/claude/.venv-friesenspy/bin/python -m pytest -n 4 tests/` (rund 1 min).
- Deploy = Push auf `main` (außer `docs/**`, `**.md`). Vor jedem Push, der Code enthält, beim Nutzer nachfragen, ob gerade geflogen wird (nginx-Log `/panel`, `/api/live`).
- Basis für den Dunkel-Vergleich: Commit **`18f0c15`** (letzter Stand vor dem Umbau).

## Review Focus

1. **Cookie `fs_karte` beschädigt oder ohne `friesenspy_theme`** → Seite startet dunkel, kein Skriptfehler im Kopfskript (Test in Task 2).
2. **Umschalten, bevor der Server geantwortet hat** (Kniebrett) → die Wahl darf von der späten Serverantwort nicht still zurückgedreht werden, solange der Server nichts anderes gespeichert hat; spätere Antwort mit gespeichertem Wert gewinnt wie bei allen Merkern (Test in Task 2).
3. **Statistik offen beim Umschalten** → Diagramm wird in den neuen Farben neu gezeichnet, nicht erst beim nächsten Datenabruf (Test in Task 6).
4. **Website ohne VAPID-Schlüssel** → Zahnrad sichtbar, Menü zeigt „Anzeige", der Abschnitt „Benachrichtigungen" fehlt (Test in Task 3).
5. **Kniebrett zeigt „Anzeige" nur einmal** → Design, Größe, Kartenhelligkeit unter einer Überschrift, nicht zwei Überschriften „Anzeige" (Test in Task 3).

---

### Task 1: Vergleichswerkzeug „Dunkel unverändert"

Ein Skript, kein dauerhafter Test: Es vergleicht gegen einen festen Ausgangsstand und würde
jede künftige, gewollte CSS-Änderung als Fehler melden. Es wird in diesem Plan nach jedem
Umbauschritt ausgeführt; seine eigene Logik sichert ein kleiner Test ab.

**Files:**
- Create: `scripts/dunkel_vergleich.py`
- Test: `tests/test_dunkel_vergleich.py`

**Interfaces:**
- Produces: `vergleiche(alt_html: str, neu_html: str) -> dict` mit Schlüsseln `geaendert: list[str]`, `entfernt: list[str]`, `neu: list[str]`; CLI `python -m scripts.dunkel_vergleich [--basis 18f0c15]` (Exit 1 bei `geaendert` oder `entfernt`).

- [ ] **Step 1: Failing test schreiben**

```python
"""Das Werkzeug, das "dunkles Design unveraendert" belegt (Spec helles Design, Schritt 3)."""
from scripts.dunkel_vergleich import vergleiche


def _seite(css):
    return "<html><head><style>\n" + css + "\n</style></head><body></body></html>"


ALT = _seite("""
:root { --bg: #04080f; }
.a { color: #2d9cdb; border: 1px solid rgba(45,156,219,0.15); }
.b { background: var(--bg); }
""")


def test_reine_umbenennung_ist_gleich():
    neu = _seite("""
:root { --bg: #04080f; --green: #2d9cdb; --green-rgb: 45,156,219; }
html.hell { --bg: #9FC7F8; --green: #105289; --green-rgb: 16,82,137; }
.a { color: var(--green); border: 1px solid rgba(var(--green-rgb), 0.15); }
.b { background: var(--bg); }
""")
    e = vergleiche(ALT, neu)
    assert e["geaendert"] == [] and e["entfernt"] == []


def test_geaenderte_deckkraft_faellt_auf():
    neu = _seite("""
:root { --bg: #04080f; --green-rgb: 45,156,219; }
.a { color: #2d9cdb; border: 1px solid rgba(var(--green-rgb),0.12); }
.b { background: var(--bg); }
""")
    assert vergleiche(ALT, neu)["geaendert"] == [".a"]


def test_falscher_dunkler_variablenwert_faellt_auf():
    neu = _seite("""
:root { --bg: #04080f; --green: #2e9cdb; }
.a { color: var(--green); border: 1px solid rgba(45,156,219,0.15); }
.b { background: var(--bg); }
""")
    assert vergleiche(ALT, neu)["geaendert"] == [".a"]


def test_neue_regeln_und_hell_bloecke_sind_erlaubt():
    neu = _seite("""
:root { --bg: #04080f; }
.a { color: #2d9cdb; border: 1px solid rgba(45,156,219,0.15); }
.b { background: var(--bg); }
.design-knopf { color: red; }
html.hell .a { color: blue; }
""")
    e = vergleiche(ALT, neu)
    assert e["geaendert"] == [] and e["entfernt"] == []
    assert e["neu"] == [".design-knopf"]


def test_entfernte_regel_faellt_auf():
    neu = _seite(":root { --bg: #04080f; }\n.b { background: var(--bg); }")
    assert vergleiche(ALT, neu)["entfernt"] == [".a"]


def test_undefinierte_variable_bleibt_undefiniert():
    # --text-dim ist heute nirgends definiert. Wer sie definiert, aendert das Dunkle.
    alt = _seite(":root { --bg: #04080f; }\n.x { color: var(--text-dim); }")
    neu = _seite(":root { --bg: #04080f; --text-dim: #6b9ab8; }\n.x { color: var(--text-dim); }")
    assert vergleiche(alt, neu)["geaendert"] == [".x"]


def test_hex_schreibweise_und_leerzeichen_sind_egal():
    alt = _seite(".a { color: #2D9CDB; border: 1px solid rgba(45, 156, 219, 0.15); }")
    neu = _seite(":root { --g: #2d9cdb; }\n.a { color: var(--g); border: 1px solid rgba(45,156,219,0.15); }")
    assert vergleiche(alt, neu)["geaendert"] == []
```

- [ ] **Step 2: Test laufen lassen, muss scheitern**

Run: `cd ~/projects/friesenspy && /home/claude/.venv-friesenspy/bin/python -m pytest tests/test_dunkel_vergleich.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'scripts.dunkel_vergleich'`

- [ ] **Step 3: Implementieren**

```python
"""Belegt, dass das dunkle Design nach dem Variablen-Umbau unveraendert ist.

Nimmt den <style>-Block von index.html im Ausgangsstand (git) und im Arbeitsstand, setzt in
BEIDEN jedes var(--x) mit dem Wert aus :root ein (html.hell-Bloecke werden verworfen) und
vergleicht Selektor fuer Selektor die Deklarationen. Erlaubt ist nur Hinzukommendes.

Aufruf:  python -m scripts.dunkel_vergleich [--basis 18f0c15]
Spec:    docs/superpowers/specs/2026-10-01-helles-design-design.md, Schritt 3
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DATEI = "app/static/index.html"

_KOMMENTAR = re.compile(r"/\*.*?\*/", re.S)
_VAR = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*(?:\([^()]*\)[^()]*)*))?\)")


def _css(html: str) -> str:
    teile = re.findall(r"<style[^>]*>(.*?)</style>", html, re.S)
    return _KOMMENTAR.sub("", "\n".join(teile))


def _bloecke(css: str):
    """Flache Liste (kontext, selektor, rumpf); @media-Klammern werden als Kontext mitgefuehrt."""
    aus, kontext, i = [], [], 0
    while i < len(css):
        auf = css.find("{", i)
        zu = css.find("}", i)
        if zu == -1:
            break
        if auf != -1 and auf < zu:
            kopf = " ".join(css[i:auf].split())
            ende = css.find("}", auf)
            naechstes_auf = css.find("{", auf + 1)
            if kopf.startswith("@") and naechstes_auf != -1 and naechstes_auf < ende:
                kontext.append(kopf)
                i = auf + 1
                continue
            aus.append((" | ".join(kontext), kopf, css[auf + 1:ende]))
            i = ende + 1
        else:
            if kontext:
                kontext.pop()
            i = zu + 1
    return aus


def _deklarationen(rumpf: str) -> list[tuple[str, str]]:
    out = []
    for teil in rumpf.split(";"):
        if ":" not in teil:
            continue
        name, wert = teil.split(":", 1)
        out.append((name.strip().lower(), " ".join(wert.split())))
    return out


def _ist_hell(selektor: str) -> bool:
    return "html.hell" in selektor or ".hell " in selektor


def _variablen(bloecke) -> dict[str, str]:
    v: dict[str, str] = {}
    for kontext, sel, rumpf in bloecke:
        if sel.strip() == ":root" and not kontext:
            for n, w in _deklarationen(rumpf):
                if n.startswith("--"):
                    v[n] = w
    return v


def _einsetzen(wert: str, var: dict[str, str], tiefe: int = 0) -> str:
    if tiefe > 10:
        return wert

    def ersatz(m):
        name, rueckfall = m.group(1), m.group(2)
        if name in var:
            return _einsetzen(var[name], var, tiefe + 1)
        if rueckfall is not None:
            return _einsetzen(rueckfall.strip(), var, tiefe + 1)
        return "<UNDEFINIERT>"

    return _VAR.sub(ersatz, wert)


def _norm(wert: str) -> str:
    wert = re.sub(r"\s*,\s*", ",", wert)
    wert = re.sub(r"\(\s*", "(", wert)
    wert = re.sub(r"\s*\)", ")", wert)
    return re.sub(r"#[0-9a-fA-F]{3,8}\b", lambda m: m.group(0).lower(), wert)


def _aufgeloest(html: str) -> dict[str, list[tuple[str, str]]]:
    bloecke = _bloecke(_css(html))
    var = _variablen(bloecke)
    regeln: dict[str, list[tuple[str, str]]] = {}
    for kontext, sel, rumpf in bloecke:
        if _ist_hell(sel) or kontext.startswith("@keyframes") or sel.startswith("@"):
            continue
        dekl = [(n, _norm(_einsetzen(w, var))) for n, w in _deklarationen(rumpf)
                if not n.startswith("--")]
        schluessel = (kontext + " || " if kontext else "") + sel
        regeln.setdefault(schluessel, []).extend(dekl)
    return regeln


def vergleiche(alt_html: str, neu_html: str) -> dict:
    alt, neu = _aufgeloest(alt_html), _aufgeloest(neu_html)
    return {
        "geaendert": [s for s in alt if s in neu and alt[s] != neu[s]],
        "entfernt": [s for s in alt if s not in neu],
        "neu": [s for s in neu if s not in alt],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--basis", default="18f0c15")
    a = ap.parse_args()
    alt = subprocess.run(["git", "show", f"{a.basis}:{DATEI}"], capture_output=True,
                         text=True, check=True).stdout
    neu = Path(DATEI).read_text(encoding="utf-8")
    e = vergleiche(alt, neu)
    for art in ("geaendert", "entfernt", "neu"):
        print(f"{art}: {len(e[art])}")
        for s in e[art]:
            print("   ", s)
    return 1 if (e["geaendert"] or e["entfernt"]) else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Tests grün**

Run: `/home/claude/.venv-friesenspy/bin/python -m pytest tests/test_dunkel_vergleich.py -v` → 7 passed.
Dann gegen den echten Stand: `cd ~/projects/friesenspy && /home/claude/.venv-friesenspy/bin/python -m scripts.dunkel_vergleich` → `geaendert: 0`, `entfernt: 0`, `neu: 0`, Exit 0. Liefert es hier schon Abweichungen, ist der Parser falsch (doppelte Selektoren, `@media`) — erst reparieren, dann weiter.

- [ ] **Step 5: Gegenprobe** — in einer Kopie von `index.html` einen Wert `rgba(45,156,219,0.3)` auf `0.31` ändern, Skript per `vergleiche()` darauf laufen lassen: muss den Selektor unter `geaendert` nennen. Kopie verwerfen.

- [ ] **Step 6: Commit**

```bash
git add scripts/dunkel_vergleich.py tests/test_dunkel_vergleich.py
git commit -m "Werkzeug: Dunkel-Vergleich fuer den Variablen-Umbau (helles Design)"
```

---

### Task 2: Design-Merker und Umschalt-Mechanik

**Files:**
- Modify: `app/static/index.html` — Kopfskript (Z. 5–14, direkt hinter dem `vr-panel`-Setzen), Pref-Abschnitt (hinter `_prefVomServerHolen`, ~Z. 5335), Startcode (`_prefsPromise`, ~Z. 16520), `<meta name="theme-color">` (Z. 662)
- Test: `tests/test_design_merker.py`

**Interfaces:**
- Consumes: `_prefLies(key)`, `_prefSchreib(key, wert)`, `_prefsPromise`
- Produces: `const _DESIGN_KEY = 'friesenspy_theme'`; `function _designNormal(wert) -> 'dunkel'|'hell'`; `function _designAnwenden(wert)` (setzt/entfernt `html.hell`, setzt `theme-color`, ruft `_designGeaendert()`-Haken); `function _designSetzen(wert)` (normalisieren, `_prefSchreib`, anwenden); `let _designBeruehrt = false`; `const _DESIGN_META = { dunkel: '#04080f', hell: '#9FC7F8' }`; Haken-Liste `const _designHaken = []` — spätere Tasks hängen `function () {…}` an.

- [ ] **Step 1: Failing tests** (node-Harness nach dem Muster von `tests/test_karte_merker.py`: Cookie-Glas, `fetch`-Attrappe, `localStorage`-Attrappe)

```python
"""Design-Merker friesenspy_theme (helles Design, Spec 2026-10-01)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")
_NODE = shutil.which("node")
ohne_node = pytest.mark.skipif(not _NODE, reason="node fehlt")


def _kopfskript():
    start = INDEX.index("<script>") + len("<script>")
    return INDEX[start:INDEX.index("</script>", start)]


def _ausschnitt(anfang, ende_marke):
    a = INDEX.index(anfang)
    e = INDEX.index(ende_marke, a)
    return INDEX[a:INDEX.index("\n}", e) + 2]


def _lauf(js):
    r = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


_DOC = """
const klassen = new Set();
global.document = {
  cookie: %s,
  documentElement: { classList: {
    add: (k) => klassen.add(k), remove: (k) => klassen.delete(k),
    contains: (k) => klassen.has(k), toggle: (k, an) => an ? klassen.add(k) : klassen.delete(k) },
    style: {} },
  querySelector: () => null, getElementById: () => null, querySelectorAll: () => [],
};
global.location = { pathname: '/', search: '' };
global.URLSearchParams = URLSearchParams;
global.window = global; global.matchMedia = () => ({ matches: false });
"""


@ohne_node
@pytest.mark.parametrize("cookie,erwartet", [
    ("'fs_karte=' + encodeURIComponent(JSON.stringify({friesenspy_theme: 'hell'}))", True),
    ("'fs_karte=' + encodeURIComponent(JSON.stringify({friesenspy_theme: 'dunkel'}))", False),
    ("'fs_karte=%7Bkaputt'", False),
    ("''", False),
    ("'fs_karte=' + encodeURIComponent(JSON.stringify({friesenspy_theme: 'lila'}))", False),
])
def test_kopfskript_setzt_hell_vor_dem_ersten_zeichnen(cookie, erwartet):
    js = _DOC % cookie + _kopfskript() + "\nconsole.log(JSON.stringify(klassen.has('hell')));"
    assert _lauf(js) is erwartet


def test_merker_schluessel_und_werte():
    assert "const _DESIGN_KEY = 'friesenspy_theme';" in INDEX
    assert "function _designNormal(" in INDEX
    assert "function _designSetzen(" in INDEX
    assert "function _designAnwenden(" in INDEX


@ohne_node
def test_normalisierung():
    js = _ausschnitt("function _designNormal(", "function _designNormal(") + """
console.log(JSON.stringify([_designNormal('hell'), _designNormal('dunkel'), _designNormal(null),
                            _designNormal('HELL'), _designNormal('x')]));"""
    assert _lauf(js) == ["hell", "dunkel", "dunkel", "dunkel", "dunkel"]


def test_serverantwort_ueberstimmt_eine_beruehrte_wahl_nicht():
    # Review Focus 2: Wer vor der Serverantwort umschaltet, behaelt seine Wahl.
    m = re.search(r"_prefsPromise\.then\(function \(\) \{\s*if \(!_designBeruehrt\) _designAnwenden\(_prefLies\(_DESIGN_KEY\)\);", INDEX)
    assert m, "Nach der Serverantwort nur anwenden, wenn niemand selbst umgeschaltet hat"
    assert "_designBeruehrt = true;" in _ausschnitt("function _designSetzen(", "function _designSetzen(")


def test_theme_color_folgt_dem_design():
    assert "const _DESIGN_META = { dunkel: '#04080f', hell: '#9FC7F8' };" in INDEX
    assert 'name="theme-color" content="#04080f"' in INDEX  # Ausgangswert bleibt
```

- [ ] **Step 2: Laufen lassen, muss scheitern**

Run: `/home/claude/.venv-friesenspy/bin/python -m pytest tests/test_design_merker.py -v` → FAIL (Kopfskript setzt `hell` nie; Funktionen fehlen).

- [ ] **Step 3: Kopfskript** — direkt hinter `document.documentElement.classList.add('vr-panel'); }` (Z. 13–14) einfügen:

```js
      // HELLES DESIGN (Spec 2026-10-01): VOR dem <style>-Block, sonst blitzt auf der Website
      // beim Laden das dunkle Design auf. Liest dasselbe Merker-Cookie wie _prefLies weiter
      // unten (fs_karte, JSON). Im Kniebrett ist das Cookie nach einem Sim-Neustart leer --
      // dort setzt erst die Serverantwort den Wert (bewusst in Kauf genommen, Spec Punkt 4).
      try {
        var teile = String(document.cookie || '').split('; ');
        for (var ti = 0; ti < teile.length; ti++) {
          if (teile[ti].indexOf('fs_karte=') !== 0) continue;
          var merker = JSON.parse(decodeURIComponent(teile[ti].slice(9)));
          if (merker && merker.friesenspy_theme === 'hell') {
            document.documentElement.classList.add('hell');
          }
        }
      } catch (e) {}
```

- [ ] **Step 4: Pref-Abschnitt** — hinter dem Ende von `_prefVomServerHolen()` einfügen:

```js
// ===================================================================
//  HELLES DESIGN (Spec docs/superpowers/specs/2026-10-01-helles-design-design.md)
// ===================================================================
// Getrennt je Kontext gespeichert (web/panel), wie jeder Merker. Standard ist Dunkel; nur
// der exakte Wert 'hell' schaltet um -- ein kaputter Merker darf nie zu einer halb hellen
// Seite fuehren.
const _DESIGN_KEY = 'friesenspy_theme';
const _DESIGN_META = { dunkel: '#04080f', hell: '#9FC7F8' };
const _designHaken = [];      // Wer beim Umschalten neu zeichnen muss (Statistik, Schalter)
let _designBeruehrt = false;  // Hat der Nutzer in dieser Sitzung selbst umgeschaltet?

function _designNormal(wert) {
  return wert === 'hell' ? 'hell' : 'dunkel';
}

function _designAnwenden(wert) {
  const d = _designNormal(wert);
  document.documentElement.classList.toggle('hell', d === 'hell');
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', _DESIGN_META[d]);
  for (let i = 0; i < _designHaken.length; i++) {
    try { _designHaken[i](d); } catch (e) {}
  }
}

function _designSetzen(wert) {
  _designBeruehrt = true;
  const d = _designNormal(wert);
  _prefSchreib(_DESIGN_KEY, d);
  _designAnwenden(d);
}
```

- [ ] **Step 5: Startcode** — direkt hinter der Zeile `const _prefsPromise = _prefVomServerHolen().then(…).catch(() => {});` (~Z. 16531):

```js
// Das Kopfskript hat auf der Website schon aus dem Cookie gemalt; hier gewinnt der Server
// (wie bei allen Merkern) -- ausser der Nutzer hat vor der Antwort selbst umgeschaltet.
_prefsPromise.then(function () {
  if (!_designBeruehrt) _designAnwenden(_prefLies(_DESIGN_KEY));
}).catch(() => {});
```

- [ ] **Step 6: Tests grün**

Run: `/home/claude/.venv-friesenspy/bin/python -m pytest tests/test_design_merker.py tests/test_karte_merker.py -v` → alle grün. Dann `python -m scripts.dunkel_vergleich` → Exit 0 (kein CSS geändert).

- [ ] **Step 7: Commit**

```bash
git add app/static/index.html tests/test_design_merker.py
git commit -m "Helles Design: Merker friesenspy_theme und Umschalt-Mechanik"
```

---

### Task 3: Einstellungsmenü — Zahnrad auf der Website, Design-Schalter

**Files:**
- Modify: `app/static/index.html` — Knopf Z. 4286, Menü-Markup Z. 4297–4340, CSS Z. 748–773 (Symbole) und bei `.panel-zoom-*` (Schalter-Stil), `_initPanelAnzeige` (~Z. 16785), `_configPromise` (~Z. 16510), DOMContentLoaded-Block (~Z. 8400)
- Modify: `tests/test_vr_panel.py:928-929` (Twemoji-Glocke entfällt), `:3500-3506`
- Test: `tests/test_einstellungsmenue.py`

**Interfaces:**
- Consumes: `_designSetzen`, `_designAnwenden`, `_designHaken`, `_prefLies`, `_DESIGN_KEY`
- Produces: Markup `#einst-design` mit Knöpfen `#design-dunkel`, `#design-hell` (Klasse `design-knopf`, aktiver Knopf zusätzlich `an`); `#notif-web-titel` (Überschrift „Benachrichtigungen", Website); Klasse `mit-push` an `#notif-panel`, wenn VAPID gesetzt; `function _designSchalterAnzeigen(d)`.

- [ ] **Step 1: Failing tests**

```python
"""Einstellungsmenue: Zahnrad ueberall, Design-Schalter (Spec helles Design)."""
import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _knopf():
    return re.search(r'<button id="notif-btn"[^>]*>', INDEX).group(0)


def test_zahnrad_auf_der_website_statt_glocke():
    assert "notif-glocke-web" not in INDEX
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
    assert re.search(r"\.notif-panel:not\(\.mit-push\) #notif-web-titel", INDEX)
    assert "classList.add('mit-push')" in INDEX
    assert "html.vr-panel #notif-web-titel" in INDEX


def test_schalter_folgt_dem_design():
    assert "_designHaken.push(_designSchalterAnzeigen);" in INDEX
    assert "_designSetzen('hell')" in INDEX and "_designSetzen('dunkel')" in INDEX
```

- [ ] **Step 2: Laufen lassen, muss scheitern** — `pytest tests/test_einstellungsmenue.py -v` → FAIL.

- [ ] **Step 3: Knopf** (Z. 4286): `title="Benachrichtigungen" hidden` → `title="Einstellungen"`; das `<img class="emoji-icon notif-glocke-web" … />` entfernen. Die beiden `<svg>` bleiben unverändert.

- [ ] **Step 4: Symbol-CSS** (Z. 759–773): Die Regel `html.vr-panel .notif-zahnrad-panel { display: inline-block; fill: currentColor; fill-rule: evenodd; }` wird zu `.notif-zahnrad-panel { … }` ohne `html.vr-panel`, nach der Zeile `.notif-glocke-panel, .notif-zahnrad-panel { display: none; }`; die Zeile `html.vr-panel .notif-glocke-web { display: none; }` entfällt. Kommentar darüber um einen Satz ergänzen: „Seit 15.32.0 auch auf der Website: das Menü enthält dort das Design."
  Achtung Dunkel-Vergleich: Das ändert den Selektor → erscheint als `entfernt`/`neu`. Das ist die gewollte sichtbare Änderung; im Vergleichslauf von Task 3 genau diese zwei Selektoren (`html.vr-panel .notif-zahnrad-panel`, `html.vr-panel .notif-glocke-web`) als erwartet notieren und sonst nichts.

- [ ] **Step 5: Menü-Markup** — Z. 4298 `Benachrichtigungen` → `Einstellungen`. Direkt vor `<div id="panel-anzeige" hidden>` einfügen:

```html
    <!-- DESIGN (Spec 2026-10-01): auf Website UND im Kniebrett. Knoepfe statt Checkbox
         (Coherent GT zeigt deren Zustand nicht). Die Ueberschrift "Anzeige" steht nur hier;
         im Kniebrett folgen darunter Groesse und Kartenhelligkeit aus #panel-anzeige. -->
    <div id="einst-design">
      <div class="panel-abschnitt-titel">Anzeige</div>
      <div class="panel-einst-name">Design</div>
      <div class="panel-zoom-reihe">
        <button type="button" class="design-knopf" id="design-dunkel">Dunkel</button>
        <button type="button" class="design-knopf" id="design-hell">Hell</button>
      </div>
    </div>
```

  In `#panel-anzeige` die Zeile `<div class="panel-abschnitt-titel">Anzeige</div>` entfernen. Direkt vor dem ersten Web-Push-Element (`#notif-enabled-row`) einfügen:
  `<div class="panel-abschnitt-titel" id="notif-web-titel">Benachrichtigungen</div>`

- [ ] **Step 6: CSS** — neben den `.panel-zoom-*`-Regeln:

```css
    /* Design-Schalter: zwei Knoepfe, der aktive gefuellt. Farben ueber Variablen, damit er in
       beiden Designs stimmt. */
    .design-knopf {
      background: none;
      border: 1px solid var(--green-dim);
      color: var(--text-label);
      font-family: var(--text-mono);
      padding: 4px 12px;
      cursor: pointer;
    }
    .design-knopf.an {
      background: var(--green);
      border-color: var(--green);
      color: var(--bg-panel);
    }
    .notif-panel:not(.mit-push) #notif-web-titel,
    .notif-panel:not(.mit-push) #notif-enabled-row,
    .notif-panel:not(.mit-push) #notif-filter,
    .notif-panel:not(.mit-push) #notif-install-btn,
    .notif-panel:not(.mit-push) #notif-reset-btn { display: none !important; }
    html.vr-panel #notif-web-titel { display: none !important; }
```

  Und die bestehende Regel `html:not(.vr-panel) #panel-anzeige { display: none !important; }` bleibt.

- [ ] **Step 7: JS** — in `_configPromise` (~Z. 16510) `document.getElementById('notif-btn').hidden = false;` ersetzen durch `document.getElementById('notif-panel').classList.add('mit-push');`. In `_initPanelAnzeige` die beiden Zeilen, die den Titel auf „Einstellungen" setzen, entfernen (steht jetzt fest im Markup). Im DOMContentLoaded-Block (~Z. 8400) nach `const installBtn = …` ergänzen:

```js
  // Design-Schalter (Website und Kniebrett, s. #einst-design)
  _on(document.getElementById('design-dunkel'), 'click', () => _designSetzen('dunkel'));
  _on(document.getElementById('design-hell'),   'click', () => _designSetzen('hell'));
  _designSchalterAnzeigen(_designNormal(_prefLies(_DESIGN_KEY)));
```

  Und im Design-Abschnitt aus Task 2 anfügen:

```js
function _designSchalterAnzeigen(d) {
  const dk = document.getElementById('design-dunkel');
  const hl = document.getElementById('design-hell');
  if (dk) dk.classList.toggle('an', d !== 'hell');
  if (hl) hl.classList.toggle('an', d === 'hell');
}
_designHaken.push(_designSchalterAnzeigen);
```

- [ ] **Step 8: Bestehende Tests anpassen** — `tests/test_vr_panel.py:928-929`: die beiden Asserts auf `notif-glocke-web` ersetzen durch `assert "notif-glocke-web" not in INDEX` mit Kommentar „Seit 15.32.0 Zahnrad auch auf der Website (helles Design)"; Z. 934 `html\.vr-panel \.notif-zahnrad-panel` → `\.notif-zahnrad-panel`. `test_die_einstellungsansicht_traegt_beide_themen` (Z. ~3500): `"titel.textContent = 'Einstellungen';"` → `'<div class="notif-panel-title">Einstellungen</div>'`. Übrige Fehlschläge der Suite lesen, nicht blind anpassen.

- [ ] **Step 9: Tests grün** — `pytest -n 4 tests/` komplett; `python -m scripts.dunkel_vergleich` → `geaendert: 0`, `entfernt:` nur die zwei in Step 4 genannten, `neu:` Schalter- und Zahnrad-Selektoren.

- [ ] **Step 10: Commit**

```bash
git add app/static/index.html tests/test_einstellungsmenue.py tests/test_vr_panel.py
git commit -m "Einstellungsmenue: Zahnrad auf der Website, Design-Schalter"
```

---

### Task 4: Palette und Hauptflächen, Kontrasttest — dann Probe beim Nutzer

**Files:**
- Modify: `app/static/index.html` — `:root` (Z. 775–792), neuer Block `html.hell { … }` direkt dahinter, CSS der Hauptflächen: `body`, `header`, Tab-Leiste, `.notif-panel`, Pilotenliste/Seitenleiste, `.leaflet-popup-*` (~Z. 2618ff.), `.leaflet-control-layers*`
- Test: `tests/test_design_kontrast.py`
- Create (außerhalb des Repos): `/home/claude/arbeit/helles-design/screenshots.py`

**Interfaces:**
- Produces: Variablen `--green-rgb`, `--schleier-rgb`, `--schatten-rgb` (neu) und der Block `html.hell`; jede spätere CSS-Stelle benutzt nur diese Namen plus die vorhandenen.

- [ ] **Step 1: Failing Kontrasttest**

```python
"""Kontrast der Textfarben in beiden Designs (Spec helles Design, Schritt 4)."""
import re
from pathlib import Path

import pytest

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _block(selektor):
    m = re.search(re.escape(selektor) + r"\s*\{(.*?)\}", INDEX, re.S)
    assert m, selektor
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", m.group(1)))


def _lum(h):
    h = h.strip().lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _kontrast(a, b):
    x, y = sorted([_lum(a), _lum(b)], reverse=True)
    return (x + 0.05) / (y + 0.05)


DUNKEL = _block(":root")
HELL = {**DUNKEL, **_block("html.hell")}

TEXT = ("--text-bright", "--text-label", "--green", "--cyan", "--amber", "--red")
FLAECHEN = ("--bg-panel", "--bg-panel-2")


@pytest.mark.parametrize("text", TEXT)
@pytest.mark.parametrize("flaeche", FLAECHEN)
def test_hell_ist_lesbar(text, flaeche):
    assert _kontrast(HELL[text], HELL[flaeche]) >= 4.5, (text, flaeche)


def test_hell_palette_ist_die_des_forums():
    assert HELL["--bg-body"].upper() == "#9FC7F8"
    assert HELL["--bg-panel"].upper() == "#FBFBFB"
    assert HELL["--bg-panel-2"].upper() == "#F1F8FF"
    assert HELL["--text-bright"].upper() == "#2B3C5A"
    assert HELL["--text-label"].upper() == "#536482"
    assert HELL["--green"].upper() == "#105289"
    assert HELL["--cyan"].upper() == "#D31141"
    assert HELL["--green-rgb"].replace(" ", "") == "16,82,137"


def test_dunkle_werte_unveraendert():
    assert DUNKEL["--bg-body"] == "#04080f"
    assert DUNKEL["--green"] == "#2d9cdb"
    assert DUNKEL["--green-rgb"].replace(" ", "") == "45,156,219"
    assert DUNKEL["--schleier-rgb"].replace(" ", "") == "4,8,15"
    assert DUNKEL["--schatten-rgb"].replace(" ", "") == "0,0,0"
```

Hinweis: Im dunklen Design wird bewusst **nicht** auf 4,5:1 geprüft — es bleibt, wie es ist
(`--text-label #6b9ab8` auf `#071525` liegt bei rund 6:1, aber das ist nicht Gegenstand).

- [ ] **Step 2: Laufen lassen, muss scheitern** (`html.hell` fehlt).

- [ ] **Step 3: `:root` ergänzen** (nach `--text-label`):

```css
      /* Kanalwerte fuer rgba(var(--x-rgb), deckkraft): Die Deckkraft bleibt an jeder Stelle,
         wie sie war -- nur der Farbton wechselt mit dem Design (Spec helles Design). */
      --green-rgb:    45,156,219;
      --schleier-rgb: 4,8,15;
      --schatten-rgb: 0,0,0;
```

  Und direkt nach dem `:root`-Block:

```css
    /* HELLES DESIGN -- Farben des Forums (board.friesenflieger.de, Friesen.new/colours.css).
       Friesenrot bleibt; nie Friesenrot direkt auf --bg-body (3,1:1). */
    html.hell {
      --bg-body:      #9FC7F8;
      --bg-panel:     #FBFBFB;
      --bg-panel-2:   #F1F8FF;
      --green:        #105289;
      --green-rgb:    16,82,137;
      --green-dim:    rgba(16,82,137,0.3);
      --green-glow:   rgba(16,82,137,0.2);
      --green-faint:  rgba(16,82,137,0.08);
      --green-grid:   rgba(16,82,137,0.05);
      --cyan:         #D31141;
      --amber:        #8f5f00;
      --red:          #c62828;
      --text-bright:  #2B3C5A;
      --text-label:   #536482;
      --schleier-rgb: 251,251,251;
      --schatten-rgb: 43,60,90;
    }
```

- [ ] **Step 4: Hauptflächen umstellen.** Für jeden festen Farbwert in den genannten Regeln nach dieser Tabelle ersetzen (nur exakte Treffer, Deckkraft unverändert übernehmen):

| Literal im CSS | wird |
|---|---|
| `#04080f` | `var(--bg-body)` |
| `#071525` | `var(--bg-panel)` |
| `#091b30` | `var(--bg-panel-2)` |
| `#2d9cdb` | `var(--green)` |
| `#d4e8f5` | `var(--text-bright)` |
| `#6b9ab8` | `var(--text-label)` |
| `#D31141` | bleibt |
| `rgba(45,156,219,X)` | `rgba(var(--green-rgb),X)` |
| `rgba(4,8,15,X)` | `rgba(var(--schleier-rgb),X)` |
| `rgba(0,0,0,X)` in `box-shadow`/Schleiern | `rgba(var(--schatten-rgb),X)` |
| andere Werte | einzeln entscheiden: gehört er zu einer Fläche/Schrift der Oberfläche, neue Variable mit dunklem Wert = Literal, heller Wert aus der Forumspalette (`#CADCEB` für Rahmen); sonst fest lassen |

  Vorgehen je Regel: Selektor mit `grep -n` finden, Literal mit einer Ersetzung ändern, die vorher `assert s.count(alt) == 1` prüft (Memory: Trefferzahl prüfen). Keine Suchen-und-Ersetzen über die ganze Datei.

- [ ] **Step 5: Dunkel-Vergleich** — `python -m scripts.dunkel_vergleich` → `geaendert: 0`, `entfernt:` nur die zwei aus Task 3. Jede Abweichung ist ein Fehler dieser Task, nicht des Werkzeugs.

- [ ] **Step 6: Tests** — `pytest -n 4 tests/` komplett. Tests, die ein ersetztes Literal wörtlich erwarten (bekannt: `test_vr_panel.py` Z. 342, 915–917, 1286–1301, 2259–2261; `test_vrp.py` 381/413; `test_ground_chart_ui.py` 88; `test_aip_ui.py` 421; `test_mithoeren.py` 56; `test_pilot_links.py`): Assertion auf die Variablenform umstellen (z. B. `"background: var(--bg-panel) !important"`), nie löschen. Nur die tatsächlich roten anfassen.

- [ ] **Step 7: Screenshots vorbereiten** (einmalig)

```bash
/home/claude/.venv-friesenspy/bin/pip install playwright
/home/claude/.venv-friesenspy/bin/python -m playwright install chromium
```

  Fehlen Systembibliotheken (Fehlermeldung beim Start nennt sie), **anhalten und den Nutzer fragen**, bevor `playwright install-deps` per `sudo` apt-Pakete installiert.

  Daten: Kopie der Produktions-DB per `.backup` (nie `cp`, WAL) und Login in der Kopie aus:

```bash
mkdir -p /home/claude/arbeit/helles-design
sudo sqlite3 /opt/friesenspy/data/friesenspy.db ".backup /home/claude/arbeit/helles-design/probe.db"
sudo chown claude: /home/claude/arbeit/helles-design/probe.db
sqlite3 /home/claude/arbeit/helles-design/probe.db "UPDATE app_settings SET value='0' WHERE key='forum_login_enabled';"
```

  (Tabellen-/Spaltennamen von `app_settings` vorher mit `.schema app_settings` prüfen.) App lokal starten:

```bash
cd ~/projects/friesenspy && SECRET_KEY=probe DB_PATH=/home/claude/arbeit/helles-design/probe.db \
  /home/claude/.venv-friesenspy/bin/uvicorn app.main:app --port 8191
```

  (im Hintergrund; Fertig-Marke „Application startup complete" im Log abwarten, nicht per `pgrep` prüfen.) Kein Poller-Ärger: prüfen, ob die App beim Start externe Abrufe (VATSIM/IVAO) startet; falls ja, laufen lassen — die Kopie ist wegwerfbar.

  `/home/claude/arbeit/helles-design/screenshots.py`:

```python
"""Screenshots beider Designs, Website und Kniebrett-Modus (?vr=1)."""
import sys
from playwright.sync_api import sync_playwright

BASIS = "http://127.0.0.1:8191/"
ZIEL = "/home/claude/arbeit/helles-design/"
TABS = sys.argv[1:] or ["live"]

with sync_playwright() as p:
    b = p.chromium.launch()
    for modus, url, groesse in (("web", BASIS, (1400, 900)), ("panel", BASIS + "?vr=1", (900, 700))):
        for design in ("dunkel", "hell"):
            s = b.new_page(viewport={"width": groesse[0], "height": groesse[1]})
            s.goto(url)
            s.wait_for_timeout(2500)
            s.evaluate(f"_designSetzen('{design}')")
            for tab in TABS:
                s.evaluate(f"var t=document.querySelector('[data-tab=\"{tab}\"]'); if (t) t.click();")
                s.wait_for_timeout(1200)
                s.screenshot(path=f"{ZIEL}{modus}-{tab}-{design}.png")
            s.click("#notif-btn")
            s.wait_for_timeout(400)
            s.screenshot(path=f"{ZIEL}{modus}-menue-{design}.png")
            s.close()
    b.close()
```

  (Den Tab-Selektor vorher im Markup nachsehen und anpassen, falls die Tabs nicht `data-tab` tragen.)

- [ ] **Step 8: Probe an den Nutzer** — Screenshots zu einer HTML-Seite zusammenfügen (Bilder als `data:`-URI eingebettet, beide Designs nebeneinander), nach `files.friesenflieger.de/downloads/` legen (Skill `friesenflieger:friesenflieger-dateien`, URL mit 200 prüfen), Link nennen. Den Nutzer ausdrücklich bitten, nur das Helle zu beurteilen — das Dunkle ist per Werkzeug belegt.
  **STOPP: weiter erst nach seinem OK.** Danach die Datei löschen und 404 prüfen.

- [ ] **Step 9: Commit** (erst nach dem OK)

```bash
git add app/static/index.html tests/test_design_kontrast.py tests/
git commit -m "Helles Design: Palette und Hauptflaechen, Kontrasttest"
```

- [ ] **Step 10: Sim-Probe `var()` in `rgba()`** — Coherent GT ist Chrome 49; `rgba(var(--green-rgb),0.3)` muss dort greifen, bevor Task 5 rund 200 weitere Stellen darauf baut. Dafür braucht es einen Deploy: Nutzer fragen, ob geflogen wird; nach Freigabe `git push origin main`; Nutzer bitten, im Kniebrett auf „Hell" zu schalten und zu melden, ob Rahmen und Hover-Flächen blau getönt oder ganz ohne Farbe erscheinen. Dunkel ist davon unberührt (belegt). **Ohne Farbe = Plan anhalten** und Ausweg besprechen (je Deckkraft eine eigene Variable).

---

### Task 5: Übrige CSS-Farbwerte

**Files:**
- Modify: `app/static/index.html` CSS (Z. ~679–4054, rund 214 Literale abzüglich Task 4) und die 4 Farben in `style=`-Attributen im Markup (u. a. Z. 4265 `color:#fff`)
- Modify: betroffene Tests wie in Task 4 Step 6

- [ ] **Step 1: Bestand erzeugen**

```bash
cd ~/projects/friesenspy && sed -n '/<style>/,/<\/style>/p' app/static/index.html \
  | grep -nE '#[0-9a-fA-F]{3,8}\b|rgba?\(' | grep -v 'var(--' > /home/claude/arbeit/helles-design/bestand.txt
wc -l /home/claude/arbeit/helles-design/bestand.txt
```

- [ ] **Step 2: In Abschnitten von rund 500 CSS-Zeilen abarbeiten.** Je Abschnitt: jede Zeile aus dem Bestand nach der Tabelle aus Task 4 Step 4 ersetzen oder bewusst fest lassen. Fest bleiben: Selektoren der Karte (Leaflet-Pfade, Marker-Klassen, Platzrunden, Kutter, Reddung, Kompass), Tempo-/Höhenschilder, `--cyan`-Akzent, Warn-Einzelfarben in Chips, sofern sie auf `--bg-panel` stehen und in Hell ≥ 4,5:1 erreichen (sonst Variable mit dunklem Originalwert). Nach jedem Abschnitt:
  - `python -m scripts.dunkel_vergleich` → `geaendert: 0`
  - `pytest -n 4 tests/` → grün (rote Literal-Asserts auf Variablenform umstellen)
  - Commit `"Helles Design: CSS Zeilen A–B auf Variablen"`

- [ ] **Step 3: Undefinierte Variablen** — `var(--blue, #2d9cdb)` (3 Stellen) → `var(--green)`; `--text-dim`, `--text`, `--color-label` unangetastet lassen (Global Constraints). Dunkel-Vergleich muss grün bleiben.

- [ ] **Step 4: Rest zählen** — Bestand erneut erzeugen; jede verbliebene Zeile muss unter „fest bleiben" fallen. Liste der festen Stellen mit Grund als Kommentarblock oberhalb von `html.hell` festhalten (eine Zeile je Gruppe, nicht je Stelle).

- [ ] **Step 5: Screenshots aller Reiter** (Skript aus Task 4 mit allen Tab-Namen) in beiden Designs, selbst durchsehen: helle Flächen mit dunkler Schrift, nirgends dunkle Inseln (vergessene `#071525`) oder unlesbarer Text. Funde beheben, erneut Dunkel-Vergleich.

---

### Task 6: Farben im JavaScript (Statistik und Oberfläche außerhalb der Karte)

**Files:**
- Modify: `app/static/index.html` — `renderActivityChart` (~Z. 14524–14670), weitere JS-Farbstellen außerhalb der Karte
- Test: `tests/test_design_statistik.py`

**Interfaces:**
- Consumes: `_designHaken`
- Produces: `function _themaFarbe(name) -> string` (liest `getComputedStyle(document.documentElement).getPropertyValue(name).trim()`); `let _aktivitaetZuletzt = null` (`{data, grouping}`).

- [ ] **Step 1: Failing tests**

```python
"""Statistik-Diagramm folgt dem Design (Spec helles Design; Review Focus 3)."""
import re
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _chart():
    a = INDEX.index("function renderActivityChart(")
    return INDEX[a:INDEX.index("function renderStatsSummary(", a)]


def test_keine_festen_oberflaechenfarben_mehr():
    c = _chart()
    for alt in ("'#071525'", "'#6b9ab8'", "'#d4e8f5'", "rgba(45,156,219,0.05)", "rgba(45,156,219,0.07)"):
        assert alt not in c, alt
    assert "_themaFarbe('--bg-panel')" in c


def test_datenlinien_behalten_ihre_farben():
    c = _chart()
    for fest in ("'#00d4e0'", "'#f0a500'", "'#D31141'"):
        assert fest in c, fest


def test_umschalten_zeichnet_neu():
    assert "_aktivitaetZuletzt = { data: data, grouping: grouping };" in _chart()
    m = re.search(r"_designHaken\.push\(function \(\) \{(.*?)\n\}\);", INDEX, re.S)
    assert m and "_activityChart.destroy()" in m.group(1) and "renderActivityChart(" in m.group(1)
```

  Die Datenlinien (Piloten `#2d9cdb`, Flüge `#00d4e0`, Stunden `#f0a500`, Dauer `#D31141`) sind Datenfarben wie auf der Karte und bleiben — außer der ersten: `borderColor: '#2d9cdb'` / `backgroundColor: 'rgba(45,156,219,0.08)'` gehen über `--green`/`--green-rgb`, weil `#2d9cdb` auf Weiß nur 2,9:1 hat.

- [ ] **Step 2: Laufen lassen, muss scheitern.**

- [ ] **Step 3: Implementieren** — vor `renderActivityChart`:

```js
// Liest eine Design-Variable. Im dunklen Design liefert sie exakt die frueheren Literale --
// das Diagramm sieht dort unveraendert aus (Spec helles Design, Punkt 6).
function _themaFarbe(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
let _aktivitaetZuletzt = null;
```

  In `renderActivityChart` als erste Zeile `_aktivitaetZuletzt = { data: data, grouping: grouping };` und die Literale ersetzen:

| alt | neu |
|---|---|
| `'#2d9cdb'` (borderColor Piloten, titleColor) | `_themaFarbe('--green')` |
| `'rgba(45,156,219,0.08)'` | `'rgba(' + _themaFarbe('--green-rgb') + ',0.08)'` |
| `'#6b9ab8'` (alle) | `_themaFarbe('--text-label')` |
| `'#071525'` | `_themaFarbe('--bg-panel')` |
| `'rgba(45,156,219,0.3)'` | `'rgba(' + _themaFarbe('--green-rgb') + ',0.3)'` |
| `'#d4e8f5'` | `_themaFarbe('--text-bright')` |
| `'rgba(45,156,219,0.05)'` / `0.07` | `'rgba(' + _themaFarbe('--green-rgb') + ',0.05)'` / `0.07` |

  Achtung Format: `getPropertyValue` liefert den Wert so, wie er im CSS steht — `--green-rgb: 45,156,219;` ergibt `45,156,219`, also `rgba(45,156,219,0.05)`, identisch zum alten Literal. Nach dem Ende von `renderActivityChart`:

```js
_designHaken.push(function () {
  if (!_activityChart || !_aktivitaetZuletzt) return;
  _activityChart.destroy();
  _activityChart = null;
  renderActivityChart(_aktivitaetZuletzt.data, _aktivitaetZuletzt.grouping);
});
```

- [ ] **Step 4: Übrige JS-Farben** — Bestand:

```bash
sed -n '/^<script>$/,$p' app/static/index.html | grep -nE "'#[0-9a-fA-F]{3,8}'|rgba?\(" \
  > /home/claude/arbeit/helles-design/js-bestand.txt
```

  Je Treffer entscheiden: Karte (Leaflet-Optionen, `PILOT_COLORS`, `_PLATZRUNDEN_FARBE`, Kutter, Reddung, Kompass, Schilder) → fest. Oberfläche außerhalb der Karte (per JS gesetzte Hintergründe/Schrift in Tabellen, Hinweisen) → `_themaFarbe(...)` bzw. besser eine CSS-Klasse statt Inline-Farbe. Ergebnis als kurze Liste in den Commit-Text.

- [ ] **Step 5: Tests** — `pytest -n 4 tests/`, `python -m scripts.dunkel_vergleich`, Screenshot Statistik-Reiter in beiden Designs. Im dunklen Screenshot muss das Diagramm dem Stand vorher gleichen (Vorher-Screenshot aus Task 4 daneben).

- [ ] **Step 6: Commit** `"Helles Design: Statistik und JS-Farben ueber Variablen"`

---

### Task 7: Handbuch, Hilfetext, Version, Auslieferung

**Files:**
- Modify: `README.md` (Handbuch-Absatz), Hilfetext hinter dem `?` in `index.html` (Suche: `help-btn` / Hilfe-Inhalt), `app/CHANGELOG.json`

- [ ] **Step 1: README** — im Abschnitt zur Bedienung einen Absatz „Helles Design": Zahnrad oben rechts → Einstellungen → Anzeige → Design Dunkel/Hell; merkt sich die Wahl je Gerät bzw. am Konto (Website und Kniebrett getrennt); Karte bleibt, Grundkarte wie gewohnt wählen; im Kniebrett erscheint beim Start kurz das dunkle Design. Keine Pfade, keine Zählwörter.

- [ ] **Step 2: Hilfetext** — denselben Inhalt in zwei, drei Sätzen hinter dem `?`; der bisherige Text zur Glocke wird auf „Zahnrad" umgestellt (grep nach `Glocke` im Hilfetext und README, jede Fundstelle anpassen).

- [ ] **Step 3: CHANGELOG** — erst wenn keine Suite läuft. Neuer erster Eintrag:

```json
{
  "version": "15.32.0",
  "date": "<Tag der Auslieferung, TT.MM.JJJJ wie die übrigen Einträge>",
  "highlight": false,
  "title": "Helles Design",
  "items": [
    "Neu: helles Design in den Farben des Forums – umschaltbar unter Zahnrad → Einstellungen → Anzeige",
    "Die Wahl wird gemerkt, auf der Website und im Kniebrett getrennt",
    "Auf der Website ersetzt das Zahnrad die Glocke; die Benachrichtigungen stehen im selben Menü"
  ]
}
```

  Datumsformat vorher an den vorhandenen Einträgen ablesen und übernehmen.

- [ ] **Step 4: Gesamtprüfung** — `pytest -n 4 tests/` grün; `python -m scripts.dunkel_vergleich` → `geaendert: 0`, `entfernt:` nur die zwei aus Task 3; Kontrasttest grün.

- [ ] **Step 5: Commit** `"Helles Design (15.32.0): Handbuch, Hilfetext, Changelog"`

- [ ] **Step 6: Auslieferung** — Nutzer fragen, ob gerade geflogen wird; nach Freigabe `git push origin main`, melden und weiter (Deploy nicht überwachen). Nutzer um die Sim-Prüfung bitten: Kniebrett öffnen, Zahnrad → Hell, einmal durch alle Reiter; Website: Zahnrad → Hell, Seite neu laden (darf nicht dunkel aufblitzen).

- [ ] **Step 7: Aufräumen** — lokale uvicorn-Instanz beenden, `/home/claude/arbeit/helles-design/` bleibt (Arbeitsverzeichnis, wird überschrieben statt gelöscht).
