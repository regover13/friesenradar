# -*- coding: utf-8 -*-
"""Die Herkunftsprüfung der Verwaltung (10.10.2026).

Ein ändernder Aufruf an ``/api/admin/…`` muss von der eigenen Seite kommen. Anlass: Die
Forum-Anmeldung trägt ``SameSite=None`` (Kniebrett im iframe) und wird vom Browser auch bei
Aufrufen fremder Seiten mitgeschickt.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app.main as main
from app.auth import ADMIN_COOKIE, make_admin_token
from app.forum_sso import USER_COOKIE, make_user_token

SECRET, PW = "s3cr3t", "test-admin-pw"


def _forum_cookie() -> dict:
    """Die Forum-Anmeldung eines Mitglieds der Gruppe „Events“ -- das Cookie, das der Browser
    auch von fremden Seiten mitschickt (``SameSite=None``)."""
    return {USER_COOKIE: make_user_token(SECRET, "Anna", "7", True, 9_999_999_999)}


class Req:
    """Eine Anfrage mit Forum-Anmeldung; ``passwort=True`` nimmt stattdessen das Passwort-Cookie."""

    def __init__(self, method="POST", passwort=False, **kopf):
        self.method = method
        self.headers = {k.replace("_", "-"): v for k, v in kopf.items()}
        self.cookies = ({ADMIN_COOKIE: make_admin_token(SECRET, PW)} if passwort
                        else _forum_cookie())


@pytest.fixture(autouse=True)
def einstellungen(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(
        SECRET_KEY=SECRET, ADMIN_PASSWORD=PW, DB_PATH=":memory:"))


def _abgelehnt(req) -> bool:
    try:
        main.require_admin(req)
    except HTTPException as e:
        assert e.status_code == 403 and "fremden Seite" in e.detail
        return True
    return False


@pytest.mark.parametrize("host, origin", [
    ("radar.friesenflieger.de", "https://radar.friesenflieger.de"),
    ("friesenradar.devprops.de", "https://friesenradar.devprops.de"),
    ("friesenspy.devprops.de", "https://friesenspy.devprops.de"),
    ("test-radar.devprops.de", "https://test-radar.devprops.de"),
    ("localhost:8091", "http://localhost:8091"),
    ("Radar.FriesenFlieger.de", "https://radar.friesenflieger.de"),
])
def test_die_eigene_seite_darf_aendern_unter_jeder_adresse(host, origin):
    assert not _abgelehnt(Req(host=host, origin=origin))


@pytest.mark.parametrize("origin", [
    "https://boese.example", "https://radar.friesenflieger.de.boese.example",
    "https://friesenradar.devprops.de",          # eine ANDERE unserer Adressen ist auch fremd
    "http://radar.friesenflieger.de:8080", "null", "kaputt",
])
def test_eine_fremde_herkunft_wird_abgelehnt(origin):
    assert _abgelehnt(Req(host="radar.friesenflieger.de", origin=origin))


@pytest.mark.parametrize("methode", ["POST", "PUT", "PATCH", "DELETE", "post"])
def test_alle_aendernden_methoden_werden_geprueft(methode):
    assert _abgelehnt(Req(methode, host="radar.friesenflieger.de", origin="https://boese.example"))


@pytest.mark.parametrize("methode", ["GET", "HEAD", "OPTIONS"])
def test_lesen_wird_nicht_geprueft(methode):
    assert not _abgelehnt(Req(methode, host="radar.friesenflieger.de",
                              origin="https://boese.example"))


def test_ohne_origin_entscheidet_sec_fetch_site():
    assert _abgelehnt(Req(host="radar.friesenflieger.de", sec_fetch_site="cross-site"))
    assert _abgelehnt(Req(host="radar.friesenflieger.de", sec_fetch_site="same-site"))
    assert not _abgelehnt(Req(host="radar.friesenflieger.de", sec_fetch_site="same-origin"))
    assert not _abgelehnt(Req(host="radar.friesenflieger.de", sec_fetch_site="none"))


def test_ohne_beides_entscheidet_der_referer():
    assert _abgelehnt(Req(host="radar.friesenflieger.de", referer="https://boese.example/x"))
    assert not _abgelehnt(Req(host="radar.friesenflieger.de",
                              referer="https://radar.friesenflieger.de/admin"))


def test_ohne_jede_angabe_wird_abgelehnt():
    """Nicht durchlassen: Eine fremde Seite kann den Referer unterdrücken, und ein alter Browser
    nennt weder Origin noch Sec-Fetch-Site -- genau dieser Aufruf käme sonst durch."""
    assert _abgelehnt(Req(host="radar.friesenflieger.de"))
    assert _abgelehnt(Req(origin="https://radar.friesenflieger.de")), "ohne Host kein Vergleich"
    assert _abgelehnt(Req(host="radar.friesenflieger.de", origin=""))


def test_die_attrappen_der_tests_ohne_methode_bleiben_unberuehrt():
    """Die Tests rufen Endpunkt-Funktionen direkt mit einer Attrappe ohne ``method`` auf. Eine
    echte Anfrage hat immer eine."""
    assert not _abgelehnt(SimpleNamespace(headers={}, cookies=Req().cookies))


def test_mit_dem_passwort_cookie_geht_ein_werkzeug_ohne_browser_durch():
    """Das Passwort-Cookie trägt ``SameSite=Lax`` und kommt von fremden Seiten gar nicht mit.
    Die Werkzeuge der FriesenBrügge (Katalog hochladen) melden sich so an und nennen keine
    Herkunft -- sie dürfen nicht ausgesperrt werden."""
    assert not _abgelehnt(Req(passwort=True, host="radar.friesenflieger.de"))
    assert not _abgelehnt(Req(passwort=True))


def test_auch_mit_dem_passwort_cookie_wird_eine_genannte_fremde_herkunft_abgelehnt():
    assert _abgelehnt(Req(passwort=True, host="radar.friesenflieger.de",
                          origin="https://boese.example"))
    assert _abgelehnt(Req(passwort=True, host="radar.friesenflieger.de",
                          sec_fetch_site="cross-site"))


def test_das_passwort_cookie_im_browser_neben_der_forum_anmeldung_aendert_nichts():
    """Beide Cookies, eigene Seite: geht. Von einer fremden Seite käme das Passwort-Cookie
    nicht mit -- dann gilt die strenge Prüfung der Forum-Anmeldung (die übrigen Tests)."""
    req = Req(passwort=True, host="radar.friesenflieger.de",
              origin="https://radar.friesenflieger.de")
    req.cookies.update(_forum_cookie())
    assert not _abgelehnt(req)


def test_die_pruefung_ersetzt_die_anmeldung_nicht():
    req = Req(host="radar.friesenflieger.de", origin="https://radar.friesenflieger.de")
    req.cookies = {}
    with pytest.raises(HTTPException) as e:
        main.require_admin(req)
    assert e.value.status_code == 401


def test_jeder_aendernde_verwaltungs_endpunkt_laeuft_durch_die_pruefung():
    """Am Quelltext: Kein ändernder ``/api/admin``-Endpunkt ohne ``require_admin`` -- bis auf
    die Anmeldung selbst, die noch keine Sitzung hat, die man missbrauchen könnte."""
    import inspect
    ausnahmen = {"/api/admin/login", "/api/admin/logout"}
    ohne = []
    for route in main.app.routes:
        pfad = getattr(route, "path", "")
        if not pfad.startswith("/api/admin") or pfad in ausnahmen:
            continue
        if not (set(getattr(route, "methods", ())) & main._HERKUNFT_METHODEN):
            continue
        if "require_admin(" not in inspect.getsource(route.endpoint):
            ohne.append(pfad)
    assert ohne == []


def test_durch_die_ganze_app_ein_fremder_aufruf_scheitert_der_eigene_nicht(tmp_path, monkeypatch):
    from app.database import init_db
    p = str(tmp_path / "t.db")
    init_db(p)
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(
        SECRET_KEY=SECRET, ADMIN_PASSWORD=PW, DB_PATH=p, CALLSIGN_PREFIX="FRS"))
    client = TestClient(main.app)
    cookies = _forum_cookie()
    koerper = {"lat": 54.0, "lon": 9.0, "menge_min": 2, "menge_max": 2,
               "abstand_min_m": 5, "abstand_max_m": 9}
    pfad = "/api/admin/strecke/streuen"
    fremd = client.post(pfad, json=koerper, cookies=cookies,
                        headers={"host": "radar.friesenflieger.de", "origin": "https://boese.example"})
    assert fremd.status_code == 403
    eigen = client.post(pfad, json=koerper, cookies=cookies,
                        headers={"host": "radar.friesenflieger.de",
                                 "origin": "https://radar.friesenflieger.de"})
    assert eigen.status_code == 200 and eigen.json()["menge"] == 2
