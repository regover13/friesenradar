# -*- coding: utf-8 -*-
"""Eingrenzung, frühe Rauchfackel und Licht am Fuß jeder Fackel (Nutzer, 28.09.2026).

* **Eingrenzung statt kleinerer Sektor.** Wird das Wrack übersehen, grenzt der Veranstalter
  ein Rechteck im Sektor ein. Der Sektor bleibt, wie er ist -- damit bleiben abgesuchte Zellen,
  Anteile und Badges unberührt. Ein echt verkleinerter Sektor bekäme ein neues Raster, und alles
  außerhalb ginge verloren.
* **Frühe Rauchfackel per Knopf**, Friesen-Dunkelblau (`rauch_navy`), dort, wo später die
  orange steht, und für alle sichtbar. Beim Fund ersetzt die orange sie.
* **Ein Licht am Fuß jeder Rauchsäule**, genau an derselben Stelle, Tag und Nacht.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.main as main
from app.database import (
    create_reddung_event, get_connection, get_progress_snapshot, get_reddung_event,
    init_db, reddung_objekte_abgleichen, set_reddung_aufgeloest, set_reddung_aufgenommen,
    set_reddung_gefunden, write_progress_snapshot,
)
from tests.test_reddung_api import FakeReq, SEKTOR, db  # noqa: F401  (Fixture)

HAV = {"havarist_lat": 53.72, "havarist_lon": 7.25}
ENG = {"eng_sued": 53.65, "eng_west": 7.10, "eng_nord": 53.80, "eng_ost": 7.40}
OHNE_ENG = {"eng_sued": None, "eng_west": None, "eng_nord": None, "eng_ost": None}
_WURZEL = Path(__file__).resolve().parents[1]
_INDEX = (_WURZEL / "app" / "static" / "index.html").read_text(encoding="utf-8")
_ADMIN = (_WURZEL / "app" / "static" / "admin.html").read_text(encoding="utf-8")


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _laufend():
    j = datetime.now(timezone.utc)
    return {"dtstart": _iso(j - timedelta(hours=1)), "dtend": _iso(j + timedelta(hours=1))}


@pytest.fixture(autouse=True)
def ohne_netz(monkeypatch):
    async def keine(lat, lon):
        return None
    monkeypatch.setattr(main, "_gelaende_ft", keine)


@pytest.fixture
def pushes(monkeypatch, db):
    gesendet = []
    poller = SimpleNamespace(broadcast_notify=lambda d, c, p, **kw: gesendet.append(p))
    monkeypatch.setattr(main.app.state, "poller", poller, raising=False)

    async def web_push(*a, **kw):
        pass
    monkeypatch.setattr(main, "send_web_push", web_push)
    return gesendet


class Req(FakeReq):
    def __init__(self, body=None):
        super().__init__(body=body or {})
        self.app = main.app


def _anlegen(**extra):
    body = {"name": "Eifel", **SEKTOR, **HAV, **extra}
    body.setdefault("dtstart", "2099-01-01T17:00:00Z")
    return asyncio.run(main.admin_create_reddung_event(Req(body)))["id"]


def _aendern(eid, body):
    async def lauf():
        erg = await main.admin_update_reddung_event(Req(body), eid)
        await asyncio.sleep(0)
        return erg
    return asyncio.run(lauf())


def _ev(db, eid):
    c = get_connection(db)
    try:
        return dict(get_reddung_event(c, eid))
    finally:
        c.close()


# === Eingrenzung ============================================================================

def test_die_eingrenzung_wird_gespeichert_und_oeffentlich_ausgeliefert(db):
    eid = _anlegen(**ENG, **_laufend())
    liste = main.reddung_events()
    assert liste[0]["eingrenzung"] == {"sued": 53.65, "west": 7.10, "nord": 53.80, "ost": 7.40}
    raster = main.reddung_raster_endpunkt(eid)
    assert raster["eingrenzung"] == liste[0]["eingrenzung"]
    assert raster["sektor"]["sued"] == SEKTOR["sued"], "der Sektor bleibt, wie er ist"


def test_ohne_eingrenzung_steht_null_da(db):
    eid = _anlegen(**_laufend())
    assert main.reddung_events()[0]["eingrenzung"] is None
    assert main.reddung_raster_endpunkt(eid)["eingrenzung"] is None


def test_die_eingrenzung_laesst_sich_aufheben(db):
    eid = _anlegen(**ENG)
    _aendern(eid, OHNE_ENG)
    assert _ev(db, eid)["eng_sued"] is None


@pytest.mark.parametrize("falsch,grund", [
    ({"eng_sued": 53.65, "eng_west": 7.10}, "unvollständig"),
    ({**ENG, "eng_sued": 53.85, "eng_nord": 53.70}, "verdreht"),
    ({**ENG, "eng_ost": 7.60}, "innerhalb des Sektors"),
    ({"eng_sued": 53.80, "eng_west": 7.10, "eng_nord": 53.85, "eng_ost": 7.40}, "Havarist"),
], ids=["halb", "verdreht", "ueber_den_sektor", "ohne_havarist"])
def test_eine_unbrauchbare_eingrenzung_wird_abgewiesen(db, falsch, grund):
    eid = _anlegen()
    with pytest.raises(HTTPException) as e:
        _aendern(eid, falsch)
    assert e.value.status_code == 400 and grund in e.value.detail, e.value.detail


def test_die_eingrenzung_laesst_die_bilanz_stehen(db):
    """Der Kern von 3A: abgesuchte Zellen bleiben -- der Stand wird nicht verworfen."""
    eid = _anlegen()
    c = get_connection(db)
    try:
        write_progress_snapshot(c, "reddung", eid,
                                {"v": 1, "bis": "2026-09-25T17:30:00Z",
                                 "treffer": {"z0_0": [111, "2026-09-25T17:10:00Z"]},
                                 "je_pilot": {"111": 1}, "fund": None}, "2026-09-25T17:30:00Z")
        c.commit()
    finally:
        c.close()
    _aendern(eid, ENG)
    c = get_connection(db)
    try:
        assert get_progress_snapshot(c, "reddung", eid) is not None
    finally:
        c.close()


def test_eine_neue_eingrenzung_im_laufenden_event_geht_per_push_raus(db, pushes):
    eid = _anlegen(**_laufend())
    _aendern(eid, ENG)
    assert len(pushes) == 1 and "eingegrenzt" in pushes[0]["body"]
    pushes.clear()
    _aendern(eid, ENG)                   # unverändert gespeichert: nichts Neues
    assert pushes == []
    _aendern(eid, OHNE_ENG)              # aufgehoben: keine Meldung „eingegrenzt"
    assert pushes == []


# === Frühe Rauchfackel =======================================================================

def _zuenden(eid):
    return asyncio.run(main.admin_reddung_signal(Req(), eid))


def test_der_knopf_zuendet_die_fackel(db):
    eid = _anlegen(**_laufend())
    assert _zuenden(eid)["status"] == "ok"
    assert _ev(db, eid)["signal_am"]
    assert main.reddung_events()[0]["signal_am"]


def test_zweimal_zuenden_aendert_die_zeit_nicht(db):
    eid = _anlegen(**_laufend())
    _zuenden(eid)
    erst = _ev(db, eid)["signal_am"]
    _zuenden(eid)
    assert _ev(db, eid)["signal_am"] == erst


def test_ohne_havarist_gibt_es_nichts_zu_zuenden(db):
    body = {"name": "Eifel", "dtstart": "2099-01-01T17:00:00Z", **SEKTOR}
    eid = asyncio.run(main.admin_create_reddung_event(Req(body)))["id"]
    with pytest.raises(HTTPException) as e:
        _zuenden(eid)
    assert e.value.status_code == 400


def test_nach_dem_fund_braucht_es_keine_fackel_mehr(db):
    eid = _anlegen(**_laufend())
    c = get_connection(db)
    try:
        set_reddung_gefunden(c, eid, _iso(datetime.now(timezone.utc)), 111)
        c.commit()
    finally:
        c.close()
    with pytest.raises(HTTPException) as e:
        _zuenden(eid)
    assert e.value.status_code == 400


def test_der_knopf_verlangt_den_admin(db):
    eid = _anlegen(**_laufend())
    fremd = Req()
    fremd.cookies = {}
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.admin_reddung_signal(fremd, eid))
    assert e.value.status_code in (401, 403)


# === Objekte: Fackel und Licht ================================================================

@pytest.fixture()
def conn(tmp_path):
    p = str(tmp_path / "o.db")
    init_db(p)
    c = get_connection(p)
    for art in ("flugzeug_echo", "rauch_navy", "rauch_signalorange", "rauch_hellblau",
                "rauch_signalrot", "licht"):
        c.execute("INSERT OR REPLACE INTO bruegge_art (art, bedeutung, status, angelegt_am) "
                  "VALUES (?,?,'aktiv','2026-09-20T00:00:00Z')", (art, art))
        for sim in ("msfs2020", "msfs2024", "xplane12"):
            c.execute("INSERT OR REPLACE INTO bruegge_katalog (simulator, titel, art, rang, "
                      "status, quelle) VALUES (?,?,?,1,'aktiv','bord')", (sim, f"{art}-{sim}", art))
    yield c
    c.close()


def _probe(conn, **extra):
    eid = create_reddung_event(conn, name="Probe", dtstart="2026-09-25T17:00:00Z",
                               dtend="2026-09-25T22:00:00Z", **SEKTOR, **HAV, **extra)
    return get_reddung_event(conn, eid)


def _objekte(conn):
    return {r[0]: (r[1], r[2], r[3], r[4]) for r in conn.execute(
        "SELECT id, art, lat, lon, nur_nah_m FROM bruegge_soll")}


def test_die_fruehe_fackel_ist_dunkelblau_und_fuer_alle_sichtbar(conn):
    ev = _probe(conn, signal_am="2026-09-25T18:00:00Z")
    reddung_objekte_abgleichen(conn, ev)
    o = _objekte(conn)
    art, lat, lon, nah = o["reddung-%d-fackel" % ev["id"]]
    assert art == "rauch_navy" and nah is None
    assert o["reddung-%d-havarist" % ev["id"]][3] is not None, "das Wrack bleibt nah-gesperrt"


def test_beim_fund_ersetzt_die_orange_die_dunkelblaue(conn):
    ev = _probe(conn, signal_am="2026-09-25T18:00:00Z")
    reddung_objekte_abgleichen(conn, ev)
    vorher = _objekte(conn)["reddung-%d-fackel" % ev["id"]]
    set_reddung_gefunden(conn, ev["id"], "2026-09-25T18:10:00Z", 111)
    reddung_objekte_abgleichen(conn, get_reddung_event(conn, ev["id"]))
    nachher = _objekte(conn)["reddung-%d-fackel" % ev["id"]]
    assert nachher[0] == "rauch_signalorange"
    assert nachher[1:3] == vorher[1:3], "dieselbe Stelle"


@pytest.mark.parametrize("stufe", ["signal", "gefunden", "aufgenommen", "aufgeloest"])
def test_am_fuss_jeder_fackel_steht_ein_licht(conn, stufe):
    ev = _probe(conn, signal_am="2026-09-25T18:00:00Z" if stufe == "signal" else None)
    if stufe != "signal":
        set_reddung_gefunden(conn, ev["id"], "2026-09-25T18:10:00Z", 111)
    if stufe in ("aufgenommen", "aufgeloest"):
        set_reddung_aufgenommen(conn, ev["id"], "2026-09-25T18:20:00Z", 111)
    if stufe == "aufgeloest":
        set_reddung_aufgeloest(conn, ev["id"], "2026-09-25T18:40:00Z")
    reddung_objekte_abgleichen(conn, get_reddung_event(conn, ev["id"]))
    o = _objekte(conn)
    fackel = o["reddung-%d-fackel" % ev["id"]]
    licht = o["reddung-%d-licht" % ev["id"]]
    assert licht[0] == "licht"
    assert licht[1:4] == fackel[1:4], "exakt dieselbe Stelle, dieselbe Sichtbarkeit"


def test_ohne_fackel_kein_licht(conn):
    ev = _probe(conn)
    reddung_objekte_abgleichen(conn, ev)
    assert not any(k.endswith("-licht") for k in _objekte(conn))


def test_beim_loeschen_geht_das_licht_mit(conn):
    ev = _probe(conn, signal_am="2026-09-25T18:00:00Z")
    reddung_objekte_abgleichen(conn, ev)
    reddung_objekte_abgleichen(conn, ev, weg=True)
    assert _objekte(conn) == {}


# === Oberfläche ===============================================================================

def _js(name, quelle=_INDEX):
    m = re.search(rf"^(async )?function {re.escape(name)}\(", quelle, flags=re.M)
    assert m, name
    return quelle[m.start():quelle.index("\n}\n", m.start()) + 3]


def test_die_live_karte_zeichnet_die_eingrenzung_und_nimmt_sie_wieder_weg():
    z = _js("_reddungZeichnen")
    assert "d.eingrenzung" in z and "_reddungEingrenzungStil" in z
    assert "removeLayer(z.eng)" in z


def test_die_event_karte_zeichnet_die_eingrenzung():
    assert "d.eingrenzung" in _js("_reddungEventKarte")


def test_zur_karte_springt_auf_die_eingrenzung():
    assert "r.eingrenzung" in _js("reddungAufKarte")


def test_live_block_und_bilanz_sagen_es_an():
    hinweise = _js("_reddungHinweiseHtml")
    assert "r.eingrenzung" in hinweise and "r.signal_am" in hinweise
    assert "st.gefunden" in hinweise, "nach dem Fund ist beides erledigt"
    assert "_reddungHinweiseHtml(r)" in _js("_reddungBannerBlock")
    assert "_reddungHinweiseHtml(r)" in _js("_reddungBilanzHtml")


def test_der_admin_kann_eingrenzen_aufheben_und_zuenden():
    assert re.search(r'name="rd-ziel" value="e1"', _ADMIN)
    assert re.search(r'name="rd-ziel" value="e2"', _ADMIN)
    for feld in ("rd-eng-sued", "rd-eng-west", "rd-eng-nord", "rd-eng-ost"):
        assert f'id="{feld}"' in _ADMIN, feld
    speichern = _ADMIN[_ADMIN.index("async function rdSpeichern"):_ADMIN.index("function _rdFormSchliessen")]
    assert "eng_sued: _rdZahlOderNull('rd-eng-sued')" in speichern
    assert "function rdEingrenzungAufheben(" in _ADMIN
    assert "function rdSignal(" in _ADMIN
    assert "'/api/admin/reddung/events/' + id + '/signal'" in _ADMIN


# === Befunde aus der Prüfung durch Fable (28.09.2026) ========================================

def test_faellt_ein_event_von_der_karte_geht_auch_die_eingrenzung(db):
    """Befund 1: Rahmen und Fläche verschwanden, das gelbe Rechteck blieb bis zum Neuladen."""
    abgleich = _js("_reddungKarteAbgleichen")
    assert "removeLayer(z.eng)" in abgleich


def test_eine_sektoraenderung_heisst_nicht_eingegrenzt(db, pushes):
    """Befund 2: Auch ein vergrößerter Sektor meldete „eingegrenzt"."""
    eid = _anlegen(**_laufend())
    _aendern(eid, {"sued": 53.50})
    assert len(pushes) == 1
    assert "Suchsektor" in pushes[0]["body"] and "eingegrenzt" not in pushes[0]["body"]


