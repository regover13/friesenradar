# -*- coding: utf-8 -*-
"""Fundstellen der Deichkontrolle an den Schnittstellen, das Badge und der Orden (10.10.2026).

Aufbau wie tests/test_strecke_api.py. Spec: Abschnitt 15.
"""
from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image

import app.database as dbm
import app.main as main
from app.auth import ADMIN_COOKIE, CONFIRM_COOKIE, make_admin_token, make_confirm_token
from app.badge import _strecke_zeilen, render_strecke_badge
from app.database import (
    bruegge_soll_alle, bruegge_soll_setzen, get_connection, init_db, strecke_fundstellen,
)

SECRET = "s3cr3t"
PW = "test-admin-pw"
TOKEN = make_admin_token(SECRET, PW)
CONFIRM_TOKEN = make_confirm_token(SECRET, PW, 9_999_999_999)

LAT, LON = 53.72, 7.25
KM_LON = 111.32 * math.cos(math.radians(LAT))
ART = "seehund_kuh"


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


JETZT = datetime.now(timezone.utc).replace(microsecond=0)


def _laufend() -> dict:
    return {"dtstart": _iso(JETZT - timedelta(hours=1)), "dtend": _iso(JETZT + timedelta(hours=1))}


def _vorbei() -> dict:
    return {"dtstart": _iso(JETZT - timedelta(hours=3)), "dtend": _iso(JETZT - timedelta(hours=1))}


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    init_db(p)
    monkeypatch.setattr(
        main, "get_settings",
        lambda: SimpleNamespace(DB_PATH=p, CALLSIGN_PREFIX="FRS", SECRET_KEY=SECRET,
                                ADMIN_PASSWORD=PW))
    monkeypatch.setattr(dbm, "_spur_sektoren", (0.0, []))
    monkeypatch.setattr(dbm, "_strecken_boxen_stand", (0.0, []))
    return p


@pytest.fixture
def modell(monkeypatch):
    rufe = []

    async def viele(punkte):
        rufe.append(list(punkte))
        return [0.0] * len(punkte)

    monkeypatch.setattr(main, "_gelaende_ft_viele", viele)
    return rufe


