"""Getrennte Schalter für Piloten und Lotsen (Wunsch aus dem Forum, 13.10.2026).

Bis 16.5.x hieß der oberste Schalter „Beim Online-gehen benachrichtigen (Piloten und Lotsen)“
und war in Wahrheit der Hauptschalter: aus = gar keine Benachrichtigung. Wer nur Lotsen und
Events wollte, hatte keine Möglichkeit. Jetzt gibt es je einen Schalter für Pilot online,
Flugplan, Lotse online und Lotsenschicht.

Wer schon ein Abo hat, behält alles, was er bekam: beide Online-Schalter stehen auf an, die
Lotsenschichten folgen dem bisherigen „Geplant“-Schalter. Alle Namen sind erfunden.
"""
import asyncio
import json
import sqlite3

import pytest

from app import database as db
from app import poller as poller_mod
from app.database import get_connection, init_db, upsert_push_subscription
from app.poller import VatsimPoller

PILOT = 1000001


@pytest.fixture
def pfad(tmp_path):
    p = str(tmp_path / "t.db")
    init_db(p)
    return p


def _abo(conn, ende="https://push.example/a", **kw):
    upsert_push_subscription(conn, ende, "k", "a", **kw)
    conn.commit()


def _enden(liste):
    return sorted(s["endpoint"] for s in liste)


def _zeile(conn, ende="https://push.example/a"):
    return dict(conn.execute("SELECT * FROM push_subscriptions WHERE endpoint = ?",
                             (ende,)).fetchone())


# --- Vorgaben und Bestand -------------------------------------------------------------------

def test_ein_neues_abo_ohne_angaben_bekommt_beide_online_meldungen(pfad):
    c = get_connection(pfad)
    _abo(c)
    assert _enden(db.get_push_subscriptions_for_pilot(c, PILOT)) == ["https://push.example/a"]
    assert _enden(db.get_push_subscriptions_fuer_lotse_online(c, PILOT)) == ["https://push.example/a"]


@pytest.mark.parametrize("geplant", [True, False])
def test_die_lotsenschichten_folgen_ohne_eigene_angabe_dem_flugplan_schalter(pfad, geplant):
    c = get_connection(pfad)
    _abo(c, notify_prefiles=geplant)
    erwartet = ["https://push.example/a"] if geplant else []
    assert _enden(db.get_push_subscriptions_fuer_lotsenschicht(c, PILOT)) == erwartet


def test_ein_bestehendes_abo_behaelt_nach_der_umstellung_was_es_bekam(tmp_path):
    """Datenbank im Stand vor 16.6.0: Die neuen Spalten fehlen noch."""
    p = str(tmp_path / "alt.db")
    roh = sqlite3.connect(p)
    roh.execute("""CREATE TABLE push_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, endpoint TEXT UNIQUE NOT NULL,
        p256dh TEXT NOT NULL, auth TEXT NOT NULL, pilot_filter TEXT DEFAULT NULL,
        created_at TEXT NOT NULL)""")
    roh.execute("ALTER TABLE push_subscriptions ADD COLUMN notify_prefiles INTEGER DEFAULT 0")
    roh.execute("INSERT INTO push_subscriptions (endpoint, p256dh, auth, created_at, notify_prefiles) "
                "VALUES ('https://push.example/mit', 'k', 'a', '2026-01-01', 1), "
                "       ('https://push.example/ohne', 'k', 'a', '2026-01-01', 0)")
    roh.commit()
    roh.close()
    init_db(p)
    c = get_connection(p)
    beide = ["https://push.example/mit", "https://push.example/ohne"]
    assert _enden(db.get_push_subscriptions_for_pilot(c, PILOT)) == beide
    assert _enden(db.get_push_subscriptions_fuer_lotse_online(c, PILOT)) == beide
    assert _enden(db.get_push_subscriptions_for_prefile(c, PILOT)) == ["https://push.example/mit"]
    assert _enden(db.get_push_subscriptions_fuer_lotsenschicht(c, PILOT)) == ["https://push.example/mit"]


# --- Die vier Schalter einzeln --------------------------------------------------------------

def test_nur_lotsen_wie_im_forum_gewuenscht(pfad):
    c = get_connection(pfad)
    _abo(c, notify_prefiles=False, notify_online_piloten=False, notify_online_lotsen=True,
         notify_lotsenschicht=True, notify_events=True)
    assert db.get_push_subscriptions_for_pilot(c, PILOT) == []
    assert db.get_push_subscriptions_for_prefile(c, PILOT) == []
    assert len(db.get_push_subscriptions_fuer_lotse_online(c, PILOT)) == 1
    assert len(db.get_push_subscriptions_fuer_lotsenschicht(c, PILOT)) == 1
    assert len(db.get_push_subscriptions_for_events(c)) == 1


