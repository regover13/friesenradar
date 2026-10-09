# -*- coding: utf-8 -*-
"""Die Schnittstellen der Deichkontrolle (10.10.2026).

Aufbau wie tests/test_reddung_api.py: FakeReq statt TestClient, Funktionen direkt gerufen.
Spec: docs/superpowers/specs/2026-10-10-deichkontrolle-design.md.
"""
from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.database as dbm
import app.main as main
from app.auth import ADMIN_COOKIE, CONFIRM_COOKIE, make_admin_token, make_confirm_token
from app.database import get_connection, get_strecken_event, init_db, strecke_fortschreiben

SECRET = "s3cr3t"
PW = "test-admin-pw"
TOKEN = make_admin_token(SECRET, PW)
CONFIRM_TOKEN = make_confirm_token(SECRET, PW, 9_999_999_999)

LAT, LON = 53.72, 7.25
KM_LON = 111.32 * math.cos(math.radians(LAT))


def _ost(km):
    return LON + km / KM_LON


GERADE = [[LAT, LON], [LAT, _ost(10.0)]]


class FakeReq:
    def __init__(self, cookies=None, body=None):
        self.cookies = cookies if cookies is not None else {
            ADMIN_COOKIE: TOKEN, CONFIRM_COOKIE: CONFIRM_TOKEN,
        }
        self._body = body or {}
        self.headers = {}

    async def json(self):
        return self._body


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _laufend() -> dict:
    jetzt = datetime.now(timezone.utc)
    return {"dtstart": _iso(jetzt - timedelta(hours=1)), "dtend": _iso(jetzt + timedelta(hours=1))}


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    init_db(p)
    monkeypatch.setattr(
        main, "get_settings",
        lambda: SimpleNamespace(DB_PATH=p, CALLSIGN_PREFIX="FRS", SECRET_KEY=SECRET,
                                ADMIN_PASSWORD=PW))
    monkeypatch.setattr(dbm, "_spur_sektoren", (0.0, []))
    return p


@pytest.fixture
def modell(monkeypatch):
    """Das Höhenmodell als Attrappe: zählt die Abrufe und liefert 100 ft je Stelle."""
    rufe = []

    async def viele(punkte):
        rufe.append(list(punkte))
        return [100.0] * len(punkte)

    monkeypatch.setattr(main, "_gelaende_ft_viele", viele)
    return rufe


@pytest.fixture
def modell_aus(monkeypatch):
    async def nichts(punkte):
        return None

    monkeypatch.setattr(main, "_gelaende_ft_viele", nichts)


def _anlegen(**extra):
    body = {"name": "Probe", **_laufend(), "punkte": GERADE, **extra}
    return asyncio.run(main.admin_create_strecken_event(FakeReq(body=body)))


def _aendern(eid, **body):
    return asyncio.run(main.admin_update_strecken_event(FakeReq(body=body), eid))


def _ev(db, eid):
    c = get_connection(db)
    try:
        return get_strecken_event(c, eid)
    finally:
        c.close()


def _fehler(aufruf) -> HTTPException:
    with pytest.raises(HTTPException) as e:
        aufruf()
    return e.value


# --- Anlegen ---------------------------------------------------------------------------------

def test_anlegen_holt_die_gelaendehoehe_je_abschnitt(db, modell):
    antwort = _anlegen()
    assert antwort["status"] == "ok" and antwort["grund_fehlt"] is False
    assert len(modell) == 1 and len(modell[0]) == 10, "ein Abruf, eine Stelle je Abschnitt"
    ev = _ev(db, antwort["id"])
    assert json.loads(ev["grund_json"]) == [100.0] * 10 and ev["grund_geholt_am"]
    assert ev["korridor_m"] == 500 and ev["hoehe_max_ft"] == 1000