def _fs(km=3.0, **extra):
    # Hoechstmenge mal Hoechstabstand darf hoechstens 200 sein -- die Abstaende richten sich
    # deshalb nach der Menge, wenn der Test sie nicht selbst vorgibt.
    menge = int(extra.get("menge_max", 9)) if isinstance(extra.get("menge_max", 9), int) else 9
    weit = max(min(20, 200 // max(menge, 1)), 1)
    f = {"lat": LAT, "lon": _ost(km), "art": ART,"menge_min": 5, "menge_max": 9,
         "abstand_min_m": min(10, weit), "abstand_max_m": weit, "startwert": f"s{km}", }
    f.update(extra)
    return f


def _anlegen(**extra):
    body = {"name": "Probe", **_laufend(), "punkte": GERADE, **extra}
    return asyncio.run(main.admin_create_strecken_event(FakeReq(body=body)))["id"]


def _aendern(eid, **body):
    return asyncio.run(main.admin_update_strecken_event(FakeReq(body=body), eid))


def _fundstellen(db, eid):
    c = get_connection(db)
    try:
        return strecke_fundstellen(c, eid)
    finally:
        c.close()


def _soll(db, eid):
    c = get_connection(db)
    try:
        return [r for r in bruegge_soll_alle(c) if r["id"].startswith(f"strecke-{eid}-")]
    finally:
        c.close()


def _fehler(aufruf) -> HTTPException:
    with pytest.raises(HTTPException) as e:
        aufruf()
    return e.value


def _flug(db, cid, von_km, bis_km, start, *, name="Anna"):
    c = get_connection(db)
    try:
        c.execute("INSERT OR IGNORE INTO pilots (cid, name, added_at) VALUES (?, ?, ?)",
                  (cid, name, start))
        t0 = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=30)
        n = int(round((bis_km - von_km) / 0.05))
        for i in range(n + 1):
            c.execute("INSERT OR REPLACE INTO bruegge_spur (cid, ts, lat, lon, alt_msl_ft, gs_kt) "
                      "VALUES (?, ?, ?, ?, 800, 100)",
                      (cid, _iso(t0 + timedelta(seconds=i)), LAT, _ost(von_km + i * 0.05)))
        c.commit()
    finally:
        c.close()


# --- Verwaltung ------------------------------------------------------------------------------

def test_anlegen_mit_fundstellen_holt_ihre_hoehe_im_selben_abruf(db, modell):
    eid = _anlegen(fundstellen=[_fs(3.0), _fs(8.0)])
    assert len(modell) == 1 and len(modell[0]) == 12, "zehn Abschnitte, zwei Fundstellen"
    fs = _fundstellen(db, eid)
    assert [f["nr"] for f in fs] == [1, 2] and all(f["grund_ft"] == 0.0 for f in fs)


def test_die_verwaltung_sieht_lage_menge_und_objekte(db, modell):
    eid = _anlegen(fundstellen=[_fs(3.0)], fund_radius_m=200, badge_name="Kontrolle")
    (zeile,) = main.admin_list_strecken_events(FakeReq())
    assert zeile["id"] == eid and zeile["fund_radius_m"] == 200 and zeile["fund_hoehe_ft"] == 1000
    assert zeile["badge_name"] == "Kontrolle" and zeile["grund_da"] is True
    (f,) = zeile["fundstellen"]
    assert f["startwert"] == "s3.0" and len(f["objekte"]) == f["menge"] and f["gefunden_am"] is None


def test_die_lage_rechnet_der_server_nie_nimmt_er_sie_aus_dem_koerper(db, modell):
    eid = _anlegen(fundstellen=[_fs(3.0, objekte=[{"lat": 0, "lon": 0, "kurs": 0}], menge=1,
                                    gefunden_am="2026-01-01T00:00:00Z", gefunden_von=7)])
    (f,) = _fundstellen(db, eid)
    assert f["menge"] >= 5 and f["gefunden_am"] is None
    assert all(abs(o["lat"] - LAT) < 0.01 for o in f["objekte"])


def test_die_vorschau_wuerfelt_dasselbe_wie_das_speichern(db, modell):
    vorschau = asyncio.run(main.admin_strecke_streuen(FakeReq(body=_fs(3.0))))
    eid = _anlegen(fundstellen=[_fs(3.0)])
    assert vorschau["startwert"] == "s3.0"
    assert vorschau["objekte"] == _fundstellen(db, eid)[0]["objekte"]


def test_die_vorschau_ohne_startwert_wuerfelt_neu(db):
    roh = {k: v for k, v in _fs(3.0).items() if k != "startwert"}
    a = asyncio.run(main.admin_strecke_streuen(FakeReq(body=roh)))
    b = asyncio.run(main.admin_strecke_streuen(FakeReq(body=roh)))
    assert a["startwert"] != b["startwert"] and a["menge"] == len(a["objekte"])


def test_die_vorschau_lehnt_unsinn_mit_einem_satz_ab(db):
    e = _fehler(lambda: asyncio.run(main.admin_strecke_streuen(
        FakeReq(body=_fs(3.0, menge_min=0)))))
    assert e.status_code == 400 and "mindestens ein Objekt" in e.detail
    e = _fehler(lambda: asyncio.run(main.admin_strecke_streuen(FakeReq(body={"lat": "x"}))))
    assert e.status_code == 400


def test_die_vorschau_ist_der_verwaltung_vorbehalten(db):
    e = _fehler(lambda: asyncio.run(main.admin_strecke_streuen(FakeReq(cookies={}, body=_fs()))))
    assert e.status_code in (401, 403)


def test_eine_unbekannte_art_wird_abgelehnt_und_nichts_bleibt_liegen(db, modell):
    e = _fehler(lambda: _anlegen(fundstellen=[_fs(3.0, art="gibt_es_nicht")]))
    assert e.status_code == 400 and "Fundstelle 1" in e.detail
    assert main.admin_list_strecken_events(FakeReq()) == [], "auch das Event nicht"


def test_was_nicht_in_den_simulator_passt_wird_abgelehnt(db, modell):
    """Vier Gruppen zu 60 sind 240 Objekte plus Rauch und Licht -- die Brügge fasst 200."""
    viele = [_fs(k, menge_min=60, menge_max=60) for k in (2.0, 4.0, 6.0, 8.0)]
    e = _fehler(lambda: _anlegen(fundstellen=viele))
    assert e.status_code == 400 and "248 Objekte" in e.detail and "frei sind 200" in e.detail


def test_fremde_objekte_im_simulator_zaehlen_mit_die_eigenen_nicht(db, modell):
    eid = _anlegen(fundstellen=[_fs(3.0, menge_min=60, menge_max=60)])
    assert len(_soll(db, eid)) == 0, "beim Anlegen steht noch nichts im Soll"
    _aendern(eid, name="x")
    assert len(_soll(db, eid)) >= 60, "das Aendern gleicht sofort ab"
    c = get_connection(db)
    for i in range(100):
        bruegge_soll_setzen(c, f"fremd-{i}", "licht", LAT, LON)
    c.commit()
    c.close()
    # 62 eigene + 100 fremde: Dieselbe Liste noch einmal passt (die eigenen zaehlen nicht doppelt).
    _aendern(eid, fundstellen=[_fs(3.0, menge_min=60, menge_max=60)])
    e = _fehler(lambda: _aendern(eid, fundstellen=[_fs(3.0, menge_min=60, menge_max=60),
                                                   _fs(8.0, menge_min=40, menge_max=40)]))
    assert "frei sind 100" in e.detail
    assert len(_fundstellen(db, eid)) == 1, "die abgelehnte Aenderung hat nichts hinterlassen"


def test_ein_neuer_name_laesst_fundstellen_und_fund_stehen(db, modell):
    eid = _anlegen(fundstellen=[_fs(3.0)])
    _flug(db, 7, 0.0, 4.0, _laufend()["dtstart"])
    main.strecke_stand(eid)
    assert _fundstellen(db, eid)[0]["gefunden_von"] == 7
    antwort = _aendern(eid, name="Neuer Name", fundstellen=[_fs(3.0)])
    assert antwort["stand_verworfen"] is False
    assert _fundstellen(db, eid)[0]["gefunden_von"] == 7


def test_ohne_fundstellen_im_koerper_bleiben_die_gespeicherten(db, modell):
    eid = _anlegen(fundstellen=[_fs(3.0)])
    _aendern(eid, name="x")
    assert len(_fundstellen(db, eid)) == 1
    _aendern(eid, fundstellen=[])
    assert _fundstellen(db, eid) == [] and _soll(db, eid) == []


def test_scheitert_das_hoehenmodell_wartet_die_neue_fundstelle_auf_den_knopf(db, modell,
                                                                           monkeypatch):
    eid = _anlegen(fundstellen=[_fs(3.0)])

    async def nichts(punkte):
        return None
    monkeypatch.setattr(main, "_gelaende_ft_viele", nichts)
    antwort = _aendern(eid, fundstellen=[_fs(3.0), _fs(8.0)])
    assert antwort["grund_fehlt"] is True
    assert [f["grund_ft"] for f in _fundstellen(db, eid)] == [0.0, None]
    assert main.strecke_stand(eid)["ohne_grund"] is True

    async def viele(punkte):
        return [50.0] * len(punkte)
    monkeypatch.setattr(main, "_gelaende_ft_viele", viele)
    asyncio.run(main.admin_strecke_grund(FakeReq(), eid))
    assert [f["grund_ft"] for f in _fundstellen(db, eid)] == [50.0, 50.0]


def test_fundradius_und_fundhoehe_aendern_verwirft_nichts(db, modell):
    """Sie gelten ab dem Speichern fuer das, was noch offen ist. Verwuerfen sie den Stand,
    naehmen sie die abgeflogenen Abschnitte mit -- bei einem alten Abend fuer immer."""
    eid = _anlegen(fundstellen=[_fs(3.0)])
    _flug(db, 7, 0.0, 4.0, _laufend()["dtstart"])
    main.strecke_stand(eid)
    antwort = _aendern(eid, fund_radius_m=300, fund_hoehe_ft=1500, fundstellen=[_fs(3.0)])
    assert antwort["stand_verworfen"] is False
    stand = main.strecke_stand(eid)
    assert stand["abgedeckt"] == 4 and stand["fundstellen"]["gefunden"] == 1
    assert stand["regeln"]["fund_radius_m"] == 300


def test_gefunden_wird_nie_weiter_oder_hoeher_als_die_objekte_zu_sehen_sind(db, modell):
    assert "Fundradius" in _fehler(lambda: _anlegen(fund_radius_m=1500)).detail
    assert "Fundhöhe" in _fehler(lambda: _anlegen(fund_hoehe_ft=5000)).detail


def test_rauch_und_licht_sind_als_fundstelle_waehlbar(db, modell):
    """Auch in den anderen Farben (Nutzer, 10.10.2026)."""
    eid = _anlegen(fundstellen=[_fs(3.0, art="rauch_signalrot", menge_min=1, menge_max=1),
                                _fs(5.0, art="licht", menge_min=1, menge_max=1)])
    assert [f["art"] for f in _fundstellen(db, eid)] == ["rauch_signalrot", "licht"]


def test_hoechstmenge_mal_hoechstabstand_ist_begrenzt(db, modell):
    """Gefunden wird gegen die Mitte -- die Grenze haelt die Gruppe beim Fundkreis."""
    e = _fehler(lambda: _anlegen(fundstellen=[_fs(3.0, menge_max=15, abstand_max_m=40)]))
    assert e.status_code == 400 and "Fundstelle 1" in e.detail and "200" in e.detail
    _anlegen(fundstellen=[_fs(3.0, menge_max=10, abstand_max_m=20)])


def test_zu_viele_oder_unlesbare_fundstellen_scheitern_vor_dem_hoehenmodell(db, modell):
    viele = [_fs(i * 0.1) for i in range(41)]
    assert "Höchstens 40" in _fehler(lambda: _anlegen(fundstellen=viele)).detail
    for ort in ({"lat": None}, {"lat": "abc"}, {"lon": float("nan")}, {"lat": 95.0}):
        e = _fehler(lambda: _anlegen(fundstellen=[_fs(3.0, **ort)]))
        assert e.status_code == 400 and "Fundstelle 1" in e.detail
    assert modell == [], "kein einziger Abruf"


def test_nan_im_koerper_haengt_nichts_auf(db, modell):
    for feld in ("abstand_max_m", "abstand_min_m", "menge_max", "richtung"):
        e = _fehler(lambda: asyncio.run(main.admin_strecke_streuen(
            FakeReq(body=_fs(3.0, **{feld: float("nan")})))))
        assert e.status_code == 400
        e = _fehler(lambda: _anlegen(fundstellen=[_fs(3.0, **{feld: float("nan")})]))
        assert e.status_code == 400
    assert main.admin_list_strecken_events(FakeReq()) == []


def test_die_hoehen_gehoeren_stelle_fuer_stelle_zu_den_fundstellen(db, monkeypatch):
    """Ein Modell, das je Ort eine andere Hoehe nennt: Verrutscht die Zuordnung um eine Stelle,
    faellt es hier auf."""
    async def viele(punkte):
        return [round(p[1] * 1000.0, 1) for p in punkte]
    monkeypatch.setattr(main, "_gelaende_ft_viele", viele)
    eid = _anlegen(fundstellen=[_fs(3.0), _fs(8.0)])
    assert [f["grund_ft"] for f in _fundstellen(db, eid)] == [
        round(_ost(3.0) * 1000.0, 1), round(_ost(8.0) * 1000.0, 1)]
    _aendern(eid, fundstellen=[_fs(8.0), _fs(5.0), _fs(3.0)])
    assert [f["grund_ft"] for f in _fundstellen(db, eid)] == [
        round(_ost(k) * 1000.0, 1) for k in (8.0, 5.0, 3.0)]


def test_zwei_events_am_selben_abend_passen_nur_zusammen_in_den_simulator(db, modell):
    """Keines steht beim Speichern schon im Soll -- gezaehlt wird trotzdem beides."""
    dicht = [_fs(k, menge_min=60, menge_max=60) for k in (2.0, 5.0)]          # 124
    _anlegen(fundstellen=dicht)
    e = _fehler(lambda: _anlegen(fundstellen=dicht))
    assert "frei sind 76" in e.detail
    # Naechste Woche ist Platz: Was heute laeuft, steht dann nicht mehr.
    spaeter = {"dtstart": _iso(JETZT + timedelta(days=7)),
               "dtend": _iso(JETZT + timedelta(days=7, hours=2))}
    _anlegen(fundstellen=dicht, **spaeter)


def test_eine_fundstelle_die_waehrend_des_events_dazukommt_zaehlt_erst_ab_dann(db, modell):
    eid = _anlegen()
    _flug(db, 7, 0.0, 4.0, _laufend()["dtstart"])
    main.strecke_stand(eid)
    _aendern(eid, fundstellen=[_fs(3.0)])
    assert _fundstellen(db, eid)[0]["gilt_ab"] is not None
    _aendern(eid, korridor_m=600, fundstellen=[_fs(3.0)])           # verwirft und rechnet neu
    stand = main.strecke_stand(eid)
    assert stand["abgedeckt"] > 0 and stand["fundstellen"]["gefunden"] == 0


def test_beim_anlegen_gelten_fundstellen_von_beginn_an(db, modell):
    eid = _anlegen(fundstellen=[_fs(3.0)])
    assert _fundstellen(db, eid)[0]["gilt_ab"] is None


def test_beginn_und_ende_brauchen_die_volle_form(db, modell):
    e = _fehler(lambda: _anlegen(dtend="2026-10-02"))
    assert e.status_code == 400 and "Form" in e.detail


def test_vor_dem_ende_gibt_es_keinen_orden(db, modell):
    _anlegen(fundstellen=[_fs(3.0)])
    _flug(db, 7, 0.0, 4.0, _laufend()["dtstart"])
    assert main.pilot_orden(7, days=30) == []


def test_fundradius_und_fundhoehe_haben_grenzen(db, modell):
    e = _fehler(lambda: _anlegen(fund_radius_m=5))
    assert e.status_code == 400 and "Fundradius" in e.detail
    e = _fehler(lambda: _anlegen(fund_hoehe_ft="x"))
    assert "Fundhöhe" in e.detail


def test_loeschen_raeumt_auch_den_simulator(db, modell):
    eid = _anlegen(fundstellen=[_fs(3.0)])
    _aendern(eid, name="x")
    assert _soll(db, eid)
    main.admin_delete_strecken_event(FakeReq(), eid)
    assert _soll(db, eid) == [] and _fundstellen(db, eid) == []


# --- Mitglieder ------------------------------------------------------------------------------

def test_mitglieder_sehen_die_zahl_aber_keine_verborgene_lage(db, modell):
    eid = _anlegen(fundstellen=[_fs(3.0), _fs(8.3)])
    _flug(db, 7, 0.0, 4.0, _laufend()["dtstart"])
    liste = main.strecke_events()
    assert liste[0]["fundstellen"] == {"anzahl": 2, "gefunden": 1}
    assert liste[0]["je_pilot"][0]["funde"] == 1
    stand = main.strecke_stand(eid)
    (f,) = stand["fundstellen"]["liste"]
    assert f["nr"] == 1 and f["name"] == "Anna" and f["gefunden"]
    assert f"{_ost(8.3):.4f}" not in json.dumps(stand)
    assert "startwert" not in json.dumps(stand) and "objekte" not in json.dumps(stand)


# --- Badge und Orden -------------------------------------------------------------------------

def _img(b: bytes) -> Image.Image:
    return Image.open(BytesIO(b)).convert("RGBA")


def test_das_badge_ist_rund_und_256_gross():
    im = _img(render_strecke_badge({"callsign": "FRS49", "aircraft": "C172", "km": 22.8,
                                    "funde": 2, "event": "Deichkontrolle", "date": "10.10.2026"}))
    assert im.size == (256, 256)
    assert im.getpixel((0, 0))[3] == 0 and im.getpixel((128, 128))[3] > 250


def test_die_zeilen_des_badges():
    assert _strecke_zeilen({"km": 22.8, "funde": 2}) == ("22,8 km abgeflogen", "2 entdeckt")
    assert _strecke_zeilen({"km": 4.0, "funde": 0}) == ("4,0 km abgeflogen", None)
    assert _strecke_zeilen({"km": 0, "funde": 1}) == (None, "1 entdeckt")


def _vergangen(db, modell):
    eid = _anlegen(fundstellen=[_fs(3.0)], **_vorbei(), badge_name="Kontrolle")
    _flug(db, 7, 0.0, 4.0, _vorbei()["dtstart"])
    return eid


def test_das_badge_gibt_es_erst_nach_dem_ende(db, modell):
    eid = _anlegen(fundstellen=[_fs(3.0)])
    _flug(db, 7, 0.0, 4.0, _laufend()["dtstart"])
    e = _fehler(lambda: main.get_strecke_badge(FakeReq(), eid, 7))
    assert e.status_code == 404


def test_das_badge_nennt_kilometer_und_funde(db, modell):
    eid = _vergangen(db, modell)
    c = get_connection(db)
    try:
        d = main._strecke_badge_data(c, dbm.get_strecken_event(c, eid), 7)
    finally:
        c.close()
    assert d["km"] == 4.0 and d["funde"] == 1 and d["event"] == "Kontrolle"
    assert d["callsign"] == "CID 7"
    antwort = main.get_strecke_badge(FakeReq(), eid, 7)
    assert antwort.media_type == "image/png" and _img(antwort.body).size == (256, 256)
    req = FakeReq()
    req.headers = {"if-none-match": antwort.headers["etag"]}
    assert main.get_strecke_badge(req, eid, 7).status_code == 304


def test_wer_nichts_beigetragen_hat_bekommt_kein_badge(db, modell):
    eid = _vergangen(db, modell)
    assert _fehler(lambda: main.get_strecke_badge(FakeReq(), eid, 99)).status_code == 404


def test_der_orden_steht_in_der_statistik(db, modell):
    eid = _vergangen(db, modell)
    orden = main.pilot_orden(7, days=30)
    assert [(o["art"], o["event_id"], o["name"]) for o in orden] == [("strecke", eid, "Kontrolle")]
    assert orden[0]["bild"] == f"/api/strecke/events/{eid}/badge/7.png"
    assert main.pilot_orden(99, days=30) == []