def test_flugplaene_ja_lotsenschichten_nein(pfad):
    c = get_connection(pfad)
    _abo(c, notify_prefiles=True, notify_lotsenschicht=False)
    assert len(db.get_push_subscriptions_for_prefile(c, PILOT)) == 1
    assert db.get_push_subscriptions_fuer_lotsenschicht(c, PILOT) == []


def test_die_pilotenauswahl_gilt_nicht_mehr_fuer_die_lotsen(pfad):
    """Bis 16.7.0 galt sie auch für Lotsen; seit 16.8.0 haben sie eine eigene Auswahl
    (tests/test_lotsenauswahl.py)."""
    c = get_connection(pfad)
    _abo(c, pilot_filter=[1000002], notify_prefiles=True)
    for abfrage in (db.get_push_subscriptions_fuer_lotse_online,
                    db.get_push_subscriptions_fuer_lotsenschicht):
        assert len(abfrage(c, PILOT)) == 1


def test_eine_alte_seite_ohne_die_neuen_angaben_setzt_nichts_zurueck(pfad):
    """Eine noch geladene alte Fassung der Seite schickt beim Speichern nur die alten Felder.
    Was der Nutzer auf einem anderen Gerät abgewählt hat, darf das nicht wieder einschalten."""
    c = get_connection(pfad)
    _abo(c, notify_prefiles=True, notify_online_piloten=False, notify_online_lotsen=False,
         notify_lotsenschicht=False)
    _abo(c, notify_prefiles=True)
    z = _zeile(c)
    assert (z["notify_online_piloten"], z["notify_online_lotsen"], z["notify_lotsenschicht"]) \
        == (0, 0, 0)


# --- Schnittstelle --------------------------------------------------------------------------

def test_der_abo_endpunkt_nimmt_die_neuen_schalter_an(pfad, monkeypatch):
    from types import SimpleNamespace
    from app import main

    class _Req:
        url = SimpleNamespace(hostname="radar.friesenflieger.de")
        cookies: dict = {}
        headers: dict = {}

        async def json(self):
            return {"endpoint": "https://push.example/a", "p256dh": "k", "auth": "a",
                    "notify_prefiles": True, "notify_online_piloten": False,
                    "notify_online_lotsen": True, "notify_lotsenschicht": False}

    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(DB_PATH=pfad, SECRET_KEY="s"))
    monkeypatch.setattr(main, "_current_cid", lambda request, settings: 7)
    asyncio.run(main.push_subscribe(_Req()))
    z = _zeile(get_connection(pfad))
    assert (z["notify_prefiles"], z["notify_online_piloten"], z["notify_online_lotsen"],
            z["notify_lotsenschicht"]) == (1, 0, 1, 0)


# --- Versand --------------------------------------------------------------------------------

@pytest.fixture
def versand(pfad, monkeypatch):
    gesendet = []

    async def _senden(_priv, _mail, _pfad, subs, payload, label=""):
        gesendet.append((label, _enden(subs)))

    monkeypatch.setattr(poller_mod, "send_web_push", _senden)
    c = get_connection(pfad)
    _abo(c, "https://push.example/piloten", notify_prefiles=True,
         notify_online_lotsen=False, notify_lotsenschicht=False)
    _abo(c, "https://push.example/lotsen", notify_prefiles=False,
         notify_online_piloten=False, notify_lotsenschicht=True)
    c.close()
    p = VatsimPoller(db_path=pfad, callsign_prefix="FRS", poll_interval=60)
    p.vapid_private_key = "x"
    p.vapid_contact_email = "y"
    return p, gesendet


def test_lotse_online_geht_nur_an_die_lotsen_abos(versand):
    p, gesendet = versand
    asyncio.run(p._lotse_push_online({"cid": PILOT, "callsign": "EDDW_TWR"}, {"title": "t"}))
    assert gesendet == [("WebPush[Lotse EDDW_TWR]", ["https://push.example/lotsen"])]


def test_eine_spaete_schicht_geht_nur_an_die_schicht_abos(versand):
    p, gesendet = versand
    asyncio.run(p._lotse_push_buchung({"cid": PILOT, "callsign": "EDDW_TWR"}, {"title": "t"}))
    assert gesendet == [("WebPush[Schicht EDDW_TWR]", ["https://push.example/lotsen"])]


def test_die_morgenmeldung_geht_nur_an_die_schicht_abos(versand):
    p, gesendet = versand
    asyncio.run(p._lotsen_push_morgen([{"cid": PILOT, "callsign": "EDDW_TWR", "name": "Erika", "station": "Bremen Turm",
                                         "beginn": "2026-10-14T17:00:00Z",
                                         "ende": "2026-10-14T19:00:00Z", "id": 1}]))
    assert [enden for _, enden in gesendet] == [["https://push.example/lotsen"]]


