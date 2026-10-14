"""Eigene Auswahl für Lotsen in den Benachrichtigungen (16.8.0, Wunsch des Nutzers 14.10.2026).

Bis 16.7.0 gab es eine einzige Personenauswahl, und die galt auch für Lotsen. Wer nur bestimmte
Piloten wollte, bekam damit auch nur diese als Lotsen -- und reine Lotsen standen gar nicht
erst in der Liste. Jetzt gilt: Pilotenauswahl für Pilot online, Flugplan und TeamSpeak,
Lotsenauswahl für Lotse online und Lotsenschichten. Beim Update übernimmt jedes Abo seine
Pilotenauswahl einmalig auch für Lotsen, damit sich für niemanden etwas ändert.
Alle Namen sind erfunden.
"""
import asyncio
import json
import pathlib
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone

import pytest

from app import database as db
from app.database import KEINE_ANGABE, get_connection, init_db, upsert_push_subscription
from app.poller import VatsimPoller

PILOT, LOTSE, ANDERE = 1000001, 1000002, 1000004
ENDE = "https://push.example/a"

INDEX = pathlib.Path(__file__).resolve().parents[1].joinpath("app/static/index.html").read_text("utf-8")
ADMIN = pathlib.Path(__file__).resolve().parents[1].joinpath("app/static/admin.html").read_text("utf-8")
_NODE = shutil.which("node")


@pytest.fixture
def pfad(tmp_path):
    p = str(tmp_path / "t.db")
    init_db(p)
    c = get_connection(p)
    c.execute("INSERT INTO pilots (cid, name, added_at, active) VALUES (1000001, 'Erika Muster', '2026-01-01', 1)")
    c.execute("INSERT INTO pilots (cid, name, added_at, active) VALUES (1000003, 'Aus Geschaltet', '2026-01-01', 0)")
    for cs, cid in (("FRS12", LOTSE), ("FRS77", ANDERE), ("FRS13", 1000003)):
        c.execute("INSERT INTO forum_callsign (callsign, cid, updated_at) VALUES (?, ?, '2026-01-01')",
                  (cs, cid))
    c.commit()
    c.close()
    return p


def _abo(conn, **kw):
    upsert_push_subscription(conn, ENDE, "k", "a", **kw)
    conn.commit()


def _lotse_filter(conn):
    return conn.execute("SELECT lotse_filter FROM push_subscriptions WHERE endpoint = ?",
                        (ENDE,)).fetchone()[0]


def _bekommt(liste) -> bool:
    return [s["endpoint"] for s in liste] == [ENDE]


# --- Bestand beim Update --------------------------------------------------------------------

def _alte_db(tmp_path, pilot_filter):
    """Datenbank im Stand von 16.7.0: Die Spalte lotse_filter fehlt."""
    p = str(tmp_path / "alt.db")
    init_db(p)
    roh = sqlite3.connect(p)
    roh.execute("ALTER TABLE push_subscriptions DROP COLUMN lotse_filter")
    roh.execute("INSERT INTO push_subscriptions (endpoint, p256dh, auth, pilot_filter, created_at) "
                "VALUES (?, 'k', 'a', ?, '2026-01-01')", (ENDE, pilot_filter))
    roh.commit()
    roh.close()
    return p


def test_eine_bestehende_pilotenauswahl_gilt_nach_dem_update_auch_fuer_lotsen(tmp_path):
    p = _alte_db(tmp_path, json.dumps([LOTSE]))
    init_db(p)
    c = get_connection(p)
    assert json.loads(_lotse_filter(c)) == [LOTSE]
    assert not _bekommt(db.get_push_subscriptions_fuer_lotse_online(c, ANDERE))
    assert _bekommt(db.get_push_subscriptions_fuer_lotse_online(c, LOTSE))


def test_ohne_pilotenauswahl_bleiben_nach_dem_update_alle_lotsen(tmp_path):
    p = _alte_db(tmp_path, None)
    init_db(p)
    c = get_connection(p)
    assert _lotse_filter(c) is None


def test_die_uebernahme_laeuft_nur_einmal(tmp_path):
    """Wer danach „Alle Lotsen“ wählt, darf beim nächsten Start nicht wieder die
    Pilotenauswahl bekommen."""
    p = _alte_db(tmp_path, json.dumps([LOTSE]))
    init_db(p)
    c = get_connection(p)
    _abo(c, pilot_filter=[LOTSE], lotse_filter=None)
    c.close()
    init_db(p)
    assert _lotse_filter(get_connection(p)) is None


# --- Wer bekommt was ------------------------------------------------------------------------

