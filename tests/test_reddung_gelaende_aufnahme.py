# -*- coding: utf-8 -*-
"""Geländehöhe beim Anlegen und ein eigener Aufnahme-Radius (Nutzer, 28.09.2026).

**Geländehöhe.** Die Suchhöhe ist „Gelände am Havaristen + 2000 ft". Das Gelände lernte der
Server bisher nur aus der Rückmeldung der FriesenBrügge -- und das Wrack bekommt vor dem Fund
nur, wer näher als 1000 m dran ist. Bis dahin galt 0 ft, also 2000 ft MSL: Am 27.09.2026 in
der Eifel (Gelände 1864 ft) mussten alle zwischen den Bäumen suchen. Jetzt holt der Server die
Höhe beim Speichern aus einem Höhenmodell (Open-Meteo, dort 568 m = 1864 ft -- der Simulator
maß 1864,3 ft). Die Messung der Brügge schlägt den Kartenwert weiterhin.

**Aufnahme-Radius.** Finden und Aufnehmen prüften gegen denselben Fundradius. Wer ihn vergrößerte,
damit neben dem Wrack gelandet werden kann, machte zugleich das Finden leichter. Jetzt zwei Felder.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

import app.main as main
from app import reddung as rd
from app.database import get_connection, get_reddung_event, reddung_grund_merken

from tests.test_reddung_api import FakeReq, SEKTOR, db  # noqa: F401  (Fixture)

HAV = {"havarist_lat": 53.72, "havarist_lon": 7.25}
_ADMIN = (Path(__file__).resolve().parents[1] / "app" / "static" / "admin.html").read_text(encoding="utf-8")
_POLLER = (Path(__file__).resolve().parents[1] / "app" / "poller.py").read_text(encoding="utf-8")


@pytest.fixture
def gelaende(monkeypatch):
    """Das Höhenmodell ersetzt: zählt Abrufe, liefert einen einstellbaren Wert."""
    stand = {"wert": 1864.3, "abrufe": []}

    async def falsch(lat, lon):
        stand["abrufe"].append((lat, lon))
        return stand["wert"]
    monkeypatch.setattr(main, "_gelaende_ft", falsch)
    return stand


def _anlegen(**extra) -> int:
    body = {"name": "Eifel", "dtstart": "2099-01-01T17:00:00Z", **SEKTOR, **extra}
    return asyncio.run(main.admin_create_reddung_event(FakeReq(body=body)))["id"]


def _aendern(eid, body):
    return asyncio.run(main.admin_update_reddung_event(FakeReq(body=body), eid))


def _ev(db, eid) -> dict:
    c = get_connection(db)
    try:
        return dict(get_reddung_event(c, eid))
    finally:
        c.close()


# --- Geländehöhe --------------------------------------------------------------------------

def test_beim_anlegen_mit_havarist_kommt_die_gelaendehoehe_mit(db, gelaende):
    eid = _anlegen(**HAV)
    ev = _ev(db, eid)
    assert ev["havarist_grund_ft"] == pytest.approx(1864.3)
    assert ev["havarist_grund_quelle"] == "karte"
    assert gelaende["abrufe"] == [(53.72, 7.25)]


def test_ohne_havarist_wird_nichts_abgefragt(db, gelaende):
    eid = _anlegen()
    assert _ev(db, eid)["havarist_grund_ft"] is None
    assert gelaende["abrufe"] == []


def test_ein_ausfall_des_hoehenmodells_verhindert_das_anlegen_nicht(db, gelaende):
    gelaende["wert"] = None
    eid = _anlegen(**HAV)
    assert _ev(db, eid)["havarist_grund_ft"] is None


def test_ein_verschobener_havarist_bekommt_die_hoehe_der_neuen_stelle(db, gelaende):
    """Die Messung gehörte zur alten Stelle -- nach dem Verschieben ist sie falsch."""
    eid = _anlegen(**HAV)
    c = get_connection(db)
    try:
        reddung_grund_merken(c, eid, 1900.0, "gemessen")
        c.commit()
    finally:
        c.close()
    gelaende["wert"] = 250.0
    _aendern(eid, {"havarist_lat": 53.80, "havarist_lon": 7.30})
    ev = _ev(db, eid)
    assert (ev["havarist_grund_ft"], ev["havarist_grund_quelle"]) == (250.0, "karte")


def test_ohne_neue_stelle_bleibt_die_messung_und_es_wird_nicht_gefragt(db, gelaende):
    eid = _anlegen(**HAV)
    c = get_connection(db)
    try:
        reddung_grund_merken(c, eid, 1900.0, "gemessen")
        c.commit()
    finally:
        c.close()
    gelaende["abrufe"].clear()
    _aendern(eid, {"name": "Eifel II", **HAV})
    ev = _ev(db, eid)
    assert (ev["havarist_grund_ft"], ev["havarist_grund_quelle"]) == (1900.0, "gemessen")
    assert gelaende["abrufe"] == []


def test_eine_fehlende_hoehe_wird_beim_naechsten_speichern_nachgeholt(db, gelaende):
    """Ein Event von vor dieser Fassung, oder das Höhenmodell war beim Anlegen weg."""
    gelaende["wert"] = None
    eid = _anlegen(**HAV)
    gelaende["wert"] = 1864.3
    _aendern(eid, {"name": "Eifel"})
    assert _ev(db, eid)["havarist_grund_quelle"] == "karte"


def test_ein_vergangenes_event_bekommt_keine_neue_hoehe(db, gelaende):
    """Seine Bilanz ist mit der damaligen Schranke gerechnet -- nachträglich eine andere
    Höhe einzutragen, passte nicht mehr zu ihr."""
    gelaende["wert"] = None
    eid = _anlegen(dtstart="2020-01-01T17:00:00Z", dtend="2020-01-01T19:00:00Z", **HAV)
    gelaende["wert"] = 1864.3
    _aendern(eid, {"name": "alt"})
    assert _ev(db, eid)["havarist_grund_ft"] is None


def test_die_messung_schlaegt_die_karte_und_nicht_umgekehrt(db):
    eid = _anlegen()
    c = get_connection(db)
    try:
        assert reddung_grund_merken(c, eid, 1864.0, "karte")
        assert reddung_grund_merken(c, eid, 1864.3, "gemessen")
        assert not reddung_grund_merken(c, eid, 1700.0, "karte")
        c.commit()
        assert get_reddung_event(c, eid)["havarist_grund_ft"] == pytest.approx(1864.3)
    finally:
        c.close()


def test_die_antwort_des_hoehenmodells_wird_in_fuss_umgerechnet():
    assert main._gelaende_aus_antwort({"elevation": [568.0]}) == pytest.approx(1863.5, abs=0.1)
    for kaputt in ({}, {"elevation": []}, {"elevation": [None]}, {"elevation": ["x"]}, None):
        assert main._gelaende_aus_antwort(kaputt) is None


def test_der_admin_warnt_wenn_die_gelaendehoehe_fehlt():
    stelle = _ADMIN[_ADMIN.index("const grund = (ev.havarist_grund_ft === null"):]
    stelle = stelle[:stelle.index("const ort =")]
    assert "Suchhöhe gilt ab 0 ft MSL" in stelle


# --- Aufnahme-Radius ----------------------------------------------------------------------

def test_aufnahme_und_fund_haben_je_einen_radius():
    ev = {"havarist_lat": 50.0, "havarist_lon": 6.0, "fund_radius_m": 150, "aufnahme_radius_m": 400}
    assert rd.havarist_ziel(ev)[3] == pytest.approx(0.150)
    assert rd.aufnahme_ziel(ev)[3] == pytest.approx(0.400)


def test_der_aufnahme_radius_steht_auf_150_m_vor():
    """150 m (Nutzer, 28.09.2026) -- zuerst 100 m; das Nachspiel des 27.09. zeigte, wie eng das ist."""
    ev = {"havarist_lat": 50.0, "havarist_lon": 6.0}
    assert rd.aufnahme_radius_m(ev) == 150.0
    assert rd.aufnahme_ziel(ev)[3] == pytest.approx(0.150)
    assert rd.aufnahme_ziel({}) is None


def test_der_poller_nimmt_fuers_aufnehmen_den_aufnahme_radius():
    stufe2 = _POLLER[_POLLER.index("# 2 -- Aufnehmen"):_POLLER.index("# 3 -- Einliefern")]
    assert "rd.aufnahme_ziel(ev)" in stufe2
    assert "[ziel]" not in stufe2


def test_der_aufnahme_radius_wird_gespeichert_und_geprueft(db, gelaende):
    eid = _anlegen(aufnahme_radius_m=300)
    assert _ev(db, eid)["aufnahme_radius_m"] == 300
    with pytest.raises(Exception):
        _aendern(eid, {"aufnahme_radius_m": 0})
    with pytest.raises(Exception):
        _aendern(eid, {"aufnahme_radius_m": "breit"})


def test_der_aufnahme_radius_verwirft_die_bilanz_nicht():
    """Er wirkt nur auf die Aufnahme -- die steht im Event, nicht im fortgeschriebenen Stand."""
    assert "aufnahme_radius_m" in main._REDDUNG_OHNE_RECHNUNG


def test_der_admin_hat_ein_feld_fuer_den_aufnahme_radius():
    assert re.search(r'<input type="number"[^>]*id="rd-aufnahme-radius" value="150"', _ADMIN)
    assert "aufnahme_radius_m: _rdZahl('rd-aufnahme-radius', 150)" in _ADMIN
    assert "setz('rd-aufnahme-radius', ev.aufnahme_radius_m == null ? 150" in _ADMIN


def test_der_echte_abruf_fragt_das_hoehenmodell_und_rechnet_um(monkeypatch):
    """Ohne Ersatz für `_gelaende_ft` selbst: Ein Tippfehler im Modulnamen verschwände sonst im
    breiten `except` -- nie eine Höhe, und niemand merkte es."""
    gefragt = {}

    class Antwort:
        status_code = 200

        def json(self):
            return {"elevation": [568.0]}

    class Klient:
        def __init__(self, **kw):
            gefragt["timeout"] = kw.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            gefragt["url"], gefragt["params"] = url, params
            return Antwort()

    monkeypatch.setattr(main._httpx, "AsyncClient", Klient)
    assert asyncio.run(main._gelaende_ft(50.543, 6.3731)) == pytest.approx(1863.5, abs=0.1)
    assert gefragt["url"] == main._GELAENDE_URL
    assert gefragt["params"] == {"latitude": 50.543, "longitude": 6.3731}
    assert gefragt["timeout"] and gefragt["timeout"] <= 10


def test_ein_netzfehler_ergibt_keine_hoehe_und_keinen_absturz(monkeypatch):
    """Der Fehlerweg selbst darf nicht werfen -- sonst bricht jedes Speichern mit 500 ab,
    sobald das Höhenmodell nicht antwortet."""
    class Kaputt:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            raise OSError("kein Netz")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(main._httpx, "AsyncClient", Kaputt)
    assert asyncio.run(main._gelaende_ft(50.5, 6.3)) is None
