"""Friesen als Lotsen (#61): Anzeige in Live-Liste, Geplant-Liste und Karte. Namen erfunden."""
import json
import re
import subprocess
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")

_A = "// LOTSEN-FUNKTIONEN-ANFANG"
_E = "// LOTSEN-FUNKTIONEN-ENDE"


def _js(ausdruck):
    block = INDEX[INDEX.index(_A):INDEX.index(_E)]
    stubs = """
function escHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function pilotLinkHtml(n,c){return '<a class="pilot-link">'+escHtml(n)+'</a>';}
function fmtOnlineTime(t){return '01:27';}
"""
    erg = subprocess.run(["node", "-e", stubs + block + "\nprocess.stdout.write(JSON.stringify(%s));" % ausdruck],
                         capture_output=True, text=True)
    assert erg.returncode == 0, erg.stderr
    return json.loads(erg.stdout)


LOTSE = {"cid": 1000001, "name": "Erika Muster", "callsign": "EDDP_GND", "station": "Leipzig Ground",
         "frequenz": "121.805", "lat": 51.4, "lon": 12.2, "online_seit": "2026-10-09T13:33:10Z", "bis": "20:00"}
SCHICHT = {"id": 1, "cid": 1000001, "name": "Erika Muster", "callsign": "EDDS_TWR", "station": "Stuttgart Tower",
           "lat": 48.7, "lon": 9.2, "von": "2026-10-11T18:00:00Z", "bis": "2026-10-11T20:00:00Z"}


def test_flugplan_spalte_nennt_station_frequenz_und_ende():
    assert _js("_lotseText(%s)" % json.dumps(LOTSE)) == "Leipzig Ground · 121.805 · bis 20:00 UTC"
    assert _js("_lotseText(%s)" % json.dumps(dict(LOTSE, bis=None))) == "Leipzig Ground · 121.805"


def test_zelle_in_der_live_liste_station_und_frequenz_untereinander():
    """Nutzer 09.10.2026: Die Spalte war viel zu breit. Station und Frequenz untereinander;
    das Ende steht unter der Online-Zeit (s. u.)."""
    assert _js("_lotseZelle(%s)" % json.dumps(LOTSE)) == "Leipzig Ground<br>121.805"
    assert _js("_lotseZelle(%s)" % json.dumps(dict(LOTSE, bis=None))) == "Leipzig Ground<br>121.805"
    boese = dict(LOTSE, station="<b>x</b>")
    assert "<b>" not in _js("_lotseZelle(%s)" % json.dumps(boese))


def test_zeile_in_der_live_liste():
    z = _js("_lotsenZeile(%s)" % json.dumps(LOTSE))
    assert z.count("<td") == 8, "dieselben acht Spalten wie eine Pilotenzeile"
    assert ">EDDP_GND<" in z and "Erika Muster" in z and ">Lotse<" in z
    assert '<td class="td-route">Leipzig Ground<br>121.805</td>' in z
    assert '<td class="td-time">01:27<br><span class="lotse-bis">bis 20:00 UTC</span></td>' in z, \
        "das Ende steht unter der Online-Zeit"
    ohne = _js("_lotsenZeile(%s)" % json.dumps(dict(LOTSE, bis=None)))
    assert '<td class="td-time">01:27</td>' in ohne and "lotse-bis" not in ohne
    assert "td-callsign-link" not in z and "text-green" not in z, "die Zeile oeffnet nichts, also kein Blau"
    assert 'data-callsign=' not in z, "sonst hielte die Karte den Lotsen fuer ein Flugzeug"
    assert 'class="td-map-btn td-lotse-map"' in z and 'data-lotse="EDDP_GND"' in z


def test_schicht_zeit_mit_wochentag_und_datum():
    assert _js("_schichtZeit(%s)" % json.dumps(SCHICHT)) == "So 11.10. 18:00–20:00 UTC"
    nacht = dict(SCHICHT, von="2026-10-12T22:00:00Z", bis="2026-10-13T00:30:00Z")
    assert _js("_schichtZeit(%s)" % json.dumps(nacht)) == "Mo 12.10. 22:00–00:30 UTC"


def test_flugplaene_und_schichten_gemeinsam_nach_zeit():
    plaene = [{"callsign": "FRS1", "deptime": "1900", "remarks": "DOF/261011"},
              {"callsign": "FRS2", "deptime": "0930", "remarks": "DOF/261012"},
              {"callsign": "FRS3", "deptime": "", "remarks": ""}]
    erg = _js("_geplantMischen(%s, [%s], Date.UTC(2026, 9, 11, 12, 0))" % (json.dumps(plaene), json.dumps(SCHICHT)))
    assert [(e["art"], e["daten"]["callsign"]) for e in erg] == [
        ("flug", "FRS3"), ("schicht", "EDDS_TWR"), ("flug", "FRS1"), ("flug", "FRS2")], \
        "ohne Zeitangabe zuerst, sonst nach Beginn"
    assert [e["idx"] for e in erg if e["art"] == "flug"] == [2, 0, 1], "der Index zeigt auf den Flugplan"