def test_waehrend_des_hoehenabrufs_ist_keine_verbindung_offen(db, monkeypatch):
    """Befund 3: Keine Datenbankverbindung über einen Netzabruf (CLAUDE.md, Datenbank)."""
    offen = []
    echt = main.get_connection

    class Verfolgt:
        def __init__(self, c):
            self._c = c
            offen.append(self)

        def close(self):
            offen.remove(self)
            return self._c.close()

        def __getattr__(self, n):
            return getattr(self._c, n)

    monkeypatch.setattr(main, "get_connection", lambda p: Verfolgt(echt(p)))
    bei_abruf = []

    async def hoehe(lat, lon):
        bei_abruf.append(len(offen))
        return 1864.0
    monkeypatch.setattr(main, "_gelaende_ft", hoehe)
    eid = _anlegen()
    _aendern(eid, {"havarist_lat": 53.73, "havarist_lon": 7.26})
    assert bei_abruf and all(n == 0 for n in bei_abruf), bei_abruf
    assert _ev(db, eid)["havarist_grund_ft"] == 1864.0


def test_signal_am_verwirft_die_bilanz_nicht():
    """Befund 4."""
    assert "signal_am" in main._REDDUNG_OHNE_RECHNUNG


def test_die_fackel_geht_nur_waehrend_des_events(db):
    """Befund 6: Vor dem Start hätte der Knopf die Stelle allen verraten."""
    eid = _anlegen()                                     # beginnt 2099
    with pytest.raises(HTTPException) as e:
        _zuenden(eid)
    assert e.value.status_code == 400 and "läuft" in e.value.detail
    assert _ev(db, eid)["signal_am"] is None