def test_pilot_online_geht_nur_an_die_piloten_abos(versand, pfad):
    _, gesendet = versand
    asyncio.run(poller_mod.send_web_push_notifications(
        "x", "y", pfad, {"cid": PILOT, "callsign": "FRS77"}))
    assert [enden for _, enden in gesendet] == [["https://push.example/piloten"]]


# --- Kniebrett ------------------------------------------------------------------------------

def test_im_kniebrett_tragen_lotsenmeldungen_eine_eigene_art(pfad):
    p = VatsimPoller(db_path=pfad, callsign_prefix="FRS", poll_interval=60)
    gesehen = []
    p.broadcast_sse = gesehen.append
    p.broadcast_notify("online", PILOT, {"title": "t", "body": "b"}, art="lotse_online")
    p.broadcast_notify("online", PILOT, {"title": "t", "body": "b"})
    assert [(m["service"], m["art"]) for m in gesehen] == [("online", "lotse_online"),
                                                           ("online", "online")]


# --- Oberfläche -----------------------------------------------------------------------------

import pathlib
import shutil
import subprocess

INDEX = pathlib.Path(__file__).resolve().parents[1].joinpath("app/static/index.html").read_text("utf-8")
ADMIN = pathlib.Path(__file__).resolve().parents[1].joinpath("app/static/admin.html").read_text("utf-8")
_NODE = shutil.which("node")


def test_der_hauptschalter_heisst_wie_er_wirkt():
    assert 'id="notif-enabled"> Benachrichtigungen auf diesem Gerät' in INDEX
    assert "Beim Online-gehen benachrichtigen" not in INDEX


@pytest.mark.parametrize("kennung, text", [
    ("notif-online-piloten", "Wenn ein Pilot online geht"),
    ("notif-prefiles", "Wenn ein Pilot einen Flugplan einreicht"),
    ("notif-online-lotsen", "Wenn ein Lotse online geht"),
    ("notif-lotsenschicht", "Gebuchte Lotsenschichten"),
])
def test_die_vier_schalter_stehen_auf_der_website(kennung, text):
    assert f'id="{kennung}" checked> {text}' in INDEX


@pytest.mark.parametrize("art, text", [
    ("online", "Wenn ein Pilot online geht"),
    ("prefile", "Wenn ein Pilot einen Flugplan einreicht"),
    ("lotse_online", "Wenn ein Lotse online geht"),
    ("lotse_schicht", "Gebuchte Lotsenschichten"),
])
def test_die_vier_schalter_stehen_im_kniebrett(art, text):
    assert f'id="panel-notif-{art}" data-art="{art}">\n        <span class="panel-notif-kasten">[ ]</span> {text}' in INDEX


def test_speichern_schickt_die_neuen_schalter_mit():
    start = INDEX.index("async function _saveNotifFilter")
    rumpf = INDEX[start:INDEX.index("\n}\n", start)]
    for feld in ("notify_online_piloten", "notify_online_lotsen", "notify_lotsenschicht"):
        assert f"{feld}:" in rumpf


@pytest.mark.parametrize("name", ["index", "admin"])
def test_die_neuen_schalter_ziehen_beim_adresswechsel_mit(name):
    seite = INDEX if name == "index" else ADMIN
    for k in ("notif_online_piloten", "notif_online_lotsen", "notif_lotsenschicht"):
        assert f"'{k}'" in seite[seite.index("var UMZUG_SPEICHER"):seite.index("];", seite.index("var UMZUG_SPEICHER"))]


def _kniebrett_schalter(gespeichert: dict) -> dict:
    start = INDEX.index("const _PANEL_NOTIFY_KEY")
    ende = INDEX.index("function _panelNotifySetzen")
    js = ("const speicher = " + json.dumps(gespeichert) + ";\n"
          "global.localStorage = { getItem: (k) => k in speicher ? speicher[k] : null };\n"
          + INDEX[start:ende] + "\nconsole.log(JSON.stringify(_panelNotifyEinstellung()));")
    p = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@pytest.mark.skipif(_NODE is None, reason="node fehlt")
def test_im_kniebrett_erben_die_lotsen_was_vorher_galt():
    """Wer im Tablet „online“ abgewählt hatte, wählte damit auch die Lotsen ab."""
    z = _kniebrett_schalter({"friesenspy_panel_notify_online": "0",
                             "friesenspy_panel_notify_prefile": "0"})
    assert (z["lotse_online"], z["lotse_schicht"]) == (False, False)
    z = _kniebrett_schalter({"friesenspy_panel_notify_online": "0",
                             "friesenspy_panel_notify_lotse_online": "1"})
    assert (z["online"], z["lotse_online"], z["lotse_schicht"]) == (False, True, True)


def test_das_kniebrett_filtert_nach_der_art_der_meldung():
    start = INDEX.index("function _panelBenachrichtigung")
    rumpf = INDEX[start:INDEX.index("\n}\n", start)]
    assert "const art = msg.art || msg.service || '';" in rumpf
