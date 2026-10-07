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
    # Das erste <script> ist seit #58 der Adresswechsel; gemeint ist das Skript danach.
    start = INDEX.index("<script>", INDEX.index("UMZUG-FUNKTIONEN-ENDE")) + len("<script>")
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
// Das Kopfskript meldet vor seinem Website-return (Z. 89) noch einen resize-Lauscher an (Z. 75).
global.addEventListener = () => {};
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


@ohne_node
@pytest.mark.parametrize("server,beruehrt,erwartet", [
    ({"friesenspy_theme": "hell"}, None, ("hell", None)),      # nur angezeigt, nichts hochgeschickt
    ({}, None, ("dunkel", None)),
    # Review Focus 2: vor der Antwort auf Hell geschaltet, Server kennt noch "dunkel" --
    # die Wahl gewinnt und wird gespeichert, statt nur angezeigt.
    ({"friesenspy_theme": "dunkel"}, "hell", ("hell", "hell")),
])
def test_serverantwort_und_eigene_wahl(server, beruehrt, erwartet):
    pref = INDEX[INDEX.index("const _PREF_COOKIE"):INDEX.index("\n}", INDEX.index("function _prefVomServerHolen(")) + 2]
    design = INDEX[INDEX.index("const _DESIGN_KEY"):INDEX.index("// ENDE DESIGN-ABSCHNITT")]
    nach = INDEX[INDEX.index("// Das Kopfskript hat auf der Website schon aus dem Cookie gemalt"):]
    nach = nach[:nach.index("}).catch(() => {});") + len("}).catch(() => {});")]
    js = (_DOC % "''") + """
global.localStorage = { getItem: () => null, setItem: () => {} };
const puts = [];
global.fetch = (url, opt) => {
  if (opt && opt.method === 'PUT') { puts.push(JSON.parse(opt.body).prefs); return Promise.resolve({ ok: true }); }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ prefs: %s }) });
};
global.setTimeout = (f) => f();
""" % json.dumps(server) + pref + "\n" + design + "\n" + """
const _prefsPromise = _prefVomServerHolen();
%s
""" % ("_designSetzen('%s');" % beruehrt if beruehrt else "") + nach + """
_prefsPromise.then(() => new Promise(r => r())).then(() => {
  const letzter = puts.length ? puts[puts.length - 1].friesenspy_theme || null : null;
  console.log(JSON.stringify([klassen.has('hell') ? 'hell' : 'dunkel', letzter]));
});"""
    assert _lauf(js) == list(erwartet)


def test_theme_color_folgt_dem_design():
    assert "const _DESIGN_META = { dunkel: '#04080f', hell: '#9FC7F8' };" in INDEX
    assert 'name="theme-color" content="#04080f"' in INDEX  # Ausgangswert bleibt


def test_die_farbe_der_adressleiste_stimmt_schon_beim_laden():
    """Issue #55, Punkt 2: Das Kopfskript setzt `html.hell` vor dem ersten Zeichnen, das
    `theme-color` kam aber erst nach der Serverantwort -- die Adressleiste der installierten
    App blitzte dunkel. Ein zweites Inline-Skript direkt hinter dem Meta zieht es sofort nach."""
    meta = INDEX.index('<meta name="theme-color" content="#04080f" />')
    danach = INDEX[meta:meta + 600]
    assert "<script>" in danach and "classList.contains('hell')" in danach
    assert "'#9FC7F8'" in danach, "muss dieselbe Farbe sein wie _DESIGN_META.hell"
    assert "_DESIGN_META = { dunkel: '#04080f', hell: '#9FC7F8' }" in INDEX
    assert INDEX.index("classList.add('hell')") < meta, "die Klasse muss vorher gesetzt sein"


def test_die_bedienfarbe_heisst_nicht_mehr_text_hell():
    """Issue #55, Punkt 3: `--text-hell` trug im hellen Design einen dunklen Wert."""
    assert "--text-hell" not in INDEX and INDEX.count("--text-bedien") >= 3