def test_ein_abgeschlossener_fall_ohne_fund_nennt_keine_orange_fackel(db):
    """Befund 5: Aufgelöst ohne Fund brennt die rote, nicht die orange."""
    eid = _anlegen(**_laufend())
    c = get_connection(db)
    try:
        set_reddung_aufgeloest(c, eid, _iso(datetime.now(timezone.utc)))
        c.commit()
    finally:
        c.close()
    with pytest.raises(HTTPException) as e:
        _zuenden(eid)
    assert "abgeschlossen" in e.value.detail and "orange" not in e.value.detail


def test_ein_vergangenes_event_behaelt_beim_verschieben_seine_hoehe(db, monkeypatch):
    """Befund 8: Schlug der Abruf fehl, stand danach NULL -- auch wo vorher gemessen war."""
    eid = _anlegen(dtstart="2020-01-01T17:00:00Z", dtend="2020-01-01T19:00:00Z")
    c = get_connection(db)
    try:
        from app.database import reddung_grund_merken
        reddung_grund_merken(c, eid, 1900.0, "gemessen")
        c.commit()
    finally:
        c.close()
    abrufe = []

    async def hoehe(lat, lon):
        abrufe.append(1)
        return None
    monkeypatch.setattr(main, "_gelaende_ft", hoehe)
    _aendern(eid, {"havarist_lat": 53.73, "havarist_lon": 7.26})
    ev = _ev(db, eid)
    assert (ev["havarist_grund_ft"], ev["havarist_grund_quelle"]) == (1900.0, "gemessen")
    assert abrufe == []