def test_die_stellen_sind_die_mittelpunkte_der_abschnitte(db, modell):
    _anlegen()
    assert modell[0][0] == (pytest.approx(LAT), pytest.approx(_ost(0.5), abs=1e-5))
    assert modell[0][9] == (pytest.approx(LAT), pytest.approx(_ost(9.5), abs=1e-5))


def test_scheitert_das_hoehenmodell_wird_trotzdem_gespeichert(db, modell_aus):
    antwort = _anlegen()
    assert antwort["grund_fehlt"] is True
    assert _ev(db, antwort["id"])["grund_json"] is None


def test_ohne_admin_gibt_es_nichts(db, modell):
    assert _fehler(lambda: asyncio.run(main.admin_create_strecken_event(
        FakeReq(cookies={}, body={"punkte": GERADE, **_laufend()})))).status_code == 401
    assert _fehler(lambda: main.admin_list_strecken_events(FakeReq(cookies={}))).status_code == 401


@pytest.mark.parametrize("extra, teil", [
    ({"punkte": [[LAT, LON]]}, "mindestens zwei Punkte"),
    ({"korridor_m": 10}, "Korridor muss zwischen"),
    ({"korridor_m": "breit"}, "Zahl"),
    ({"hoehe_max_ft": 5}, "Die Höhe muss zwischen"),
    ({"gs_min_kt": 200}, "Mindestgeschwindigkeit muss unter"),
    ({"dtend": "2000-01-01T00:00:00Z"}, "Enddatum"),
    ({"korridor_m": 50, "punkte": [[LAT, LON], [LAT, LON + 5.0]]}, "höchstens 2000"),
])
def test_unsinnige_eingaben_ergeben_400_mit_einem_satz(db, modell, extra, teil):
    f = _fehler(lambda: _anlegen(**extra))
    assert f.status_code == 400 and teil in f.detail
    assert modell == [], "vor dem Höhenmodell wird geprüft"


def test_ohne_strecke_oder_beginn_wird_nicht_angelegt(db, modell):
    assert _fehler(lambda: asyncio.run(main.admin_create_strecken_event(
        FakeReq(body={"name": "x", **_laufend()})))).status_code == 400
    assert _fehler(lambda: asyncio.run(main.admin_create_strecken_event(
        FakeReq(body={"name": "x", "punkte": GERADE})))).status_code == 400


# --- Ändern ----------------------------------------------------------------------------------

def _mit_stand(db, eid):
    """Vier Abschnitte abfliegen und fortschreiben."""
    c = get_connection(db)
    try:
        ev = get_strecken_event(c, eid)
        start = datetime.strptime(ev["dtstart"], "%Y-%m-%dT%H:%M:%SZ")
        for i in range(77):
            c.execute("INSERT OR REPLACE INTO bruegge_spur (cid, ts, lat, lon, alt_msl_ft, gs_kt) "
                      "VALUES (7, ?, ?, ?, 600, 100)",
                      (_iso(start + timedelta(seconds=10 + i)), LAT, _ost(i * 0.05)))
        strecke_fortschreiben(c, ev, bis=_iso(start + timedelta(seconds=200)))
        c.commit()
    finally:
        c.close()


def _abgedeckt(eid):
    return main.strecke_stand(eid)["abgedeckt"]


def test_ein_neuer_name_laesst_den_stand_stehen(db, modell):
    """Das Formular schickt IMMER alle Felder -- auch die unveränderten."""
    eid = _anlegen()["id"]
    _mit_stand(db, eid)
    ev = _ev(db, eid)
    antwort = _aendern(eid, name="Neuer Name", dtstart=ev["dtstart"], dtend=ev["dtend"],
                       punkte=GERADE, korridor_m=500, hoehe_max_ft=1000,
                       gs_max_kt=140, gs_min_kt=30)
    assert antwort["stand_verworfen"] is False
    assert _ev(db, eid)["name"] == "Neuer Name"
    assert _abgedeckt(eid) == 4
    assert len(modell) == 1, "die Strecke ist dieselbe -- kein zweiter Abruf beim Höhenmodell"