def test_flugplan_ohne_datum_gilt_fuer_heute():
    erg = _js("_geplantMischen([{callsign:'FRS1', deptime:'1700', remarks:''}], [%s], Date.UTC(2026, 9, 11, 12, 0))"
              % json.dumps(SCHICHT))
    assert [e["daten"]["callsign"] for e in erg] == ["FRS1", "EDDS_TWR"]


def test_zeile_in_der_geplant_liste():
    z = _js("_schichtZeile(%s, 0)" % json.dumps(SCHICHT))
    assert z.count("<td") == 5
    assert ">EDDS_TWR<" in z and "Lotse · Stuttgart Tower" in z and "So 11.10. 18:00–20:00 UTC" in z
    assert "text-green" not in z and "cursor:pointer" not in z
    assert 'data-schicht="0"' in z and "td-lotse-map" in z


# --- Verdrahtung ---------------------------------------------------------------------------

def test_ueberschrift_der_geplant_liste():
    assert '<div class="panel-title">Geplant · Flugpläne und Lotsenschichten</div>' in INDEX
    assert "Eingereichte Flugpläne (Prefile)" not in INDEX


def test_live_liste_zeigt_lotsen_auch_ohne_flieger():
    fn = INDEX[INDEX.index("function renderLiveTable("):INDEX.index("function escHtml(")]
    assert "_lotsen.online" in fn and "_lotsenZeile(" in fn
    leer = fn[:fn.index("empty-state")]
    assert "_lotsen.online.length" in leer, "Keine Friesen online nur, wenn auch niemand lotst"
    assert ".td-map-btn:not(.td-lotse-map)" in fn, "der Kartensprung der Flieger darf Lotsen nicht greifen"


def test_geplant_liste_mischt_schichten_ein():
    fn = INDEX[INDEX.index("function renderPrefiles("):INDEX.index("async function showPrefileRoute(")]
    assert "_geplantMischen(" in fn and "_schichtZeile(" in fn


def test_lotsen_werden_im_takt_der_flugplaene_geholt():
    fn = INDEX[INDEX.index("async function fetchAndRenderPrefiles("):INDEX.index("let _prefileData")]
    assert "fetch('/api/lotsen')" in fn
    assert re.search(r"setInterval\(_imTakt\(fetchAndRenderPrefiles\)", INDEX), "kein neuer Takt ohne _imTakt"


def test_karte_zeichnet_lotsen_und_raeumt_sie_wieder_weg():
    fn = INDEX[INDEX.index("function _lotsenAufKarteZeichnen("):INDEX.index("function _lotseAufKarte(")]
    assert "removeLayer" in fn and "L.marker" in fn and "icon-headset" in fn
    um = INDEX[INDEX.index("function updateMap(pilots)"):INDEX.index("function updateMap(pilots)") + 600]
    assert "_lotsenAufKarteZeichnen()" in um


def test_schalter_in_den_einstellungen_nennen_auch_die_lotsen():
    """Nutzer 09.10.2026: Die Schalter melden seit 16.2.0 auch Lotsen, das muss dranstehen."""
    assert '<input type="checkbox" id="notif-enabled"> Beim Online-gehen benachrichtigen (Piloten und Lotsen)' in INDEX
    assert '<input type="checkbox" id="notif-prefiles" checked> Auch bei Geplantem (Flugpläne und Lotsenschichten)' in INDEX
    assert "Benachrichtigen wenn (gilt für Online, Geplantes &amp; TeamSpeak):" in INDEX
    assert "Auch bei eingereichten Flugplänen" not in INDEX


def test_spaltenkoepfe_passen_auch_fuer_lotsen():
    """Nutzer 09.10.2026: „Pilot“ und „Flugplan“ passen fuer Lotsen nicht."""
    live = INDEX[INDEX.index("function renderLiveTable("):INDEX.index("function escHtml(")]
    assert "<th>Friese</th>" in live and "<th>Flugplan / Station</th>" in live and "<th>Pilot</th>" not in live
    gepl = INDEX[INDEX.index("function renderPrefiles("):INDEX.index("async function showPrefileRoute(")]
    assert "<th>Friese</th><th>Flugplan / Station</th><th>Zeit (geplant)</th>" in gepl


def test_spalte_heisst_online_und_das_ende_ist_nicht_in_der_farbe_der_online_zeit():
    live = INDEX[INDEX.index("function renderLiveTable("):INDEX.index("function escHtml(")]
    assert "<th>Online</th>" in live and "<th>Online seit</th>" not in live
    assert re.search(r"\.td-time \.lotse-bis \{[^}]*color: var\(--text-label\)", INDEX), \
        "wie bisher in der Stationsspalte, nicht in der Farbe der Online-Zeit"