def test_bearbeiten_beginnt_ohne_geklickte_ecken():
    """Befund 10: Ecken aus Event A mischten sich in das Rechteck von Event B."""
    bearbeiten = _ADMIN[_ADMIN.index("function rdEdit("):_ADMIN.index("async function rdCopyLink")]
    assert "_rdEcken = [null, null]" in bearbeiten
    assert "_rdEngEcken = [null, null]" in bearbeiten


def test_ein_titel_nur_im_2024er_bestand_gilt_auch_fuer_msfs_2020(tmp_path):
    """Die Katalog-Spalte `simulator` nennt, WO ein Titel gefunden wurde -- nicht, wo er läuft.
    MSFS 2020 und 2024 schöpfen aus einem Vorrat (`bruegge_titel_fuer`).

    Am 28.09.2026 las eine Prüfung aus „FrsLicht_Warm steht nur bei msfs2024", MSFS-2020-Piloten
    sähen weder Fackel noch Licht -- und das ging ungeprüft an den Nutzer weiter. Hier genau
    dieser Stand: Licht und Fackel nur mit msfs2024- und xplane12-Zeilen, und trotzdem EINE
    Zeile für alle Simulatoren."""
    p = str(tmp_path / "k.db")
    init_db(p)
    c = get_connection(p)
    try:
        for art in ("flugzeug_echo", "rauch_navy", "licht"):
            c.execute("INSERT OR REPLACE INTO bruegge_art (art, bedeutung, status, angelegt_am) "
                      "VALUES (?,?,'aktiv','2026-09-20T00:00:00Z')", (art, art))
            for sim in ("msfs2024", "xplane12"):            # KEINE msfs2020-Zeile
                c.execute("INSERT OR REPLACE INTO bruegge_katalog (simulator, titel, art, rang, "
                          "status, quelle) VALUES (?,?,?,1,'aktiv','community')",
                          (sim, f"{art}-{sim}", art))
        from app.database import _art_je_simulator
        assert _art_je_simulator(c, "licht")["msfs2020"] == "licht"
        ev = _probe(c, signal_am="2026-09-25T18:00:00Z")
        reddung_objekte_abgleichen(c, ev)
        zeilen = c.execute("SELECT id, simulator FROM bruegge_soll WHERE art IN "
                           "('licht','rauch_navy')").fetchall()
        assert sorted(tuple(z) for z in zeilen) == [(f"reddung-{ev['id']}-fackel", None),
                                  (f"reddung-{ev['id']}-licht", None)], \
            "simulator NULL = für alle drei, auch MSFS 2020"
    finally:
        c.close()


