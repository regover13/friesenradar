"""Wer eine alte Adresse im Browser aufruft, wechselt auf radar.friesenflieger.de (#58).

Umgeleitet wird in der Seite selbst und nur der normale Seitenaufruf im Browser: Nur die Seite
weiss, ob sie im Kniebrett, eingebettet oder als App vom Startbildschirm laeuft. Die
Einstellungen des Browsers reisen im Anker der Adresse mit, weil jede Adresse ihren eigenen
Speicher hat."""
import json
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
ADMIN = (STATIC / "admin.html").read_text(encoding="utf-8")

_ANFANG = "/* UMZUG-FUNKTIONEN-ANFANG */"
_ENDE = "/* UMZUG-FUNKTIONEN-ENDE */"


def _funktionen(quelle=INDEX):
    a = quelle.index(_ANFANG)
    return quelle[a:quelle.index(_ENDE, a)]


def _js(ausdruck, quelle=INDEX):
    skript = _funktionen(quelle) + "\nprocess.stdout.write(JSON.stringify(%s));" % ausdruck
    erg = subprocess.run(["node", "-e", skript], capture_output=True, text=True)
    assert erg.returncode == 0, erg.stderr
    return json.loads(erg.stdout)


def _entscheid(**u):
    basis = {"host": "friesenspy.devprops.de", "panel": False, "iframe": False,
             "coherent": False, "standalone": False, "aus": False}
    basis.update(u)
    return _js("_umzugEntscheid(%s)" % json.dumps(basis))


# --- Wer wird umgeleitet -------------------------------------------------------------------

@pytest.mark.parametrize("host", ["friesenspy.devprops.de", "friesenradar.devprops.de"])
def test_beide_alten_adressen_leiten_um(host):
    assert _entscheid(host=host) == "umleiten"


@pytest.mark.parametrize("host", ["radar.friesenflieger.de", "localhost", "test-radar.devprops.de"])
def test_neue_adresse_und_fremde_bleiben(host):
    assert _entscheid(host=host) == "bleiben"


@pytest.mark.parametrize("merkmal", ["panel", "iframe", "coherent", "aus"])
def test_kniebrett_einbettung_und_ausschalter_bleiben(merkmal):
    assert _entscheid(**{merkmal: True}) == "bleiben"


def test_app_vom_startbildschirm_bekommt_einen_hinweis_statt_der_umleitung():
    assert _entscheid(standalone=True) == "hinweis"


def test_kniebrett_geht_vor_app_hinweis():
    assert _entscheid(standalone=True, panel=True) == "bleiben"


# --- Wohin, und was reist mit ---------------------------------------------------------------

def test_ziel_behaelt_pfad_abfrage_und_anker():
    ziel = _js("_umzugZiel({pathname: '/', search: '?tv=1', hash: '#tab=karte&flug=7'}, {push: 1})")
    assert ziel.startswith("https://radar.friesenflieger.de/?tv=1#tab=karte&flug=7&umzug=")


def test_ziel_ohne_anker():
    ziel = _js("_umzugZiel({pathname: '/', search: '', hash: ''}, {push: 0})")
    assert ziel.startswith("https://radar.friesenflieger.de/#umzug=")


def test_gepaeck_kommt_heil_an_und_der_anker_ist_danach_sauber():
    erg = _js("""(function () {
      var g = {k: {friesenspy_theme: 'hell', friesenspy_layer: 'topo'},
               l: {friesenradar_tv: '1', notif_ts: '0'}, push: 1};
      var ziel = _umzugZiel({pathname: '/', search: '', hash: '#tab=karte'}, g);
      return _umzugAuspacken(ziel.slice(ziel.indexOf('#')));
    })()""")
    assert erg["rest"] == "tab=karte"
    assert erg["gepaeck"]["k"] == {"friesenspy_theme": "hell", "friesenspy_layer": "topo"}
    assert erg["gepaeck"]["l"] == {"friesenradar_tv": "1", "notif_ts": "0"}
    assert erg["gepaeck"]["push"] == 1


def test_anker_ohne_gepaeck_bleibt_unberuehrt():
    assert _js("_umzugAuspacken('#tab=karte')") == {"rest": "tab=karte", "gepaeck": None}


@pytest.mark.parametrize("anker", ["#umzug=kaputt", "#umzug=%7B", "#umzug=%5B1%5D", "#umzug=null"])
def test_kaputtes_gepaeck_wird_verworfen_und_entfernt(anker):
    assert _js("_umzugAuspacken(%s)" % json.dumps(anker)) == {"rest": "", "gepaeck": None}


def test_fremde_schluessel_und_uebergrosse_werte_fallen_weg():
    """Der Anker ist von aussen setzbar: Nur bekannte Speicher-Schluessel, nur kurze Texte."""
    erg = _js("""_umzugAuspacken('#umzug=' + encodeURIComponent(JSON.stringify({
      k: {friesenspy_theme: 'hell', 'boese;path=/': 'x', gross: new Array(2000).join('a'), zahl: 5},
      l: {friesenradar_tv: '1', fs_user: 'geklaut', notif_ts: {a: 1}},
      push: 'ja'})))""")
    assert erg["gepaeck"]["k"] == {"friesenspy_theme": "hell"}
    assert erg["gepaeck"]["l"] == {"friesenradar_tv": "1"}
    assert erg["gepaeck"]["push"] == 0


def test_mitgebrachtes_fuellt_nur_was_fehlt():
    erg = _js("_umzugMischen({friesenspy_theme: 'dunkel'}, {friesenspy_theme: 'hell', friesenspy_layer: 'topo'})")
    assert erg == {"friesenspy_theme": "dunkel", "friesenspy_layer": "topo"}


# --- Verdrahtung ---------------------------------------------------------------------------

def test_umleitung_steht_vor_dem_stilblock():
    """Sonst baut sich die alte Seite erst auf, bevor sie wechselt."""
    assert INDEX.index(_ANFANG) < INDEX.index("\n  <style")


def test_admin_leitet_nach_derselben_regel_um():
    assert _funktionen(ADMIN).strip() == _funktionen(INDEX).strip(), \
        "admin.html muss denselben Funktionsblock tragen wie index.html"
    assert ADMIN.index(_ANFANG) < ADMIN.index("\n  <style")


def test_teilen_nennt_von_beiden_alten_adressen_aus_die_neue():
    for datei in (INDEX, ADMIN):
        start = datei.index("function _teilenUrsprung(")
        fn = datei[start:datei.index("\n", datei.index("}", start))]
        for alt in ("https://friesenspy.devprops.de", "https://friesenradar.devprops.de"):
            js = "var location = {origin: %s, hostname: %s};\n%s\n%s\nprocess.stdout.write(_teilenUrsprung());" % (
                json.dumps(alt), json.dumps(alt[8:]), _funktionen(datei), fn)
            aus = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
            assert aus == "https://radar.friesenflieger.de"


def test_hinweise_haben_ihren_platz_in_der_seite():
    assert 'id="umzug-banner"' in INDEX
