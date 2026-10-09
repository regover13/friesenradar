"""Die durchlaufende Linie (Scanline) laesst sich in den Einstellungen abschalten
(Nutzerwunsch 09.10.2026). Gemerkt wie das Design: im Merker-Cookie und am Konto."""
import json
import re
import subprocess
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def test_schalter_steht_in_den_einstellungen_zwischen_design_und_tv():
    assert INDEX.index('id="einst-design"') < INDEX.index('id="einst-radarlinie"') < INDEX.index('id="einst-tv"')
    a = INDEX.index('id="einst-radarlinie"')
    abschnitt = INDEX[a:INDEX.index('id="einst-tv"')]
    assert ">Radarlinie<" in abschnitt
    assert 'id="radarlinie-an"' in abschnitt and 'id="radarlinie-aus"' in abschnitt


def test_wo_es_die_linie_nicht_gibt_gibt_es_auch_den_schalter_nicht():
    assert re.search(r"html\.vr-panel #einst-radarlinie,\s*html\.tv #einst-radarlinie \{ display: none", INDEX)


def test_abgeschaltet_heisst_weg():
    assert re.search(r"html\.ohne-radarlinie \.scanline \{ display: none !important; \}", INDEX)


def _kopf(cookie):
    """Fuehrt das Kopfskript aus und gibt die Klassen von <html> zurueck."""
    start = INDEX.index("<script>", INDEX.index("UMZUG-FUNKTIONEN-ENDE")) + len("<script>")
    skript = INDEX[start:INDEX.index("</script>", start)]
    harness = """
var klassen = [];
var document = { cookie: %s, documentElement: { classList: { add: function (k) { klassen.push(k); }, contains: function (k) { return klassen.indexOf(k) >= 0; } }, style: {} } };
var location = { search: '', pathname: '/' };
var localStorage = { getItem: function () { return null; }, removeItem: function () {} };
var window = { matchMedia: function () { return { matches: false }; }, innerWidth: 1200, addEventListener: function () {} };
var navigator = { userAgent: '' };
function URLSearchParams() { this.get = function () { return null; }; }
try { %s } catch (e) {}
process.stdout.write(JSON.stringify(klassen));
""" % (json.dumps(cookie), skript)
    erg = subprocess.run(["node", "-e", harness], capture_output=True, text=True)
    assert erg.returncode == 0, erg.stderr
    return json.loads(erg.stdout)


def _cookie(merker):
    from urllib.parse import quote
    return "fs_karte=" + quote(json.dumps(merker))


def test_kopfskript_blendet_die_linie_schon_vor_dem_ersten_zeichnen_aus():
    assert "ohne-radarlinie" in _kopf(_cookie({"friesenspy_scanline": "aus"}))
    assert "ohne-radarlinie" not in _kopf(_cookie({"friesenspy_scanline": "an"}))
    assert "ohne-radarlinie" not in _kopf(_cookie({"friesenspy_theme": "hell"}))
    assert "ohne-radarlinie" not in _kopf("")


def test_wahl_wird_wie_das_design_gemerkt():
    a = INDEX.index("const _RADARLINIE_KEY = 'friesenspy_scanline';")
    block = INDEX[a:INDEX.index("// ENDE RADARLINIE", a)]
    assert "_prefSchreib(_RADARLINIE_KEY, an ? 'an' : 'aus')" in block
    assert "classList.toggle('ohne-radarlinie'" in block
    assert "_radarlinieSetzen(true)" in INDEX and "_radarlinieSetzen(false)" in INDEX
    assert "_radarlinieAnwenden(_prefLies(_RADARLINIE_KEY))" in INDEX, "nach der Serverantwort anwenden"
