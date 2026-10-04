"""Pilotennamen fuehren in die Statistik des Piloten (Nutzerwunsch 27.09.2026).

Ueberall, wo ein Pilot mit Namen (beim Kutter: mit Rufzeichen) steht und seine CID bekannt
ist, oeffnet ein Klick die Detailansicht seiner Statistik. Gebaut an einer Stelle:
`pilotLinkHtml` erzeugt den Verweis, ein einziger delegierter Klick-Lauscher oeffnet ihn --
das ueberlebt jeden innerHTML-Neubau, ohne dass ein Renderer Handler anhaengen muss.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")
_NODE = shutil.which("node")


def _funktion(name: str) -> str:
    m = re.search(rf"^(async )?function {re.escape(name)}\(", _INDEX, flags=re.M)
    assert m, f"function {name} fehlt"
    return _INDEX[m.start():_INDEX.index("\n}\n", m.start()) + 3]


def _node(js: str):
    erg = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert erg.returncode == 0, erg.stderr
    return json.loads(erg.stdout.strip().splitlines()[-1])


_ESC = _funktion("escHtml")


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_der_verweis_traegt_die_cid_und_escaped_den_namen():
    js = _ESC + _funktion("pilotLinkHtml") + """
      console.log(JSON.stringify([pilotLinkHtml('Jan <b>', 1031301), pilotLinkHtml('Ohne', null),
                                  pilotLinkHtml('Null', 0)]));
    """
    mit, ohne, null = _node(js)
    assert 'data-pilot-cid="1031301"' in mit and 'class="pilot-link"' in mit
    assert "Jan &lt;b&gt;" in mit and "<b>" not in mit
    # Ohne CID gibt es nichts zu oeffnen -- dann bleibt es reiner Text.
    assert ohne == "Ohne" and null == "Null"


def _oeffnen_js(im_fenster: list[int]) -> str:
    return """
      let tage = '30', geoeffnet = null, tabGeklickt = 0, geschlossen = 0, oben = 0;
      let pilotStatsMap = {};
      const sel = {get value() { return tage; }, set value(v) { tage = v; }};
      const document = {
        querySelector: () => ({click: () => { tabGeklickt++; }}),
        getElementById: (id) => id === 'stats-days' ? sel
          : id === 'ac-modal' ? {classList: {contains: () => true}} : null,
      };
      const window = {scrollTo: () => { oben++; }};
      function closeAcModal() { geschlossen++; }
      const IM_FENSTER = %s;
      async function fetchStats() {
        pilotStatsMap = {};
        for (const c of (tage === '365' ? [...IM_FENSTER, 42] : IM_FENSTER)) pilotStatsMap[c] = {};
      }
      async function openPilotFlights(cid) { geoeffnet = [cid, tage]; }
    """ % json.dumps(im_fenster) + _funktion("openPilotStats")


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_ein_pilot_im_gewaehlten_zeitraum_oeffnet_dort():
    js = _oeffnen_js([7, 42]) + """
      openPilotStats(42).then(() => console.log(JSON.stringify([geoeffnet, tabGeklickt, geschlossen, oben])));
    """
    assert _node(js) == [[42, "30"], 1, 1, 1]


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_ein_pilot_ausserhalb_des_zeitraums_oeffnet_im_jahr():
    """openPilotFlights bricht still ab, wenn die CID nicht in pilotStatsMap steht."""
    js = _oeffnen_js([7]) + """
      openPilotStats(42).then(() => console.log(JSON.stringify(geoeffnet)));
    """
    assert _node(js) == [42, "365"]


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_der_klick_oeffnet_und_loest_die_zeile_nicht_mit_aus():
    """Die Flugplan-Zeile oeffnet bei Klick das Flugplan-Fenster. Ein Klick auf den Namen darin
    darf nur die Statistik oeffnen -- deshalb Einfangphase und stopPropagation."""
    js = _funktion("_pilotLinkKlick") + """
      const aufrufe = []; function openPilotStats(c) { aufrufe.push(c); }
      function ereignis(treffer) {
        const e = {gestoppt: 0, verhindert: 0,
          target: {closest: () => treffer},
          stopPropagation() { this.gestoppt++; }, preventDefault() { this.verhindert++; }};
        _pilotLinkKlick(e); return [e.gestoppt, e.verhindert];
      }
      const auf = ereignis({dataset: {pilotCid: '1031301'}, closest: () => null});
      const daneben = ereignis(null);
      // Der eigene Name im Zahnradmenue: Das Menue schliesst sich beim Klick (16.0.0).
      const menue = {hidden: false};
      const imMenue = ereignis({dataset: {pilotCid: '7'}, closest: (sel) => sel === '#notif-panel' ? menue : null});
      console.log(JSON.stringify([aufrufe, auf, daneben, imMenue, menue.hidden]));
    """
    assert _node(js) == [[1031301, 7], [1, 1], [0, 0], [1, 1], True]


def test_der_lauscher_haengt_in_der_einfangphase_am_dokument():
    assert "document.addEventListener('click', _pilotLinkKlick, true)" in _INDEX


def test_der_verweis_ist_blau_wie_alles_klickbare():
    m = re.search(r"\.pilot-link\s*\{([^}]*)\}", _INDEX)
    assert m and "var(--green)" in m.group(1) and "cursor: pointer" in m.group(1)


# Jede Ansicht, in der ein Pilot mit CID steht, nimmt den Verweis.
@pytest.mark.parametrize("funktion", [
    "renderLiveTable", "renderPrefiles", "buildPopupHtml", "openAcModal",
    "renderBummelParticipants", "renderBummelStandings", "fetchBummelActive",
    "_reddungMarkenHtml", "_reddungBilanzHtml",
    "_kutterBannerBlock", "_kutterBadgeSection", "_kutterDetailBody",
])
def test_die_ansicht_verlinkt_ihre_piloten(funktion):
    assert "pilotLinkHtml(" in _funktion(funktion), funktion


def test_die_live_tabelle_zeigt_den_namen_nicht_mehr_als_reinen_text():
    assert "<td>${escHtml(p.name || '—')}</td>" not in _funktion("renderLiveTable")


def test_der_kutter_block_reicht_die_cid_durch():
    """Der Live-Block baut sich eigene Zeilen und nahm bisher nur das Rufzeichen mit."""
    block = _funktion("_kutterBannerBlock")
    assert re.search(r"active\.push\(\{\s*cid: p\.cid,", block)


def test_der_name_auf_der_event_karte_oeffnet_wie_das_rufzeichen_daneben():
    """Die Event-Analyse oeffnet ueber openPilotFromEvents (Jahresfenster, weil das Event lange
    zurueckliegen kann) -- der Name daneben muss dasselbe tun."""
    karte = _funktion("renderEventsResults")
    assert re.search(r'class="pilot-card-cid pilot-link"[^>]*onclick="openPilotFromEvents\(\$\{p\.cid\}\)"', karte)


def test_der_eigene_name_im_kopf_fuehrt_zur_eigenen_statistik():
    sitzung = _funktion("fsRefreshSession")
    assert re.search(r"getElementById\('userName'\)\.innerHTML\s*=\s*pilotLinkHtml\(", sitzung)
    assert "getElementById('userName').textContent" not in sitzung
