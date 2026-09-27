"""Admin-API fuer die Messeverkehr-Allowlist und das Feature-Flag.

Ruling (Task 5, Plan 2026-09-27-messeverkehr.md): Der Plan nahm einen TestClient-Login ueber
POST /api/admin/login an -- den gibt es in dieser Codebasis nicht. Das echte Muster (siehe
tests/test_admin_api.py) ruft die Endpunkt-Funktionen direkt async auf, mit einem FakeReq statt
einem echten Request, und Admin-Endpunkte lesen ihren Body selbst per `await request.json()`
statt ueber ein FastAPI-Body(...)-Parameter. Uebernommen, weil es die tatsaechliche Konvention
der Codebasis ist -- Kosten bei Irrtum: nur diese Testdatei muesste umgeschrieben werden.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.main as main
from app.auth import ADMIN_COOKIE, make_admin_token
from app.database import init_db, get_connection

SECRET = "s3cr3t"
PW = "test-admin-pw"
TOKEN = make_admin_token(SECRET, PW)


class FakeReq:
    def __init__(self, cookies=None, body=None):
        self.cookies = cookies if cookies is not None else {ADMIN_COOKIE: TOKEN}
        self._body = body or {}

    async def json(self):
        return self._body


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    init_db(p)
    monkeypatch.setattr(
        main, "get_settings",
        lambda: SimpleNamespace(
            DB_PATH=p, CALLSIGN_PREFIX="FRS", SECRET_KEY=SECRET, ADMIN_PASSWORD=PW,
            VAPID_PRIVATE_KEY="vapid", VAPID_CONTACT_EMAIL="mailto:test",
            STATSIM_API_KEY=None,
        ),
    )
    return p


def test_flag_default_aus(db):
    res = asyncio.run(main.admin_get_messeverkehr(FakeReq()))
    assert res["enabled"] is False
    assert res["erlaubt"] == []


def test_flag_umschalten(db):
    asyncio.run(main.admin_set_messeverkehr(FakeReq(body={"enabled": True})))
    res = asyncio.run(main.admin_get_messeverkehr(FakeReq()))
    assert res["enabled"] is True


def test_cid_hinzufuegen_und_entfernen(db):
    asyncio.run(main.admin_add_messeverkehr_erlaubt(FakeReq(body={"cid": 123456, "von": "Tobias"})))
    res = asyncio.run(main.admin_get_messeverkehr(FakeReq()))
    assert {e["cid"] for e in res["erlaubt"]} == {123456}

    asyncio.run(main.admin_remove_messeverkehr_erlaubt(123456, FakeReq()))
    res = asyncio.run(main.admin_get_messeverkehr(FakeReq()))
    assert res["erlaubt"] == []


def test_ohne_admin_login_401(db):
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.admin_get_messeverkehr(FakeReq(cookies={})))
    assert e.value.status_code == 401


def test_flag_string_false_schaltet_nicht_ein(db):
    """Final-Fix I4: bool("false") ist True in Python -- ein von Hand getipptes
    curl -d '{"enabled":"false"}' hat das Feature bisher versehentlich EINgeschaltet statt
    ausgeschaltet. Nur echte Booleans duerfen zaehlen, alles andere ist ein Fehler (400)."""
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.admin_set_messeverkehr(FakeReq(body={"enabled": "false"})))
    assert e.value.status_code == 400

    res = asyncio.run(main.admin_get_messeverkehr(FakeReq()))
    assert res["enabled"] is False


def test_flag_ohne_enabled_feld_ist_fehler(db):
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.admin_set_messeverkehr(FakeReq(body={})))
    assert e.value.status_code == 400


def test_get_liefert_einstellungen_mit_defaults(db):
    res = asyncio.run(main.admin_get_messeverkehr(FakeReq()))
    assert res["min_fluege"] == 2
    assert res["max_fluege"] == 4
    assert res["staffelung_min"] == 30
    assert res["ausschluss_callsigns"] == []


def test_einstellungen_setzen(db):
    asyncio.run(main.admin_set_messeverkehr_einstellungen(
        FakeReq(body={"min_fluege": 1, "max_fluege": 5, "staffelung_min": 45})
    ))
    res = asyncio.run(main.admin_get_messeverkehr(FakeReq()))
    assert res["min_fluege"] == 1
    assert res["max_fluege"] == 5
    assert res["staffelung_min"] == 45


def test_einstellungen_min_darf_nicht_ueber_max_liegen(db):
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.admin_set_messeverkehr_einstellungen(
            FakeReq(body={"min_fluege": 5, "max_fluege": 1, "staffelung_min": 30})
        ))
    assert e.value.status_code == 400


def test_einstellungen_negative_werte_sind_fehler(db):
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.admin_set_messeverkehr_einstellungen(
            FakeReq(body={"min_fluege": -1, "max_fluege": 4, "staffelung_min": 30})
        ))
    assert e.value.status_code == 400


def test_ausschluss_callsigns_setzen_und_lesen(db):
    asyncio.run(main.admin_set_messeverkehr_ausschluss(
        FakeReq(body={"callsigns": ["frs7", " FRS8 ", "", "FRS9N"]})
    ))
    res = asyncio.run(main.admin_get_messeverkehr(FakeReq()))
    assert res["ausschluss_callsigns"] == ["FRS7", "FRS8", "FRS9N"]

    # Erneutes Setzen ERSETZT die Liste komplett, haengt nicht an.
    asyncio.run(main.admin_set_messeverkehr_ausschluss(FakeReq(body={"callsigns": ["FRS1"]})))
    res = asyncio.run(main.admin_get_messeverkehr(FakeReq()))
    assert res["ausschluss_callsigns"] == ["FRS1"]