def test_eine_andere_hoehe_verwirft_den_stand_aber_nicht_die_gelaendehoehen(db, modell):
    eid = _anlegen()["id"]
    _mit_stand(db, eid)
    antwort = _aendern(eid, hoehe_max_ft=300)
    assert antwort["stand_verworfen"] is True and len(modell) == 1
    assert _abgedeckt(eid) == 0, "600 ft über Meer bei 100 ft Gelände sind jetzt zu hoch"


def test_ein_anderer_korridor_holt_die_gelaendehoehen_neu(db, modell):
    eid = _anlegen()["id"]
    antwort = _aendern(eid, korridor_m=1000)
    assert antwort["stand_verworfen"] is True and antwort["grund_fehlt"] is False
    assert len(modell) == 2 and len(modell[1]) == 5, "fünf Abschnitte zu 2 km"
    assert len(json.loads(_ev(db, eid)["grund_json"])) == 5


def test_eine_andere_strecke_holt_die_gelaendehoehen_neu(db, modell):
    eid = _anlegen()["id"]
    _aendern(eid, punkte=[[LAT, LON], [LAT, _ost(4.0)]])
    assert len(modell[1]) == 4
    assert len(_ev(db, eid)["punkte_json"]) > 0 and main.strecke_stand(eid)["abschnitte"] == 4


def test_scheitert_das_hoehenmodell_beim_aendern_ruht_die_rechnung(db, modell, monkeypatch):
    eid = _anlegen()["id"]

    async def nichts(punkte):
        return None

    monkeypatch.setattr(main, "_gelaende_ft_viele", nichts)
    antwort = _aendern(eid, korridor_m=1000)
    assert antwort["grund_fehlt"] is True and _ev(db, eid)["grund_json"] is None
    assert main.strecke_stand(eid)["ohne_grund"] is True


def test_ein_teil_update_wird_gegen_den_gespeicherten_stand_geprueft(db, modell):
    eid = _anlegen()["id"]
    f = _fehler(lambda: _aendern(eid, korridor_m=50, punkte=[[LAT, LON], [LAT, LON + 5.0]]))
    assert f.status_code == 400 and "höchstens 2000" in f.detail
    f = _fehler(lambda: _aendern(eid, gs_min_kt=140))
    assert f.status_code == 400
    assert _fehler(lambda: _aendern(999, name="x")).status_code == 404


def test_leeres_ende_heisst_mitternacht_des_folgetags(db, modell):
    eid = _anlegen()["id"]
    _aendern(eid, dtstart="2026-11-01T18:00:00Z", dtend="")
    assert _ev(db, eid)["dtend"] == "2026-11-02T00:00:00Z"


# --- Geländehöhen nachholen, Löschen ---------------------------------------------------------

def test_der_knopf_holt_fehlende_gelaendehoehen_nach(db, modell_aus, monkeypatch):
    eid = _anlegen()["id"]
    f = _fehler(lambda: asyncio.run(main.admin_strecke_grund(FakeReq(), eid)))
    assert f.status_code == 502

    async def viele(punkte):
        return [250.0] * len(punkte)

    monkeypatch.setattr(main, "_gelaende_ft_viele", viele)
    assert asyncio.run(main.admin_strecke_grund(FakeReq(), eid))["abschnitte"] == 10
    assert json.loads(_ev(db, eid)["grund_json"]) == [250.0] * 10


def test_loeschen_verlangt_das_passwort_erneut(db, modell):
    eid = _anlegen()["id"]
    nur_admin = FakeReq(cookies={ADMIN_COOKIE: TOKEN})
    f = _fehler(lambda: main.admin_delete_strecken_event(nur_admin, eid))
    assert f.status_code == 403 and f.detail == "confirm_required"
    assert _ev(db, eid) is not None
    main.admin_delete_strecken_event(FakeReq(), eid)
    assert _ev(db, eid) is None


