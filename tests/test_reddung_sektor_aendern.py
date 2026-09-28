# -*- coding: utf-8 -*-
"""Den Sektor während einer FriesenReddung ändern (Nutzer, 28.09.2026).

Zwei Lücken: Niemand prüfte, ob der Havarist im (neuen) Sektor liegt -- grenzt der
Veranstalter versehentlich daneben ein, sucht die Gruppe den Rest des Abends ins Leere. Und die
Piloten erfuhren von der Eingrenzung nichts, wer nicht auf die Karte schaute, suchte weiter.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.main as main
from tests.test_reddung_api import FakeReq, SEKTOR, db  # noqa: F401  (Fixture)

HAV = {"havarist_lat": 53.72, "havarist_lon": 7.25}


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _laufend():
    j = datetime.now(timezone.utc)
    return {"dtstart": _iso(j - timedelta(hours=1)), "dtend": _iso(j + timedelta(hours=1))}


@pytest.fixture
def ohne_netz(monkeypatch):
    async def keine(lat, lon):
        return None
    monkeypatch.setattr(main, "_gelaende_ft", keine)


@pytest.fixture
def pushes(monkeypatch, db):
    """Push-Wege ersetzt: sammelt, was an die Gruppe ginge."""
    gesendet = []
    poller = SimpleNamespace(broadcast_notify=lambda dienst, cid, p, **kw: gesendet.append(("sse", p)))
    monkeypatch.setattr(main.app.state, "poller", poller, raising=False)

    async def web_push(key, mail, pfad, subs, payload, **kw):
        gesendet.append(("web", payload))
    monkeypatch.setattr(main, "send_web_push", web_push)
    einst = main.get_settings()
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(
        **{**vars(einst), "VAPID_PRIVATE_KEY": "vapid"}))
    monkeypatch.setattr(main, "get_push_subscriptions_for_events", lambda conn: [{"endpoint": "x"}])
    return gesendet


class Req(FakeReq):
    def __init__(self, body):
        super().__init__(body=body)
        self.app = main.app


def _anlegen(**extra):
    body = {"name": "Eifel", **SEKTOR, **HAV, **extra}
    body.setdefault("dtstart", "2099-01-01T17:00:00Z")
    return asyncio.run(main.admin_create_reddung_event(FakeReq(body=body)))["id"]


def _aendern(eid, body):
    async def lauf():
        erg = await main.admin_update_reddung_event(Req(body), eid)
        await asyncio.sleep(0)          # angestossene Push-Aufgaben laufen lassen
        return erg
    return asyncio.run(lauf())


# --- 1: Der Havarist muss im Sektor liegen ------------------------------------------------

def test_ein_sektor_ohne_den_havaristen_wird_beim_anlegen_abgewiesen(db, ohne_netz):
    with pytest.raises(HTTPException) as e:
        _anlegen(havarist_lat=54.5, havarist_lon=7.25)
    assert e.value.status_code == 400 and "außerhalb des Sektors" in e.value.detail


def test_eine_eingrenzung_am_havaristen_vorbei_wird_abgewiesen(db, ohne_netz):
    eid = _anlegen()
    with pytest.raises(HTTPException) as e:
        _aendern(eid, {"sued": 53.80, "west": 6.95, "nord": 53.90, "ost": 7.55})
    assert e.value.status_code == 400 and "außerhalb des Sektors" in e.value.detail


def test_ein_verschobener_havarist_ausserhalb_wird_abgewiesen(db, ohne_netz):
    eid = _anlegen()
    with pytest.raises(HTTPException):
        _aendern(eid, {"havarist_lat": 50.0, "havarist_lon": 6.0})


def test_eine_eingrenzung_um_den_havaristen_geht_durch(db, ohne_netz):
    eid = _anlegen()
    _aendern(eid, {"sued": 53.65, "west": 7.10, "nord": 53.80, "ost": 7.40})


def test_ohne_havarist_gibt_es_nichts_zu_pruefen(db, ohne_netz):
    body = {"name": "Eifel", "dtstart": "2099-01-01T17:00:00Z", **SEKTOR}
    asyncio.run(main.admin_create_reddung_event(FakeReq(body=body)))


# --- 2: Die Gruppe erfährt von der Eingrenzung --------------------------------------------

NEU = {"sued": 53.65, "west": 7.10, "nord": 53.80, "ost": 7.40}


def test_eine_eingrenzung_im_laufenden_event_geht_per_push_raus(db, ohne_netz, pushes):
    eid = _anlegen(**_laufend())
    _aendern(eid, NEU)
    wege = sorted(w for w, _ in pushes)
    assert wege == ["sse", "web"]
    # Ein neuer Sektor ist keine Eingrenzung -- eigener Text (Fable, 28.09.2026).
    assert all("Suchsektor" in p["body"] for _, p in pushes)


def test_vor_dem_start_geht_nichts_raus(db, ohne_netz, pushes):
    eid = _anlegen()
    _aendern(eid, NEU)
    assert pushes == []


def test_ohne_neuen_sektor_geht_nichts_raus(db, ohne_netz, pushes):
    eid = _anlegen(**_laufend())
    _aendern(eid, {"name": "Eifel II", **SEKTOR})
    assert pushes == []


def test_mit_abgeschalteten_pushes_geht_nichts_raus(db, ohne_netz, pushes):
    eid = _anlegen(**_laufend())
    asyncio.run(main.admin_reddung_push(FakeReq(body={"enabled": False}), eid))
    _aendern(eid, NEU)
    assert pushes == []