def test_bestimmte_piloten_aber_alle_lotsen(pfad):
    """Der Fall aus der Nachricht des Nutzers."""
    c = get_connection(pfad)
    _abo(c, pilot_filter=[PILOT], lotse_filter=None, notify_prefiles=True)
    assert _bekommt(db.get_push_subscriptions_for_pilot(c, PILOT))
    assert not _bekommt(db.get_push_subscriptions_for_pilot(c, ANDERE))
    assert not _bekommt(db.get_push_subscriptions_for_prefile(c, ANDERE))
    for cid in (PILOT, LOTSE, ANDERE):
        assert _bekommt(db.get_push_subscriptions_fuer_lotse_online(c, cid))
        assert _bekommt(db.get_push_subscriptions_fuer_lotsenschicht(c, cid))


def test_alle_piloten_aber_bestimmte_lotsen(pfad):
    c = get_connection(pfad)
    _abo(c, pilot_filter=None, lotse_filter=[LOTSE], notify_prefiles=True)
    assert _bekommt(db.get_push_subscriptions_for_pilot(c, ANDERE))
    assert _bekommt(db.get_push_subscriptions_for_prefile(c, ANDERE))
    assert _bekommt(db.get_push_subscriptions_fuer_lotse_online(c, LOTSE))
    assert not _bekommt(db.get_push_subscriptions_fuer_lotse_online(c, ANDERE))
    assert not _bekommt(db.get_push_subscriptions_fuer_lotsenschicht(c, ANDERE))


def test_teamspeak_folgt_der_pilotenauswahl(pfad):
    c = get_connection(pfad)
    _abo(c, pilot_filter=[PILOT], lotse_filter=[LOTSE], notify_ts=True)
    assert _bekommt(db.get_ts_push_subscriptions(c, PILOT))
    assert not _bekommt(db.get_ts_push_subscriptions(c, LOTSE))


def test_eine_leere_lotsenauswahl_heisst_niemand(pfad):
    c = get_connection(pfad)
    _abo(c, lotse_filter=[])
    assert not _bekommt(db.get_push_subscriptions_fuer_lotse_online(c, LOTSE))


# --- Speichern ------------------------------------------------------------------------------

def test_eine_seite_ohne_lotsenauswahl_laesst_die_gespeicherte_stehen(pfad):
    """Eine noch geladene ältere Fassung schickt das Feld nicht mit."""
    c = get_connection(pfad)
    _abo(c, lotse_filter=[LOTSE])
    _abo(c, pilot_filter=[PILOT])
    assert json.loads(_lotse_filter(c)) == [LOTSE]
    upsert_push_subscription(c, ENDE, "k", "a", lotse_filter=KEINE_ANGABE)
    assert json.loads(_lotse_filter(c)) == [LOTSE]


def test_alle_lotsen_ueberschreibt_eine_auswahl(pfad):
    c = get_connection(pfad)
    _abo(c, lotse_filter=[LOTSE])
    _abo(c, lotse_filter=None)
    assert _lotse_filter(c) is None


def test_ein_neues_abo_ohne_angabe_bekommt_alle_lotsen(pfad):
    c = get_connection(pfad)
    _abo(c, pilot_filter=[PILOT])
    assert _lotse_filter(c) is None


class _Req:
    def __init__(self, body):
        from types import SimpleNamespace
        self.url = SimpleNamespace(hostname="radar.friesenflieger.de")
        self.cookies, self.headers, self._body = {}, {}, body

    async def json(self):
        return self._body


@pytest.fixture
def main_mit_db(pfad, monkeypatch):
    from types import SimpleNamespace
    from app import main
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(DB_PATH=pfad, SECRET_KEY="s"))
    monkeypatch.setattr(main, "_current_cid", lambda request, settings: 7)
    return main


def test_der_abo_endpunkt_nimmt_die_lotsenauswahl_an(pfad, main_mit_db):
    roh = {"endpoint": ENDE, "p256dh": "k", "auth": "a"}
    asyncio.run(main_mit_db.push_subscribe(_Req(dict(roh, lotse_filter=[LOTSE]))))
    assert json.loads(_lotse_filter(get_connection(pfad))) == [LOTSE]
    asyncio.run(main_mit_db.push_subscribe(_Req(dict(roh, pilot_filter=[PILOT]))))
    assert json.loads(_lotse_filter(get_connection(pfad))) == [LOTSE]
    asyncio.run(main_mit_db.push_subscribe(_Req(dict(roh, lotse_filter=None))))
    assert _lotse_filter(get_connection(pfad)) is None


# --- Die Liste zur Auswahl ------------------------------------------------------------------

