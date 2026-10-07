"""Kniebrett-Paket 3.0.0: neuer Ordner, alter daneben (Variante B, Nutzer 03.10.2026).

Seit 3.0.0 heissen Paketordner und App-Klasse FriesenRadar. Wer beim Update den alten Ordner
`friesenflieger-friesenspy-efb` nicht loescht, hat zwei Apps im Tablet -- und erfaehrt es nur,
wenn eine der beiden es ihm sagt. Beide Wege sind hier festgehalten:

- die NEUE App erkennt die alte an deren Klassennamen und meldet `altesPaket` im pong; die
  Seite zeigt dann einen Kasten, der sich nicht wegklicken laesst;
- die ALTE App (2.x) kann nichts erkennen, aber die Seite weiss, dass sie zu alt ist: Ihr
  Hinweis nennt beim Sprung auf 3.x den Ordner, der weg muss.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
INDEX = (WURZEL / "app" / "static" / "index.html").read_text(encoding="utf-8")
QUELLE = WURZEL / "msfs-panel" / "PackageSources" / "FriesenRadar"
SHELL = (QUELLE / "src" / "FriesenRadar.tsx").read_text(encoding="utf-8")
MANIFEST = json.loads((QUELLE / "manifest.json").read_text(encoding="utf-8"))
ALTER_ORDNER = "friesenflieger-friesenspy-efb"


def test_ordner_klasse_und_app_pfad_heissen_gleich():
    """Das CSS-Praefix kommt aus dem Quellordner (build.js), die EFB fuehrt die App unter dem
    Klassennamen, und BASE_URL zeigt auf efb_apps/<Name>. Weichen sie ab, fehlen die Styles."""
    build = (QUELLE / "build.js").read_text(encoding="utf-8")
    assert QUELLE.name == "FriesenRadar"
    assert "class FriesenRadar extends App" in SHELL
    assert 'efb_apps/FriesenRadar"' in build
    assert 'efb_apps\\FriesenRadar"' in (WURZEL / "msfs-panel" / "build-package.ps1").read_text(encoding="utf-8")


def test_manifest_heisst_friesenradar_und_ist_3():
    assert MANIFEST["title"] == "FriesenRadar"
    assert MANIFEST["package_version"].split(".")[0] == "3"


def test_geraetekennung_bleibt():
    """Unter diesem Schluessel liegt die Bindung jedes Tablets."""
    assert 'const DEVICE_KEY = "friesenspy_device";' in SHELL


def test_neue_app_meldet_das_alte_paket_im_pong():
    stelle = SHELL.index('if (d.art === "ping")')
    assert "altesPaket: altesPaketDa()" in SHELL[stelle:stelle + 900]
    rumpf = SHELL[SHELL.index("function altesPaketDa("):]
    rumpf = rumpf[:rumpf.index("\n}\n")]
    assert 'internalName === "FriesenSpy"' in rumpf
    assert "return undefined" in rumpf, "unbekannt darf nicht als 'kein altes Paket' gelten"


def test_seite_zeigt_den_doppelt_kasten_und_er_ist_nicht_wegklickbar():
    m = re.search(r'<div id="panel-paket-doppelt"[^>]*>(.*?)</div>', INDEX, re.S)
    assert m, "Kasten #panel-paket-doppelt fehlt"
    assert "<button" not in m.group(1)
    assert ALTER_ORDNER in m.group(1)
    pong = INDEX[INDEX.index("if (d.art === 'pong') {"):]
    pong = pong[:pong.index("\n    }\n")]
    assert "d.altesPaket === true" in pong
    assert "panel-paket-doppelt" in pong


def test_doppelt_kasten_nur_im_kniebrett():
    assert re.search(r"\.panel-paket-doppelt\s*\{[^}]*display:\s*none", INDEX)
    assert re.search(r"html\.vr-panel \.panel-paket-doppelt\.an\s*\{", INDEX)


def _hinweistext(installiert, aktuell):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js nicht verfuegbar")
    start = INDEX.index("function _versionKleiner(")
    ende = INDEX.index("\n}\n", INDEX.index("function _paketHinweisText(")) + 3
    teil = INDEX[start:INDEX.index("\n}\n", start) + 3] + INDEX[INDEX.index("function _paketHinweisText("):ende]
    js = teil + "process.stdout.write(_paketHinweisText(%s, %s));" % (json.dumps(installiert), json.dumps(aktuell))
    return subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout


def test_alte_app_hinweis_nennt_den_alten_ordner_beim_sprung_auf_3():
    t = _hinweistext("2.3.2", "3.0.0")
    assert "3.0.0" in t and "2.3.2" in t and ALTER_ORDNER in t and "radar.friesenflieger.de/download" in t


def test_innerhalb_derselben_hauptnummer_kein_ordnerhinweis():
    t = _hinweistext("3.0.0", "3.1.0")
    assert ALTER_ORDNER not in t and "3.1.0" in t


def test_download_seite_nennt_den_alten_ordner_erst_ab_3():
    efb = (WURZEL / "app" / "static" / "efb.html").read_text(encoding="utf-8")
    m = re.search(r'<span id="alter-ordner" hidden>(.*?)</span>', efb, re.S)
    assert m and ALTER_ORDNER in m.group(1)
    skript = efb[efb.index("fetch('/api/efb-package'"):]
    skript = skript[:skript.index(".catch(")]
    assert "split('.')[0]) >= 3" in skript and "alter-ordner" in skript


def test_app_symbol_ist_das_rote_flugzeug():
    """Abschluss-Review 03.10.2026: Das Symbol war beim Umbenennen nur mitgewandert (altes
    "FRS" im Kreis). Es muss dasselbe sein wie das App-Symbol der Website."""
    symbol = (QUELLE / "src" / "Assets" / "app-icon.svg").read_text(encoding="utf-8")
    vorlage = (WURZEL / "app" / "static" / "logo" / "friesenradar-symbol.svg").read_text(encoding="utf-8")
    assert symbol == vorlage
    assert "<image" not in symbol, "Coherent GT: nur reine Vektoren (s. 0e925af/fce83aa)"


def test_nur_nachrichten_aus_dem_eigenen_rahmen():
    """Liegt das alte Paket daneben, lauschen BEIDE Apps am gemeinsamen Fenster der EFB-Huelle.
    Ohne diese Pruefung beantwortet jede App den ping der anderen (zwei pongs, springende
    Paketversion) und zeigt deren Benachrichtigungen doppelt an."""
    start = SHELL.index("private readonly onNachricht")
    rumpf = SHELL[start:start + 900]
    assert "e.source" in rumpf and "rahmenRef" in rumpf
    assert rumpf.index("e.source") < rumpf.index('d.art === "ping"')


def test_eigene_kartenbindung():
    """Beide Fassungen nebeneinander duerfen sich die Bindung des Kartensystems nicht teilen."""
    assert '"FRIESENRADAR_VERKEHR"' in SHELL and "FRIESENSPY_VERKEHR" not in SHELL
