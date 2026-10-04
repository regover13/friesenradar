"""Push-Abos beim Adresswechsel (Nutzer 04.10.2026, nach dem Umzug auf friesenradar.devprops.de).

Der Browser fuehrt Abos je Adresse. Wer auf der neuen Adresse neu einschaltet, behielte sonst
sein Abo von der alten und bekaeme jede Meldung doppelt. Beim ERSTEN Einschalten ueber eine
neuere Adresse entfernt der Server deshalb das aeltere Abo desselben Mitglieds beim selben
Push-Dienst. Naeherung, vom Nutzer so entschieden: Zwei Geraete beim selben Dienst lassen sich
nicht unterscheiden.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import app.main as main
from app.database import (
    alte_adress_abos_entfernen,
    get_connection,
    init_db,
    upsert_push_subscription,
)

HOSTS = main._SSO_RUECKSPRUNG_HOSTS
ALT, NEU, VEREIN = HOSTS
APPLE_1 = "https://web.push.apple.com/AAA"
APPLE_2 = "https://web.push.apple.com/BBB"
FCM = "https://fcm.googleapis.com/fcm/send/CCC"
WNS_1 = "https://wns2-am3p.notify.windows.com/w/?token=DDD"
WNS_2 = "https://wns2-db5p.notify.windows.com/w/?token=EEE"


@pytest.fixture
def conn(tmp_path):
    p = str(tmp_path / "t.db")
    init_db(p)
    c = get_connection(p)
    yield c
    c.close()


def _abos(conn):
    return {r[0]: r[1] for r in conn.execute("SELECT endpoint, herkunft FROM push_subscriptions")}


def test_die_herkunft_wird_gespeichert_und_von_einem_anonymen_auffrischen_nicht_geloescht(conn):
    upsert_push_subscription(conn, APPLE_1, "p", "a", owner_cid=7, herkunft=NEU)
    upsert_push_subscription(conn, APPLE_1, "p", "a")
    assert _abos(conn) == {APPLE_1: NEU}


def test_das_aeltere_abo_beim_selben_dienst_faellt_weg(conn):
    upsert_push_subscription(conn, APPLE_1, "p", "a", owner_cid=7)            # Bestand: ohne Herkunft
    upsert_push_subscription(conn, FCM, "p", "a", owner_cid=7, herkunft=ALT)   # anderer Dienst
    upsert_push_subscription(conn, APPLE_2, "p", "a", owner_cid=7, herkunft=NEU)
    assert alte_adress_abos_entfernen(conn, APPLE_2, 7, NEU, HOSTS) == 1
    assert set(_abos(conn)) == {FCM, APPLE_2}


def test_windows_endpunkte_verschiedener_rechenzentren_sind_derselbe_dienst(conn):
    upsert_push_subscription(conn, WNS_1, "p", "a", owner_cid=7, herkunft=ALT)
    upsert_push_subscription(conn, WNS_2, "p", "a", owner_cid=7, herkunft=NEU)
    assert alte_adress_abos_entfernen(conn, WNS_2, 7, NEU, HOSTS) == 1


def test_fremde_abos_und_abos_derselben_oder_einer_neueren_adresse_bleiben(conn):
    upsert_push_subscription(conn, APPLE_1, "p", "a", owner_cid=8, herkunft=ALT)      # anderes Mitglied
    upsert_push_subscription(conn, WNS_1, "p", "a", owner_cid=7, herkunft=NEU)        # zweites Geraet, neue Adresse
    upsert_push_subscription(conn, FCM, "p", "a", owner_cid=7, herkunft=VEREIN)       # schon weiter
    upsert_push_subscription(conn, WNS_2, "p", "a", owner_cid=7, herkunft=NEU)
    upsert_push_subscription(conn, APPLE_2, "p", "a", owner_cid=7, herkunft=NEU)
    assert alte_adress_abos_entfernen(conn, WNS_2, 7, NEU, HOSTS) == 0
    assert alte_adress_abos_entfernen(conn, APPLE_2, 7, NEU, HOSTS) == 0
    assert len(_abos(conn)) == 5


def test_die_vereinsadresse_loest_auch_die_zwischenadresse_ab(conn):
    upsert_push_subscription(conn, APPLE_1, "p", "a", owner_cid=7, herkunft=NEU)
    upsert_push_subscription(conn, APPLE_2, "p", "a", owner_cid=7, herkunft=VEREIN)
    assert alte_adress_abos_entfernen(conn, APPLE_2, 7, VEREIN, HOSTS) == 1


def test_ohne_mitglied_oder_ueber_die_aelteste_adresse_passiert_nichts(conn):
    upsert_push_subscription(conn, APPLE_1, "p", "a", owner_cid=7)
    upsert_push_subscription(conn, APPLE_2, "p", "a", owner_cid=7, herkunft=ALT)
    assert alte_adress_abos_entfernen(conn, APPLE_2, 7, ALT, HOSTS) == 0
    assert alte_adress_abos_entfernen(conn, APPLE_2, None, NEU, HOSTS) == 0
    assert alte_adress_abos_entfernen(conn, APPLE_2, 7, None, HOSTS) == 0
    assert alte_adress_abos_entfernen(conn, APPLE_2, 7, "fremd.example", HOSTS) == 0
    assert len(_abos(conn)) == 2


# ---- Endpunkt ---------------------------------------------------------------------------

class _Req:
    def __init__(self, host, body, origin=None, kopf=None):
        self.url = SimpleNamespace(hostname=host)
        self._body = body
        self.cookies = {}
        self.headers = {"origin": origin} if origin is not None else {}
        self.headers.update(kopf or {})

    async def json(self):
        return self._body


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    init_db(p)
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(DB_PATH=p, SECRET_KEY="s"))
    monkeypatch.setattr(main, "_current_cid", lambda request, settings: 7)
    return p


def _einschalten(host, endpoint):
    body = {"endpoint": endpoint, "p256dh": "p", "auth": "a"}
    return asyncio.run(main.push_subscribe(_Req(host, body)))


def test_einschalten_ueber_die_neue_adresse_raeumt_das_alte_abo_weg(app_db):
    _einschalten(ALT, APPLE_1)
    _einschalten(NEU, APPLE_2)
    c = get_connection(app_db)
    try:
        assert _abos(c) == {APPLE_2: NEU}
    finally:
        c.close()


def test_nur_das_erste_einschalten_raeumt_auf(app_db):
    """Die Seite schickt ihr Abo bei jedem Laden erneut. Raeumte auch das auf, verloere ein
    Rechner, der bei der alten Adresse bleibt, sein Abo immer wieder -- jedes Mal, wenn das
    Handy desselben Mitglieds die neue Adresse oeffnet."""
    _einschalten(NEU, APPLE_2)
    _einschalten(ALT, APPLE_1)      # der Rechner an der alten Adresse meldet sich (wieder)
    _einschalten(NEU, APPLE_2)      # das Handy laedt die Seite neu
    c = get_connection(app_db)
    try:
        assert _abos(c) == {APPLE_2: NEU, APPLE_1: ALT}
    finally:
        c.close()


@pytest.mark.parametrize("origin", ["https://boese.example", "null"])
def test_eine_fremde_seite_kann_weder_einschalten_noch_aufraeumen(app_db, origin):
    """Das Sitzungs-Cookie traegt SameSite=None (Kniebrett im iframe) und kaeme bei einem
    seitenfremden POST mit. Ohne Pruefung koennte eine fremde Seite im Namen eines Mitglieds ein
    Abo anlegen -- und seit dem Aufraeumen damit dessen echtes Abo loeschen."""
    from fastapi import HTTPException
    _einschalten(ALT, APPLE_1)
    body = {"endpoint": APPLE_2, "p256dh": "p", "auth": "a"}
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.push_subscribe(_Req(NEU, body, origin=origin)))
    assert e.value.status_code == 403
    c = get_connection(app_db)
    try:
        assert set(_abos(c)) == {APPLE_1}
    finally:
        c.close()


def test_die_eigene_seite_darf_einschalten(app_db):
    body = {"endpoint": APPLE_2, "p256dh": "p", "auth": "a"}
    asyncio.run(main.push_subscribe(_Req(NEU, body, origin=f"https://{NEU}")))
    c = get_connection(app_db)
    try:
        assert _abos(c) == {APPLE_2: NEU}
    finally:
        c.close()


@pytest.mark.parametrize("origin, kopf", [
    (f"http://{NEU}", None),                                   # gleicher Host, aber unverschluesselt
    (None, {"sec-fetch-site": "cross-site"}),                  # kein Origin, der Browser sagt es selbst
    (None, {"sec-fetch-site": "same-site"}),                   # Nachbar unter devprops.de, z. B. die Ablage
    (None, {"referer": "https://files.devprops.de/x.html"}),   # alter Browser: nur der Referer
])
def test_die_herkunftspruefung_hat_keine_luecke_ohne_origin(app_db, origin, kopf):
    from fastapi import HTTPException
    body = {"endpoint": APPLE_2, "p256dh": "p", "auth": "a"}
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.push_subscribe(_Req(NEU, body, origin=origin, kopf=kopf)))
    assert e.value.status_code == 403


@pytest.mark.parametrize("kopf", [
    {},                                                         # Kommandozeile: gar nichts
    {"sec-fetch-site": "same-origin"},
    {"sec-fetch-site": "none"},
    {"referer": f"https://{NEU}/"},
])
def test_eigene_aufrufe_ohne_origin_gehen_durch(app_db, kopf):
    body = {"endpoint": APPLE_2, "p256dh": "p", "auth": "a"}
    assert asyncio.run(main.push_subscribe(_Req(NEU, body, kopf=kopf))) == {"status": "ok"}


def test_mit_sitzung_aber_ohne_jede_herkunftsangabe_wird_abgewiesen(app_db):
    """Kein Origin, kein Sec-Fetch-Site, kein Referer: Ein heutiger Browser schickt bei einem POST
    immer mindestens Origin. Kommt trotzdem ein Cookie mit, ist nicht zu beweisen, woher der
    Aufruf stammt -- dann lieber abweisen als durchlassen."""
    from fastapi import HTTPException
    r = _Req(NEU, {"endpoint": APPLE_2, "p256dh": "p", "auth": "a"})
    r.cookies = {"fs_user": "irgendwas"}
    with pytest.raises(HTTPException) as e:
        asyncio.run(main.push_subscribe(r))
    assert e.value.status_code == 403