# --- Was Mitglieder sehen ------------------------------------------------------------------------

def test_die_liste_traegt_kurzstand_und_zeiten(db, modell):
    eid = _anlegen()["id"]
    _mit_stand(db, eid)
    (e,) = main.strecke_events()
    assert e["id"] == eid and e["laeuft"] is True and e["vorbei_seit_s"] is None
    assert e["km_gesamt"] == 10.0 and e["km_abgedeckt"] == 4.0
    assert e["regeln"] == {"korridor_m": 500.0, "hoehe_max_ft": 1000.0,
                           "gs_max_kt": 140.0, "gs_min_kt": 30.0}
    assert "strecke" not in e, "die Geometrie kommt erst mit dem Stand eines Events"


def test_der_stand_traegt_die_abschnitte_mit_pilot_und_zeit(db, modell):
    eid = _anlegen()["id"]
    _mit_stand(db, eid)
    s = main.strecke_stand(eid)
    assert len(s["strecke"]) == 10
    assert [a["cid"] for a in s["strecke"]] == [7] * 4 + [None] * 6
    assert s["strecke"][0]["linie"][0] == [pytest.approx(LAT), pytest.approx(LON)]
    assert _fehler(lambda: main.strecke_stand(999)).status_code == 404


def test_die_verwaltung_sieht_punkte_laenge_und_ob_die_hoehen_da_sind(db, modell):
    eid = _anlegen()["id"]
    (z,) = main.admin_list_strecken_events(FakeReq())
    assert z["id"] == eid and z["punkte"] == GERADE and z["laenge_km"] == 10.0
    assert z["grund_da"] is True and z["stand"]["abschnitte"] == 10


# --- Das Höhenmodell selbst ----------------------------------------------------------------------

class _Antwort:
    def __init__(self, status, daten):
        self.status_code, self._daten = status, daten

    def json(self):
        return self._daten


def _klient(antworten, rufe):
    class Klient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            rufe.append(params)
            return antworten(params)

    return Klient


def test_das_hoehenmodell_wird_in_bloecken_zu_100_gefragt(monkeypatch):
    """Gemessen am 10.10.2026: 100 Koordinaten je Anfrage gehen, 101 nicht."""
    rufe = []

    def antworten(params):
        n = len(params["latitude"].split(","))
        return _Antwort(200, {"elevation": [100.0] * n})

    monkeypatch.setattr(main._httpx, "AsyncClient", _klient(antworten, rufe))
    hoehen = asyncio.run(main._gelaende_ft_viele([(47.0 + i / 1000, 11.0) for i in range(250)]))
    assert [len(r["latitude"].split(",")) for r in rufe] == [100, 100, 50]
    assert len(hoehen) == 250 and hoehen[0] == pytest.approx(328.1, abs=0.1), "Meter in Fuß"


@pytest.mark.parametrize("antwort", [
    _Antwort(400, {"error": True}),
    _Antwort(200, {"elevation": [1.0]}),            # zu wenige Werte
    _Antwort(200, {"nichts": 1}),
])
def test_eine_unbrauchbare_antwort_des_hoehenmodells_ergibt_keine_halben_hoehen(
        monkeypatch, antwort):
    monkeypatch.setattr(main._httpx, "AsyncClient", _klient(lambda p: antwort, []))
    assert asyncio.run(main._gelaende_ft_viele([(47.0, 11.0), (47.1, 11.0)])) is None


def test_ein_netzfehler_beim_hoehenmodell_wirft_nicht(monkeypatch):
    def kaputt(params):
        raise OSError("kein Netz")

    monkeypatch.setattr(main._httpx, "AsyncClient", _klient(kaputt, []))
    assert asyncio.run(main._gelaende_ft_viele([(47.0, 11.0)])) is None
