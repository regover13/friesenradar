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