def test_oben_wer_gelotst_hat_darunter_alle_uebrigen(pfad):
    """Wunsch des Nutzers 14.10.2026: einen Verlauf gibt es erst seit 16.8.0, deshalb stehen
    alle Friesen drin -- wer schon gelotst hat, oben."""
    c = get_connection(pfad)
    db.lotsen_gesehen_merken(c, [LOTSE], "2026-10-14T10:00:00Z")
    c.commit()
    assert db.lotsen_zur_auswahl(c) == [
        {"cid": LOTSE, "name": "FRS12", "gelotst": True},
        {"cid": PILOT, "name": "Erika Muster", "gelotst": False},
        {"cid": ANDERE, "name": "FRS77", "gelotst": False}]


def test_wer_vor_dem_update_gelotst_hat_steht_auch_oben(pfad):
    """Ein gemerkter Lotsenname heißt: hat schon gelotst (der Fall vom 10.10.2026)."""
    c = get_connection(pfad)
    db.lotsen_name_merken(c, ANDERE, "Simon Beispiel", "2026-10-10T13:38:03Z")
    c.commit()
    assert db.lotsen_zur_auswahl(c)[0] == {"cid": ANDERE, "name": "Simon Beispiel", "gelotst": True}


def test_abgeschaltete_und_fremde_stehen_nicht_in_der_liste(pfad):
    c = get_connection(pfad)
    db.lotsen_gesehen_merken(c, [1000003, 9999999], "2026-10-14T10:00:00Z")
    cids = {e["cid"] for e in db.lotsen_zur_auswahl(c)}
    assert 1000003 not in cids and 9999999 not in cids


def test_der_endpunkt_liefert_die_liste(pfad, main_mit_db):
    antwort = asyncio.run(main_mit_db.get_lotsen_auswahl())
    assert {e["cid"] for e in antwort["lotsen"]} == {PILOT, LOTSE, ANDERE}


# --- Namen: nie die Nummer ------------------------------------------------------------------

@pytest.mark.parametrize("name, verborgen", [
    ("1948215", True), ("1948215 ETNW", True), ("", True), (None, True),
    ("Erika Muster", False), ("Erika 1948215", False), ("19482150 Muster", False)])
def test_eine_nummer_ist_kein_name(name, verborgen):
    assert db.name_verborgen(1948215, name) is verborgen


def _verborgener_pilot(c, cid=1948215, flug="FRS331N"):
    c.execute("INSERT INTO pilots (cid, name, added_at, active) VALUES (?, ?, '2026-01-01', 1)",
              (cid, f"{cid} ETNW"))
    if flug:
        c.execute("INSERT INTO flights (cid, callsign, logon_time) VALUES (?, ?, '2026-10-04T18:08:10Z')",
                  (cid, flug))
    c.commit()


def test_verborgener_name_wird_zum_zuletzt_geflogenen_rufzeichen(pfad):
    c = get_connection(pfad)
    _verborgener_pilot(c)
    assert db.lotsen_bekannte(c)[1948215] == "FRS331N"


def test_das_forum_rufzeichen_geht_dem_geflogenen_vor(pfad):
    c = get_connection(pfad)
    _verborgener_pilot(c)
    c.execute("INSERT INTO forum_callsign (callsign, cid, updated_at) VALUES ('FRS331', 1948215, '2026-01-01')")
    assert db.lotsen_bekannte(c)[1948215] == "FRS331"


def test_der_forumsname_geht_dem_rufzeichen_vor(pfad):
    c = get_connection(pfad)
    _verborgener_pilot(c)
    db.forum_name_merken(c, 1948215, "Hein Mück")
    assert db.lotsen_bekannte(c)[1948215] == "Hein Mück"
    db.forum_name_merken(c, 1948215, "")
    assert db.lotsen_bekannte(c)[1948215] == "FRS331N"


def test_ein_echter_vatsim_name_geht_allem_vor(pfad):
    c = get_connection(pfad)
    db.forum_name_merken(c, PILOT, "erika_forum")
    assert db.lotsen_bekannte(c)[PILOT] == "Erika Muster"


def test_ohne_jede_quelle_heisst_er_ein_friese(pfad):
    c = get_connection(pfad)
    _verborgener_pilot(c, flug=None)
    assert db.lotsen_bekannte(c)[1948215] == "Ein Friese"


def test_der_login_merkt_sich_den_forumsnamen():
    import pathlib
    quelle = pathlib.Path(__file__).resolve().parents[1].joinpath("app/main.py").read_text("utf-8")
    rumpf = quelle[quelle.index("    # Benutzername aus dem Forum: Rückfall"):]
    rumpf = rumpf[:rumpf.index("    # Autoritative Callsign")]
    assert 'forum_name_merken(conn, int(str(claims.get("cid")).strip()),' in rumpf


def _poller(pfad):
    p = VatsimPoller(db_path=pfad, callsign_prefix="FRS", poll_interval=60)
    p.broadcast_notify = lambda *a, **kw: None

    async def _nichts(*a, **kw):
        return None

    p._lotse_push_online = _nichts
    return p