# === Sicherheitsabfrage vor dem Setzen einer Eingrenzung (Nutzer, 28.09.2026) ================

import shutil
import subprocess

_NODE = shutil.which("node")


def _admin_js(name):
    m = re.search(rf"^    (async )?function {re.escape(name)}\(", _ADMIN, flags=re.M)
    assert m, name
    return _ADMIN[m.start():_ADMIN.index("\n    }\n", m.start()) + 7]


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_gefragt_wird_nur_bei_einer_neuen_oder_verschobenen_eingrenzung():
    js = _admin_js("_rdEngNeu") + """
      const ev = {eng_sued: 53.65, eng_west: 7.10, eng_nord: 53.80, eng_ost: 7.40};
      const leer = {eng_sued: null, eng_west: null, eng_nord: null, eng_ost: null};
      console.log(JSON.stringify([
        _rdEngNeu(null, [53.65, 7.10, 53.80, 7.40]),   // neues Event mit Eingrenzung
        _rdEngNeu(leer, [53.65, 7.10, 53.80, 7.40]),   // erstmals gesetzt
        _rdEngNeu(ev,   [53.65, 7.10, 53.80, 7.40]),   // unverändert gespeichert
        _rdEngNeu(ev,   [53.66, 7.10, 53.80, 7.40]),   // verschoben
        _rdEngNeu(ev,   [null, null, null, null]),     // aufgehoben
        _rdEngNeu(null, [null, null, null, null]),     // keine
      ]));
    """
    erg = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert erg.returncode == 0, erg.stderr
    assert json.loads(erg.stdout.strip().splitlines()[-1]) == [True, True, False, True, False, False]


