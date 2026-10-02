"""Vorschau auf FriesenRadar (Issue #56, Release V16 "Lichtblick").

Der neue Name erscheint nur, wenn `html.radar` gesetzt ist: ueber die neuen Adressen (Kopfskript,
vor dem ersten Zeichnen) oder fuer freigegebene CIDs (`/api/me` -> `radar_vorschau`, fuers
Kniebrett, das immer friesenspy.devprops.de laedt). Ohne Schalter bleibt alles wie bisher.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
_NODE = shutil.which("node")
ohne_node = pytest.mark.skipif(not _NODE, reason="node fehlt")


def _kopfskript():
    start = INDEX.index("<script>") + len("<script>")
    return INDEX[start:INDEX.index("</script>", start)]


_DOC = """
const klassen = new Set();
global.document = { cookie: '', documentElement: { classList: {
  add: (k) => klassen.add(k), remove: (k) => klassen.delete(k), contains: (k) => klassen.has(k),
  toggle: (k, an) => an ? klassen.add(k) : klassen.delete(k) }, style: {} },
  querySelector: () => null, getElementById: () => null, querySelectorAll: () => [] };
global.location = { pathname: '/', search: '', hostname: %s };
global.URLSearchParams = URLSearchParams;
global.window = global; global.matchMedia = () => ({ matches: false });
global.addEventListener = () => {};
"""


@ohne_node
@pytest.mark.parametrize("host,erwartet", [
    ("friesenradar.devprops.de", True), ("radar.friesenflieger.de", True),
    ("friesenspy.devprops.de", False), ("localhost", False),
])
def test_kopfskript_schaltet_die_vorschau_ueber_die_neuen_adressen(host, erwartet):
    js = (_DOC % json.dumps(host)) + _kopfskript() + "\nconsole.log(JSON.stringify(klassen.has('radar')));"
    r = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1]) is erwartet


def test_cid_freigabe_schaltet_die_vorschau_ein():
    a = INDEX.index("function fsRefreshSession()")
    rumpf = INDEX[a:INDEX.index("\n}\n", a)]
    assert "if (d.radar_vorschau) _radarAnwenden();" in rumpf


def test_logos_liegen_bereit_und_stehen_in_der_kopfzeile():
    for name in ("friesenradar-weiss.svg", "friesenradar-farbig.svg"):
        assert (STATIC / "logo" / name).is_file(), name
        assert f'src="/static/logo/{name}"' in INDEX, name
    # Im Dunklen weiss, im Hellen farbig (Entscheidung 02.10.2026, Issue #51).
    assert re.search(r"html\.radar \.logo-radar-weiss \{[^}]*display: block", INDEX)
    assert re.search(r"html\.radar\.hell \.logo-radar-weiss \{[^}]*display: none", INDEX)
    assert re.search(r"html\.radar\.hell \.logo-radar-farbig \{[^}]*display: block", INDEX)
    assert re.search(r"html\.radar \.logo-alt \{[^}]*display: none", INDEX)


def test_kopfzeile_ist_in_der_vorschau_zentriert():
    r = re.search(r"html\.radar header \{([^}]*)\}", INDEX).group(1)
    assert "grid-template-columns: 1fr auto 1fr" in r
    assert "padding: 6px 18px 0 18px" in r


def test_name_kommt_aus_einer_stelle():
    assert "function _appName()" in INDEX
    # Feste Stellen im Markup tragen die Klasse, damit _radarAnwenden sie findet.
    assert INDEX.count('class="app-name"') >= 3
    # Statistik-Quellenangaben nennen den Namen ueber _appName(), nicht fest.
    assert "FriesenSpy · ${stCount} StatSim" not in INDEX


def test_kniebrett_leiste_zeigt_das_logo():
    r = re.search(r"html\.radar\.vr-panel \.panel-topbar::before \{([^}]*)\}", INDEX).group(1)
    assert "/static/logo/friesenradar-weiss.svg" in r
    assert "content: ''" in r