def _gesehen(pfad):
    return {r[0] for r in get_connection(pfad).execute("SELECT cid FROM lotsen_gesehen")}


def test_wer_als_lotse_online_ist_wird_vorgemerkt(pfad):
    p = _poller(pfad)
    p._lotsen_aus_feed({"controllers": [
        {"cid": LOTSE, "name": "egal", "callsign": "EDDW_TWR", "frequency": "118.505",
         "facility": 4, "text_atis": [], "logon_time": "2026-10-14T09:00:00Z"}]}, set())
    assert _gesehen(pfad) == {LOTSE}


def test_vorgemerkt_wird_nur_einmal(pfad, monkeypatch):
    """Der Feed kommt alle 15 s; geschrieben werden soll nur, wenn jemand neu ist."""
    p = _poller(pfad)
    c = get_connection(pfad)
    jetzt = datetime(2026, 10, 14, tzinfo=timezone.utc)
    assert p._lotsen_vormerken(c, [LOTSE], jetzt) is True
    assert p._lotsen_vormerken(c, [LOTSE], jetzt) is False


def test_wer_eine_schicht_bucht_wird_vorgemerkt(pfad):
    p = _poller(pfad)
    p._now = lambda: datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)

    class _Antwort:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"id": 1, "cid": ANDERE, "callsign": "EDDH_TWR", "type": "booking",
                     "start": "2026-10-14 17:00:00", "end": "2026-10-14 19:00:00"}]

    class _Client:
        async def get(self, *a, **kw):
            return _Antwort()

    p._http_client = _Client()
    asyncio.run(p._lotsen_buchungen_holen())
    assert [b["cid"] for b in p.lotsen_buchungen] == [ANDERE]
    assert _gesehen(pfad) == {ANDERE}


# --- Oberfläche -----------------------------------------------------------------------------

def test_die_website_hat_zwei_auswahlen():
    assert 'name="notif-filter-mode" value="select"> Nur bestimmte Piloten' in INDEX
    assert 'name="notif-lotse-mode" value="select"> Nur bestimmte Lotsen' in INDEX
    assert '<div id="notif-lotse-list" hidden></div>' in INDEX


@pytest.mark.skipif(_NODE is None, reason="node fehlt")
def test_zwischen_den_gruppen_steht_ein_strich():
    html = _js({}, "_notifLotseListeHtml([{cid:1,name:'A',gelotst:true},{cid:2,name:'B',gelotst:false}])")
    assert html.index('data-cid="1"') < html.index('notif-lotse-strich') < html.index('data-cid="2"')
    assert 'notif-lotse-strich' not in _js({}, "_notifLotseListeHtml([{cid:2,name:'B',gelotst:false}])")


def test_speichern_schickt_die_lotsenauswahl_mit():
    start = INDEX.index("async function _saveNotifFilter")
    rumpf = INDEX[start:INDEX.index("\n}\n", start)]
    assert "lotse_filter: lotseFilter," in rumpf
    assert "localStorage.setItem('notif_lotse_filter', JSON.stringify(lotseFilter));" in rumpf


@pytest.mark.parametrize("seite", [INDEX, ADMIN])
def test_die_lotsenauswahl_zieht_beim_adresswechsel_mit(seite):
    a = seite.index("var UMZUG_SPEICHER")
    assert "'notif_lotse_filter'" in seite[a:seite.index("];", a)]


def _js(speicher: dict, ausdruck: str):
    start = INDEX.index("// LOTSENAUSWAHL-ANFANG")
    ende = INDEX.index("// LOTSENAUSWAHL-ENDE")
    js = ("const speicher = " + json.dumps(speicher) + ";\n"
          "global.localStorage = { getItem: (k) => k in speicher ? speicher[k] : null };\n"
          "global.document = { getElementById: () => null, querySelector: () => null };\n"
          "global.escHtml = (t) => String(t);\n"
          + INDEX[start:ende] + "\nconsole.log(JSON.stringify(" + ausdruck + "));")
    p = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@pytest.mark.skipif(_NODE is None, reason="node fehlt")
def test_ohne_eigenen_eintrag_gilt_die_pilotenauswahl():
    """So hat der Server sie beim Update übernommen; die Seite muss dasselbe zeigen."""
    assert _js({"notif_pilot_filter": "[1,2]"}, "_notifLotseGespeichert()") == [1, 2]
    assert _js({}, "_notifLotseGespeichert()") is None


@pytest.mark.skipif(_NODE is None, reason="node fehlt")
def test_alle_lotsen_ist_ein_eigener_eintrag():
    assert _js({"notif_pilot_filter": "[1,2]", "notif_lotse_filter": "null"},
               "_notifLotseGespeichert()") is None
    assert _js({"notif_lotse_filter": "[3]"}, "_notifLotseGespeichert()") == [3]