def test_speichern_fragt_vorher_nach():
    speichern = _admin_js("rdSpeichern")
    frage = speichern.index("_rdEngNeu(")
    assert "confirm(" in speichern[frage:]
    assert frage < speichern.index("await api('POST', pfad, koerper)"), "vor dem Absenden"
    assert "noch nicht begonnen" in speichern


def test_der_haken_steht_im_formular_und_ist_vorgabe_aus():
    assert re.search(r'<input type="checkbox" id="rd-signal-ab-start"(?![^>]*checked)[^>]*>', _ADMIN)
    assert "direkt mit dunkelblauem Rauchsignal starten" in _ADMIN
    assert "signal_ab_start: document.getElementById('rd-signal-ab-start').checked ? 1 : 0" in _ADMIN
    assert "getElementById('rd-signal-ab-start').checked = !!ev.signal_ab_start" in _ADMIN
    # Ein neues Event beginnt wieder ohne Haken.
    schliessen = _admin_js("_rdFormSchliessen")
    assert "getElementById('rd-signal-ab-start')" in schliessen and ".checked = false" in schliessen


def test_der_haken_verwirft_die_bilanz_nicht_und_wird_gespeichert(db):
    assert "signal_ab_start" in main._REDDUNG_OHNE_RECHNUNG
    eid = _anlegen(signal_ab_start=1)
    assert _ev(db, eid)["signal_ab_start"] == 1
    with pytest.raises(HTTPException):
        _aendern(eid, {"signal_ab_start": 5})
