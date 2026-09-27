"""Tabellen behalten beim Aktualisieren ihre Scrollstellung (Nutzer-Fund 27.09.2026).

Auf dem Smartphone sprang die waagerecht verschobene Live-Tabelle alle paar Sekunden zurueck
an den Anfang: Jede Aktualisierung baut die Tabelle per innerHTML neu, und der neue Kasten
beginnt wieder links. Die Live-Tabelle wird dabei gleich dreifach aufgefrischt (SSE-Push,
Rueckfall-Abruf, 10-s-Anzeigetakt). Dasselbe galt fuer jede Tabelle, die sich von selbst
auffrischt -- Flugplaene, Bummel, Kutter, Reddung, die Flugliste eines Piloten.

Geloest an EINER Stelle statt in jedem Renderer: Ein Scroll-Lauscher merkt sich die Stellung
jedes Tabellen-Wrappers, ein MutationObserver setzt sie beim neu eingesetzten Wrapper wieder.
Dazu wartet jeder Takt, solange ein Finger auf einer Tabelle liegt -- ein Umbau mitten in der
Wischbewegung wuerde sie abwuergen, auch wenn die Stellung danach stimmt.
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


def _block() -> str:
    """Konstanten und Zustand des Blocks, von der ersten Deklaration bis vor die erste Funktion."""
    start = _INDEX.index("const _SCROLL_WRAPS")
    ende = _INDEX.index("function _scrollSchluessel(")
    return _INDEX[start:ende]


def _node(js: str):
    erg = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert erg.returncode == 0, erg.stderr
    return json.loads(erg.stdout.strip().splitlines()[-1])


# Ein DOM, das genau kann, woran der Block haengt: matches/closest ueber die Klasse,
# querySelectorAll ueber die Nachfahren und ein id-Anker. Absichtlich kein jsdom
# (Vorbild tests/test_zieh_aktualisieren.py).
_DOM = """
const WRAP = ['live-table-wrap', 'table-scroll'];
function El(id, klasse) {
  this.id = id || ''; this.klasse = klasse || ''; this.kinder = []; this.parentElement = null;
  this.nodeType = 1; this.scrollLeft = 0; this.scrollTop = 0;
}
El.prototype.dazu = function (k) { k.parentElement = this; this.kinder.push(k); return k; };
El.prototype.istWrap = function () { return WRAP.indexOf(this.klasse) !== -1; };
El.prototype.matches = function (sel) {
  if (sel === '[id]') return !!this.id;
  return this.istWrap();
};
El.prototype.closest = function (sel) {
  for (let e = this; e; e = e.parentElement) if (e.matches(sel)) return e;
  return null;
};
El.prototype.querySelectorAll = function (sel) {
  const out = [];
  (function lauf(e) { for (const k of e.kinder) { if (k.matches(sel)) out.push(k); lauf(k); } })(this);
  return out;
};
"""


def _scroll_js() -> str:
    return _DOM + _block() + "".join(_funktion(n) for n in (
        "_scrollSchluessel", "_scrollMerken", "_scrollZurueck"))


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_die_neu_gebaute_tabelle_steht_wo_die_alte_stand():
    js = _scroll_js() + """
      const anker = new El('live-content');
      const alt = anker.dazu(new El('', 'live-table-wrap'));
      alt.scrollLeft = 140;
      _scrollMerken({target: alt});
      // innerHTML: der alte Wrapper faellt weg, ein neuer mit Stellung 0 kommt
      anker.kinder = [];
      const neu = anker.dazu(new El('', 'live-table-wrap'));
      _scrollZurueck(neu);
      console.log(JSON.stringify(neu.scrollLeft));
    """
    assert _node(js) == 140


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_auch_die_senkrechte_stellung_einer_begrenzten_liste_bleibt():
    js = _scroll_js() + """
      const anker = new El('friesen-events');
      const alt = anker.dazu(new El('', 'live-table-wrap'));
      alt.scrollTop = 80;
      _scrollMerken({target: alt});
      anker.kinder = [];
      const neu = anker.dazu(new El('', 'live-table-wrap'));
      _scrollZurueck(anker);                 // der Beobachter meldet oft den Elternknoten
      console.log(JSON.stringify([neu.scrollLeft, neu.scrollTop]));
    """
    assert _node(js) == [0, 80]


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_eine_tabelle_erbt_nie_die_stellung_einer_anderen():
    """Zwei Tabellen im selben Bereich und eine in einem anderen -- jede fuer sich."""
    js = _scroll_js() + """
      const a = new El('bummel-view'), b = new El('stats-content');
      const a1 = a.dazu(new El('', 'live-table-wrap')), a2 = a.dazu(new El('', 'live-table-wrap'));
      const b1 = b.dazu(new El('', 'table-scroll'));
      a2.scrollLeft = 90; _scrollMerken({target: a2});
      a.kinder = []; b.kinder = [];
      const n1 = a.dazu(new El('', 'live-table-wrap')), n2 = a.dazu(new El('', 'live-table-wrap'));
      const m1 = b.dazu(new El('', 'table-scroll'));
      _scrollZurueck(a); _scrollZurueck(b);
      console.log(JSON.stringify([n1.scrollLeft, n2.scrollLeft, m1.scrollLeft]));
    """
    assert _node(js) == [0, 90, 0]


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_fremde_scroll_ereignisse_werden_nicht_gemerkt():
    js = _scroll_js() + """
      const anker = new El('live-content');
      const div = anker.dazu(new El('', 'irgendwas'));
      div.scrollLeft = 50;
      _scrollMerken({target: div});
      _scrollMerken({target: {nodeType: 9}});    // Scrollen des Dokuments selbst
      console.log(JSON.stringify(Object.keys(_scrollStand).length));
    """
    assert _node(js) == 0


# --- Kein Umbau unter dem Finger ----------------------------------------------------------

def _finger_js() -> str:
    return _DOM + """
      let jetzt = 0; const uhren = [];
      Date.now = () => jetzt;
      global.setTimeout = (fn, ms) => { uhren.push({fn, bis: jetzt + ms}); return uhren.length; };
      global.clearTimeout = (n) => { if (uhren[n - 1]) uhren[n - 1].fn = null; };
      function vorspulen(ms) {
        jetzt += ms;
        for (const u of uhren.slice()) if (u.fn && u.bis <= jetzt) { const f = u.fn; u.fn = null; f(); }
      }
      const anker = new El('live-content');
      const wrap = anker.dazu(new El('', 'live-table-wrap'));
      const zelle = wrap.dazu(new El('', 'td'));
      const knopf = new El('', 'tab');
    """ + _block() + "".join(_funktion(n) for n in (
        "_scrollSchluessel", "_scrollMerken", "_fingerRunter", "_fingerHoch", "_fingerFrei",
        "_wennFingerFrei", "_imTakt"))


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_ohne_finger_laeuft_der_takt_sofort():
    js = _finger_js() + """
      let n = 0; const takt = _imTakt(() => n++);
      takt(); takt();
      console.log(JSON.stringify(n));
    """
    assert _node(js) == 2


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_unter_dem_finger_wartet_der_takt_bis_nach_dem_loslassen():
    js = _finger_js() + """
      let n = 0; const takt = _imTakt(() => n++);
      _fingerRunter({target: zelle});
      takt(); takt(); takt();                     // drei Takte fallen in die Wischbewegung
      const waehrend = n;
      _fingerHoch();
      const gleichNachDemLoslassen = n;           // der Schwung laeuft noch
      vorspulen(_FINGER_NACHLAUF_MS);
      console.log(JSON.stringify([waehrend, gleichNachDemLoslassen, n]));
    """
    # Nachgeholt wird genau EINMAL: drei aufgelaufene Takte sind ein einziger Neubau.
    assert _node(js) == [0, 0, 1]


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_der_schwung_nach_dem_loslassen_verlaengert_die_wartezeit():
    js = _finger_js() + """
      let n = 0; const takt = _imTakt(() => n++);
      _fingerRunter({target: zelle}); takt(); _fingerHoch();
      vorspulen(_FINGER_NACHLAUF_MS - 50);
      wrap.scrollLeft = 30; _scrollMerken({target: wrap});   // die Tabelle rollt noch aus
      vorspulen(_FINGER_NACHLAUF_MS - 50);
      const nochImSchwung = n;
      vorspulen(100);
      console.log(JSON.stringify([nochImSchwung, n]));
    """
    assert _node(js) == [0, 1]


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_ein_finger_ausserhalb_der_tabellen_haelt_nichts_auf():
    js = _finger_js() + """
      let n = 0; const takt = _imTakt(() => n++);
      _fingerRunter({target: knopf});
      takt();
      console.log(JSON.stringify(n));
    """
    assert _node(js) == 1


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_ein_verlorenes_loslassen_legt_die_seite_nicht_still():
    """touchend erreicht das Dokument nicht, wenn sein Ziel inzwischen aus dem DOM entfernt
    wurde. Dann darf die Sperre nicht ewig halten."""
    js = _finger_js() + """
      let n = 0; const takt = _imTakt(() => n++);
      _fingerRunter({target: zelle});
      takt();
      jetzt += _FINGER_HOECHSTENS_MS + 1;
      takt();
      console.log(JSON.stringify(n));
    """
    # Der aufgestaute Takt und der neue sind derselbe -- er laeuft einmal.
    assert _node(js) == 1


# --- Verdrahtung ---------------------------------------------------------------------------

@pytest.mark.parametrize("aufruf", [
    "fetchAndRenderPrefiles", "fetchAndRenderTeamspeak", "fetchBummelActive",
    "fetchKutterActive", "_reddungTakt", "refreshLiveData", "_refreshKutterDetail",
])
def test_jeder_selbsttaetige_takt_wartet_auf_den_finger(aufruf):
    assert re.search(rf"setInterval\(_imTakt\({re.escape(aufruf)}\)", _INDEX), aufruf
    assert not re.search(rf"setInterval\({re.escape(aufruf)}\s*,", _INDEX), aufruf


def test_der_live_push_und_die_flugliste_warten_ebenfalls():
    sse = _INDEX[_INDEX.index("msg.type === 'positions'"):_INDEX.index("msg.type === 'bruegge'")]
    assert "_wennFingerFrei(_liveZeichnen)" in sse and "renderLiveTable(" not in sse
    plan = _funktion("scheduleFlightsRefresh")
    assert "_wennFingerFrei(" in plan
    live = _funktion("refreshLiveData")
    assert "_wennFingerFrei(_liveZeichnen)" in live and "renderLiveTable(" not in live


def test_der_anzeigetakt_der_live_tabelle_wartet_ebenfalls():
    m = re.search(r"setInterval\(_imTakt\(\(\) => \{\s*if \(liveData\.length > 0\) _liveZeichnen\(\);\s*\}\), 10000\)", _INDEX)
    assert m


def test_der_beobachter_haengt_am_ganzen_dokument():
    halten = _funktion("_scrollStellungHalten")
    assert "_scrollZurueck(" in halten and "observe(document.body" in halten
    assert "addEventListener('scroll', _scrollMerken, true)" in halten
    for ereignis in ("touchstart", "touchend", "touchcancel", "mousedown", "mouseup"):
        assert f"'{ereignis}'" in halten, ereignis


def test_der_block_steht_vor_seinem_ersten_aufruf():
    """Ein const hinter dem ersten Top-Level-Aufruf legt die ganze Seite lahm (TDZ)."""
    erst = _INDEX.index("const _SCROLL_WRAPS")
    assert erst < _INDEX.index("\n_scrollStellungHalten();")
    assert erst < _INDEX.index("\ninitFromUrl();")
    assert erst < _INDEX.index("\nconnectSSE();")
