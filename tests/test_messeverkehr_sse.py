"""Final-Fix I3: Der SSE-Zweig fuer type=='positions' hatte dieselbe Filterlogik wie
_positions_fuer_betrachter (app/main.py), nur als eigene, ungetestete Kopie im laufenden
Strom -- dem Pfad, der jede Sekunde die echten Live-Updates traegt. Diese Datei bindet ihn
direkt an den Generator, nach dem Muster von test_kniebrett_strom_filter.py.
"""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from app import main
from app.database import init_db, get_connection, add_messeverkehr_erlaubt
from app.forum_sso import USER_COOKIE, make_user_token
from app.poller import VatsimPoller


@pytest.fixture()
def env(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    init_db(p)
    monkeypatch.setattr(main, "get_settings",
                        lambda: SimpleNamespace(DB_PATH=p, SECRET_KEY="s3cr3t"))
    return p


class _FakeRequest:
    def __init__(self, cookies: dict | None = None, runden: int = 1):
        self.cookies = cookies or {}
        self.query_params: dict = {}
        self._uebrig = runden

    async def is_disconnected(self) -> bool:
        self._uebrig -= 1
        return self._uebrig < 0


def _poller(db: str) -> VatsimPoller:
    return VatsimPoller(db_path=db, callsign_prefix="FRS", poll_interval=60)


async def _ausgeliefert(request, poller, aktion) -> list[dict]:
    raus: list[dict] = []

    async def lauf():
        async for stueck in main._event_generator(request, poller):
            if stueck.startswith("data: "):
                raus.append(json.loads(stueck[6:]))

    aufgabe = asyncio.ensure_future(lauf())
    await asyncio.sleep(0.05)
    aktion(poller)
    await asyncio.wait_for(aufgabe, timeout=5)
    return raus


_GEMISCHT = [
    {"cid": 123, "callsign": "FRS1", "latitude": 1.0},
    {"cid": -900000, "callsign": "FRS801", "latitude": 2.0, "_messeverkehr": True},
]


def _sende_gemischt(poller: VatsimPoller) -> None:
    poller.broadcast_sse({"type": "positions", "data": [dict(e) for e in _GEMISCHT]})


def _cookie_fuer(cid: int) -> dict:
    token = make_user_token("s3cr3t", "Test", str(cid), False, time.time() + 3600)
    return {USER_COOKIE: token}


class TestMesseverkehrSSE:
    def test_nicht_angemeldet_sieht_nur_echte(self, env):
        raus = asyncio.run(_ausgeliefert(_FakeRequest(), _poller(env), _sende_gemischt))
        assert len(raus) == 1
        assert [e["cid"] for e in raus[0]["data"]] == [123]

    def test_angemeldet_aber_nicht_erlaubt_sieht_nur_echte(self, env):
        raus = asyncio.run(_ausgeliefert(_FakeRequest(_cookie_fuer(999999)), _poller(env),
                                          _sende_gemischt))
        assert [e["cid"] for e in raus[0]["data"]] == [123]

    def test_erlaubter_betrachter_sieht_beide_ohne_markierung(self, env):
        conn = get_connection(env)
        add_messeverkehr_erlaubt(conn, 123456, "Test")
        conn.commit()
        conn.close()

        raus = asyncio.run(_ausgeliefert(_FakeRequest(_cookie_fuer(123456)), _poller(env),
                                          _sende_gemischt))
        cids = {e["cid"] for e in raus[0]["data"]}
        assert cids == {123, -900000}
        assert all("_messeverkehr" not in e for e in raus[0]["data"])

    def test_nachricht_ohne_messeverkehr_bleibt_unveraendert(self, env):
        echte_nachricht = {"type": "positions", "data": [{"cid": 123, "callsign": "FRS1"}]}
        raus = asyncio.run(_ausgeliefert(_FakeRequest(), _poller(env),
                                          lambda p: p.broadcast_sse(echte_nachricht)))
        assert raus[0]["data"] == echte_nachricht["data"]
