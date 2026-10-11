"""Ersatzweg bei stehendem VATSIM-Hauptfeed (#63). Alle Nummern und Namen sind erfunden."""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app import ersatzweg
from app.database import get_connection, init_db
from app.poller import VatsimPoller

UTC = timezone.utc
JETZT = datetime(2026, 10, 11, 11, 0, 0, tzinfo=UTC)
CID = 1000001


@pytest.fixture
def pfad(tmp_path):
    p = str(tmp_path / "t.db")
    init_db(p)
    c = get_connection(p)
    c.execute("INSERT INTO pilots (cid, name, added_at, active) VALUES (?, 'Erika Muster', '2026-01-01', 1)", (CID,))
    c.execute("INSERT INTO forum_callsign (callsign, cid, updated_at) VALUES ('FRS61', ?, '2026-01-01')", (CID,))
    c.commit()
    c.close()
    return p


class Welt:
    """Was VATSIM gerade liefert -- je Quelle einzeln stellbar."""

    def __init__(self):
        self.feed = {"general": {"update_timestamp": "2026-10-11T03:08:12.2684332Z"},
                     "pilots": [], "controllers": [], "prefiles": []}
        self.funk = []
        self.funk_stand = time.time() - 60
        self.status = {}
        self.lotsen = []
        self.funk_abrufe = 0
        self.status_abrufe = 0
        self.funk_kaputt = False

    def fliegt(self, cs, lat, lon, hoehe_m=1271.6):
        self.funk = [e for e in self.funk if e["callsign"] != cs]
        self.funk.append({"callsign": cs, "transceivers": [
            {"id": 1, "frequency": 122800010, "latDeg": lat, "lonDeg": lon,
             "heightMslM": hoehe_m, "heightAglM": hoehe_m}]})

    def weiter(self, sek=15):
        self.funk_stand += sek


def _status(cs="FRS61", start="2026-10-11T08:46:23Z", plan=True):
    fp = {"flight_type": "VFR", "callsign": cs, "aircraft": "LEG2/L-SDGRY/S", "cruisespeed": "181",
          "dep": "EGPB", "arr": "BIEG", "alt": "BIAR", "altitude": "8500", "rmks": "RMK/TEST",
          "route": "RIXUN DCT MY", "deptime": "0900", "hrsenroute": 2, "minenroute": 58,
          "hrsfuel": 4, "minsfuel": 41} if plan else None
    return {"id": "x", "callsign": cs, "start": start, "fp": fp}


def _pilot_im_feed(logon="2026-10-11T08:46:23.4967831Z", lat=64.0, lon=-12.0):
    return {"cid": CID, "name": "Erika Muster", "callsign": "FRS61", "latitude": lat,
            "longitude": lon, "altitude": 4000, "groundspeed": 150, "heading": 300,
            "logon_time": logon, "last_updated": "x",
            "flight_plan": {"aircraft_short": "LEG2", "departure": "EGPB", "arrival": "BIEG"}}


def _poller(pfad, welt):
    p = VatsimPoller(db_path=pfad, callsign_prefix="FRS", poll_interval=60)
    p._http_client = object()
    p._now = lambda: JETZT
    p.gesendet = []
    p.broadcast_notify = lambda dienst, cid, payload, nur_cid=None: p.gesendet.append((dienst, cid))
    return p


def _poll(p, welt):
    async def feed(_client):
        return welt.feed

    async def funk(_client):
        welt.funk_abrufe += 1
        if welt.funk_kaputt:
            raise RuntimeError("Funkliste weg")
        return welt.funk, welt.funk_stand

    async def status(_client, cid):
        welt.status_abrufe += 1
        antwort = welt.status.get(cid)
        if isinstance(antwort, Exception):
            raise antwort
        return antwort

    async def lotsen(_client):
        return welt.lotsen

    with patch("app.poller.fetch_vatsim_data", new=feed), \
         patch("app.ersatzweg.hole_funkliste", new=funk), \
         patch("app.ersatzweg.hole_status", new=status), \
         patch("app.ersatzweg.hole_lotsenliste", new=lotsen):
        asyncio.run(p._poll_once())


def _fluege(pfad):
    c = get_connection(pfad)
    try:
        return [dict(r) for r in c.execute("SELECT * FROM flights ORDER BY id")]
    finally:
        c.close()


def _spur(pfad):
    c = get_connection(pfad)
    try:
        return [dict(r) for r in c.execute("SELECT * FROM position_history ORDER BY id")]
    finally:
        c.close()


def _frischer_feed(welt, *pilots):
    welt.feed = {"general": {"update_timestamp": (JETZT - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")},
                 "pilots": list(pilots), "controllers": [], "prefiles": []}


# --- reine Funktionen ----------------------------------------------------------------------

def test_stillstand_wird_am_alter_des_standes_erkannt():
    assert ersatzweg.feed_steht({"general": {"update_timestamp": "2026-10-11T03:08:12.2684332Z"}}, JETZT)
    assert not ersatzweg.feed_steht({"general": {"update_timestamp": "2026-10-11T10:59:30.1Z"}}, JETZT)
    assert not ersatzweg.feed_steht({"pilots": []}, JETZT), "ohne Zeitstempel gilt der Feed als laufend"


def test_flugplan_aus_der_statusabfrage_hat_die_form_des_feeds():
    fp = ersatzweg.flugplan_aus_status(_status())
    assert fp["aircraft_short"] == "LEG2" and fp["departure"] == "EGPB" and fp["arrival"] == "BIEG"
    assert fp["flight_rules"] == "V" and fp["enroute_time"] == "0258" and fp["fuel_time"] == "0441"
    assert fp["alternate"] == "BIAR" and fp["altitude"] == "8500" and fp["cruise_tas"] == "181"
    assert ersatzweg.flugplan_aus_status(_status(plan=False)) is None
    assert ersatzweg._typ_kurz("H/B744/L") == "B744"


def test_fahrt_aus_zwei_positionen():
    f = ersatzweg.Fahrtrechner()
    assert f.rechne("A", 54.0, 8.0, 0.0) is None, "ein Punkt allein ergibt keine Fahrt"
    assert f.rechne("A", 54.0, 8.0, 15.0) is None, "unveränderte Liste ist noch kein Stillstand"
    gs, hdg = f.rechne("A", 54.0 + 1 / 60, 8.0, 30.0)   # 1 NM nach Norden in 30 s
    assert 118 <= gs <= 122 and hdg == 0
    assert f.rechne("A", 54.0 + 1 / 60, 8.0, 45.0) == (gs, hdg), "kurz unverändert: Wert bleibt"
    assert f.rechne("A", 54.0 + 1 / 60, 8.0, 90.0) == (0, 0), "lange unverändert: steht"


def test_wer_von_anfang_an_steht_bekommt_null_knoten():
    f = ersatzweg.Fahrtrechner()
    assert f.rechne("A", 54.0, 8.0, 0.0) is None
    assert f.rechne("A", 54.0, 8.0, 60.0) == (0, 0)


def test_ein_sprung_ergibt_keine_fahrt():
    f = ersatzweg.Fahrtrechner()
    f.rechne("A", 54.0, 8.0, 0.0)
    assert f.rechne("A", 10.0, 8.0, 15.0) is None and f.spruenge == {"A"}


def test_versatz_bei_gleichem_listenstand_ist_ein_sprung():
    f = ersatzweg.Fahrtrechner()
    f.rechne("A", 54.0, 8.0, 100.0)
    assert f.rechne("A", 54.1, 8.0, 100.0) is None and f.spruenge == {"A"}
    f.spruenge.clear()
    f.rechne("B", 54.0, 8.0, 100.0)
    f.rechne("B", 54.0001, 8.0, 100.0)
    assert f.spruenge == set(), "ein paar Meter sind kein Sprung"


def test_fuenf_meilen_in_einem_zyklus_sind_ein_sprung():
    f = ersatzweg.Fahrtrechner()
    f.rechne("A", 54.0, 8.0, 0.0)
    assert f.rechne("A", 54.0 + 5 / 60, 8.0, 15.0) is None and f.spruenge == {"A"}


def test_funkliste_ohne_funkgeraet_und_null_null_fehlen():
    roh = [{"callsign": "A", "transceivers": []},
           {"callsign": "B", "transceivers": [{"latDeg": 0, "lonDeg": 0, "heightMslM": 1}]},
           {"callsign": "EDGG_CTR", "transceivers": [{"latDeg": 50.0, "lonDeg": 8.0, "heightMslM": 100}]},
           {"callsign": "c", "transceivers": [{"latDeg": 54.0, "lonDeg": 8.0, "heightMslM": 304.8}]}]
    assert ersatzweg.funk_positionen(roh) == {"C": (54.0, 8.0, 1000)}


# --- der Poller ----------------------------------------------------------------------------

def test_laufender_feed_fragt_die_funkliste_nie(pfad):
    welt = Welt()
    _frischer_feed(welt, _pilot_im_feed())
    p = _poller(pfad, welt)
    _poll(p, welt)
    assert welt.funk_abrufe == 0 and not p.ersatzweg_aktiv
    assert len(_fluege(pfad)) == 1


def test_stehender_feed_schreibt_den_flug_aus_funkliste_und_status(pfad):
    welt = Welt()
    welt.status[CID] = _status()
    welt.fliegt("FRS61", 64.0, -12.0)
    p = _poller(pfad, welt)
    _poll(p, welt)
    assert p.ersatzweg_aktiv
    assert _fluege(pfad) == [], "ein Punkt allein: Fahrt steht noch nicht fest"
    welt.weiter(15)
    welt.fliegt("FRS61", 64.0 + 0.5 / 60, -12.0)
    _poll(p, welt)
    fluege = _fluege(pfad)
    assert len(fluege) == 1
    f = fluege[0]
    assert (f["cid"], f["callsign"], f["departure"], f["arrival"]) == (CID, "FRS61", "EGPB", "BIEG")
    assert f["logon_time"] == "2026-10-11T08:46:23Z" and f["aircraft_short"] == "LEG2"
    assert f["logoff_time"] is None
    spur = _spur(pfad)
    assert len(spur) == 1 and 115 <= spur[0]["groundspeed"] <= 125 and spur[0]["heading"] == 0
    assert spur[0]["altitude"] == 4172
    assert ("online", CID) in p.gesendet
    assert welt.status_abrufe == 1, "eine Statusabfrage je Flug, nicht je Zyklus"
    assert [e for e in p.traffic_snapshot] == [], "ein Friese ist kein Fremdverkehr"


def test_wechsel_zurueck_auf_den_feed_fuehrt_denselben_flug_weiter(pfad):
    welt = Welt()
    welt.status[CID] = _status()
    welt.fliegt("FRS61", 64.0, -12.0)
    p = _poller(pfad, welt)
    _poll(p, welt)
    welt.weiter(15)
    welt.fliegt("FRS61", 64.01, -12.0)
    _poll(p, welt)
    _frischer_feed(welt, _pilot_im_feed(lat=64.02))
    _poll(p, welt)
    assert not p.ersatzweg_aktiv
    fluege = _fluege(pfad)
    assert len(fluege) == 1 and fluege[0]["logoff_time"] is None
    assert len(_spur(pfad)) == 2
    c = get_connection(pfad)
    try:
        live = c.execute("SELECT logon_time FROM live_positions WHERE cid = ?", (CID,)).fetchone()
        fenster = [tuple(r) for r in c.execute("SELECT von, bis FROM feed_ersatzweg")]
    finally:
        c.close()
    assert live["logon_time"] == "2026-10-11T08:46:23Z", "eine Verbindung, eine Schreibweise"
    assert fenster == [("2026-10-11T11:00:00Z", "2026-10-11T11:00:00Z")]
    assert p.gesendet.count(("online", CID)) == 1


def test_flug_von_vor_dem_stillstand_ueberlebt_das_einschalten(pfad):
    welt = Welt()
    _frischer_feed(welt, _pilot_im_feed())
    p = _poller(pfad, welt)
    _poll(p, welt)
    stehend = Welt().feed
    stehend["pilots"] = [_pilot_im_feed()]
    welt.feed = stehend
    welt.status[CID] = _status()
    welt.fliegt("FRS61", 64.05, -12.1)
    _poll(p, welt)                      # erster Zyklus im Ersatzweg: noch keine Fahrt
    fluege = _fluege(pfad)
    assert len(fluege) == 1 and fluege[0]["logoff_time"] is None
    spur = _spur(pfad)
    assert len(spur) == 2 and spur[1]["latitude"] == 64.05 and spur[1]["groundspeed"] == 150
    assert fluege[0]["logon_time"] == "2026-10-11T08:46:23.4967831Z"


def test_wer_nicht_mehr_in_der_funkliste_steht_wird_nach_der_karenz_abgemeldet(pfad):
    welt = Welt()
    _frischer_feed(welt, _pilot_im_feed())
    p = _poller(pfad, welt)
    _poll(p, welt)
    stehend = Welt().feed
    stehend["pilots"] = [_pilot_im_feed()]   # der stehende Feed zeigt ihn weiter
    welt.feed = stehend
    for _ in range(ersatzweg.KARENZ_ZYKLEN):
        _poll(p, welt)
        assert _fluege(pfad)[0]["logoff_time"] is None, "eine Lücke meldet niemanden ab"
    _poll(p, welt)
    assert _fluege(pfad)[0]["logoff_time"] is not None


def test_nach_neustart_im_stillstand_bleibt_es_bei_einer_flugzeile(pfad):
    welt = Welt()
    _frischer_feed(welt, _pilot_im_feed())
    p = _poller(pfad, welt)
    _poll(p, welt)                       # Flug unter der Schreibweise des Feeds geöffnet
    p2 = _poller(pfad, welt)             # Neustart: alle Merker leer, Flug geschlossen
    c = get_connection(pfad)
    c.execute("UPDATE flights SET logoff_time = '2026-10-11T10:59:00Z'")
    c.execute("DELETE FROM live_positions")
    c.commit()
    c.close()
    welt.feed = Welt().feed
    welt.status[CID] = _status()
    welt.fliegt("FRS61", 64.0, -12.0)
    _poll(p2, welt)
    welt.weiter(15)
    welt.fliegt("FRS61", 64.01, -12.0)
    _poll(p2, welt)
    fluege = _fluege(pfad)
    assert len(fluege) == 1 and fluege[0]["logoff_time"] is None, "wieder geöffnet, nicht neu angelegt"


def test_steht_auch_die_funkliste_faellt_der_zyklus_aus(pfad):
    welt = Welt()
    welt.status[CID] = _status()
    welt.fliegt("FRS61", 64.0, -12.0)
    welt.funk_stand = time.time() - 600
    p = _poller(pfad, welt)
    _poll(p, welt)
    _poll(p, welt)
    assert _fluege(pfad) == [] and p.traffic_snapshot == []


def test_unbekanntes_rufzeichen_wird_nicht_geschrieben(pfad):
    welt = Welt()
    welt.fliegt("FRS999", 54.0, 8.0)
    p = _poller(pfad, welt)
    _poll(p, welt)
    welt.weiter(15)
    welt.fliegt("FRS999", 54.01, 8.0)
    _poll(p, welt)
    assert _fluege(pfad) == [] and welt.status_abrufe == 0


def test_statusabfrage_mit_anderem_rufzeichen_verwirft_die_zuordnung(pfad):
    welt = Welt()
    welt.status[CID] = _status(cs="EDDH_TWR")
    welt.fliegt("FRS61", 54.0, 8.0)
    p = _poller(pfad, welt)
    _poll(p, welt)
    welt.weiter(15)
    welt.fliegt("FRS61", 54.01, 8.0)
    _poll(p, welt)
    assert _fluege(pfad) == []


def test_fremdverkehr_kommt_aus_der_funkliste(pfad):
    welt = Welt()
    welt.fliegt("DLH123", 50.0, 8.0, hoehe_m=3048)
    p = _poller(pfad, welt)
    _poll(p, welt)
    welt.weiter(15)
    welt.fliegt("DLH123", 50.0 + 1 / 60, 8.0, hoehe_m=3048)
    _poll(p, welt)
    assert len(p.traffic_snapshot) == 1
    e = p.traffic_snapshot[0]
    assert e["cs"] == "DLH123" and e["alt"] == 10000 and 235 <= e["gs"] <= 245 and e["cid"] is None


def test_ohne_funkliste_faellt_der_zyklus_aus_und_niemand_wird_abgemeldet(pfad):
    welt = Welt()
    _frischer_feed(welt, _pilot_im_feed())
    p = _poller(pfad, welt)
    _poll(p, welt)
    welt.feed = Welt().feed
    welt.funk_kaputt = True
    _poll(p, welt)
    assert _fluege(pfad)[0]["logoff_time"] is None


def test_lotsen_ueber_den_ersatzweg_ohne_frequenz_und_namen_bleiben(pfad):
    c = get_connection(pfad)
    c.execute("INSERT INTO forum_callsign (callsign, cid, updated_at) VALUES ('FRS77', 1000004, '2026-01-01')")
    c.execute("INSERT INTO lotsen_name (cid, name, gesehen_am) VALUES (1000004, 'Lotte Lotse', '2026-10-01')")
    c.commit()
    c.close()
    welt = Welt()
    welt.lotsen = [{"id": 1000004, "callsign": "EDDH_TWR", "start": "2026-10-11T10:00:00Z"},
                   {"id": 1000004, "callsign": "EDDH_OBS", "start": "2026-10-11T10:00:00Z"},
                   {"id": 555, "callsign": "EDDF_TWR", "start": "2026-10-11T10:00:00Z"}]
    p = _poller(pfad, welt)
    _poll(p, welt)
    assert [(l["callsign"], l["frequenz"], l["name"]) for l in p.lotsen_online] == \
        [("EDDH_TWR", "–", "Lotte Lotse")]
    c = get_connection(pfad)
    try:
        assert c.execute("SELECT name FROM lotsen_name WHERE cid = 1000004").fetchone()["name"] == "Lotte Lotse"
    finally:
        c.close()


def test_ohne_bestaetigung_der_statusabfrage_wird_auch_ein_laufender_flug_nicht_fortgeschrieben(pfad):
    """Ein Rufzeichen kann sich jeder geben: Positionen aus der Funkliste zählen erst, wenn die
    Statusabfrage das Rufzeichen für diese Nummer bestätigt hat."""
    welt = Welt()
    _frischer_feed(welt, _pilot_im_feed())
    p = _poller(pfad, welt)
    _poll(p, welt)
    welt.feed = Welt().feed
    welt.fliegt("FRS61", 10.0, 10.0)          # jemand anderes unter demselben Rufzeichen
    welt.status[CID] = RuntimeError("api.vatsim.net antwortet nicht")
    for _ in range(ersatzweg.KARENZ_ZYKLEN + 1):
        welt.weiter(15)
        _poll(p, welt)
    assert all(z["latitude"] == 64.0 for z in _spur(pfad)), "keine fremde Position geschrieben"
    assert _fluege(pfad)[0]["logoff_time"] is not None


def test_neue_verbindung_wird_nicht_an_den_alten_offenen_flug_gehaengt(pfad):
    welt = Welt()
    _frischer_feed(welt, _pilot_im_feed(logon="2026-10-11T02:00:00.1234567Z"))
    p = _poller(pfad, welt)
    _poll(p, welt)
    welt.feed = Welt().feed
    welt.status[CID] = _status(start="2026-10-11T08:46:23Z")
    welt.fliegt("FRS61", 64.0, -12.0)
    _poll(p, welt)
    welt.weiter(15)
    welt.fliegt("FRS61", 64.01, -12.0)
    _poll(p, welt)
    fluege = _fluege(pfad)
    assert [f["logon_time"] for f in fluege] == ["2026-10-11T02:00:00.1234567Z", "2026-10-11T08:46:23Z"]
    assert fluege[0]["logoff_time"] is not None and fluege[1]["logoff_time"] is None


def test_probe_erzwingt_den_ersatzweg_bis_zum_gesetzten_zeitpunkt(pfad):
    from app.database import set_app_setting
    welt = Welt()
    _frischer_feed(welt, _pilot_im_feed())
    p = _poller(pfad, welt)
    c = get_connection(pfad)
    set_app_setting(c, "ersatzweg_erzwingen_bis", "2026-10-11T11:05:00Z")
    c.commit()
    c.close()
    _poll(p, welt)
    assert p.ersatzweg_aktiv and welt.funk_abrufe == 1
    p._now = lambda: JETZT + timedelta(minutes=6)
    _frischer_feed(welt, _pilot_im_feed())
    welt.feed["general"]["update_timestamp"] = "2026-10-11T11:05:55.0000000Z"
    _poll(p, welt)
    assert not p.ersatzweg_aktiv and welt.funk_abrufe == 1


def test_meldung_ohne_frequenz_nennt_keine():
    from app import lotsen
    l = {"callsign": "EDDH_TWR", "frequenz": "–", "station": "Hamburg Tower", "bis": ""}
    assert lotsen.payload_lotse_online("Lotte", l)["body"] == "EDDH_TWR"


def test_springt_das_rufzeichen_wird_die_bestaetigung_neu_geholt(pfad):
    welt = Welt()
    welt.status[CID] = _status()
    welt.fliegt("FRS61", 64.0, -12.0)
    p = _poller(pfad, welt)
    _poll(p, welt)
    welt.weiter(15)
    welt.fliegt("FRS61", 64.01, -12.0)
    _poll(p, welt)
    assert len(_spur(pfad)) == 1 and welt.status_abrufe == 1
    welt.status[CID] = None                    # der Friese ist weg ...
    welt.weiter(15)
    welt.fliegt("FRS61", 10.0, 10.0)          # ... und das Rufzeichen taucht woanders auf
    _poll(p, welt)
    assert welt.status_abrufe == 2, "nach einem Sprung sofort neu gefragt"
    assert all(z["latitude"] > 60 for z in _spur(pfad)), "die fremde Position wird nicht geschrieben"


def test_alte_bestaetigung_verfaellt_wenn_die_statusabfrage_dauerhaft_scheitert(pfad):
    welt = Welt()
    welt.status[CID] = _status()
    p = _poller(pfad, welt)
    asyncio.run(_pflegen(p, welt))
    assert p._ersatz_status["FRS61"]["art"] == "ok"
    welt.status[CID] = RuntimeError("weg")
    p._ersatz_status["FRS61"]["naechste"] = 0
    p._ersatz_status["FRS61"]["bestaetigt"] -= ersatzweg.BESTAETIGUNG_GILT_SEC + 1
    asyncio.run(_pflegen(p, welt))
    assert p._ersatz_status["FRS61"]["art"] == "fehler"


async def _pflegen(p, welt):
    async def status(_client, cid):
        antwort = welt.status.get(cid)
        if isinstance(antwort, Exception):
            raise antwort
        return antwort
    with patch("app.ersatzweg.hole_status", new=status):
        await p._ersatz_status_pflegen({"FRS61": CID})


def test_bestaetigung_bleibt_verworfen_wenn_der_zyklus_nach_dem_sprung_abbricht(pfad):
    welt = Welt()
    welt.status[CID] = _status()
    welt.fliegt("FRS61", 64.0, -12.0)
    p = _poller(pfad, welt)
    _poll(p, welt)
    welt.weiter(15)
    welt.fliegt("FRS61", 64.01, -12.0)
    _poll(p, welt)
    assert p._ersatz_status["FRS61"]["art"] == "ok"
    welt.weiter(15)
    welt.fliegt("FRS61", 10.0, 10.0)
    with patch("app.poller.cid_for_callsign_authoritative", side_effect=RuntimeError("database is locked")):
        _poll(p, welt)
    assert "FRS61" not in p._ersatz_status, "der Abbruch darf die alte Bestätigung nicht retten"


def test_nicht_aufgefrischte_bestaetigung_traegt_keine_position_mehr(pfad):
    welt = Welt()
    welt.status[CID] = _status()
    welt.fliegt("FRS61", 64.0, -12.0)
    p = _poller(pfad, welt)
    _poll(p, welt)
    welt.weiter(15)
    welt.fliegt("FRS61", 64.01, -12.0)
    _poll(p, welt)
    assert len(_spur(pfad)) == 1
    st = p._ersatz_status["FRS61"]
    st["bestaetigt"] -= ersatzweg.BESTAETIGUNG_GILT_SEC + 1
    st["naechste"] = time.monotonic() + 9999     # die Auffrischung kommt nicht dran
    welt.weiter(15)
    welt.fliegt("FRS61", 64.02, -12.0)
    _poll(p, welt)
    assert all(z["latitude"] != 64.02 for z in _spur(pfad))


def test_bestaetigung_fuer_eine_andere_nummer_zaehlt_nicht(pfad):
    welt = Welt()
    welt.status[CID] = _status()
    welt.fliegt("FRS61", 64.0, -12.0)
    p = _poller(pfad, welt)
    _poll(p, welt)
    st = p._ersatz_status["FRS61"]
    st["cid"] = 1000099                       # die Zuordnung hat inzwischen gewechselt ...
    st["naechste"] = time.monotonic() + 9999
    p._ersatz_status_pflegen = _nichts        # ... und die Auffrischung kam nicht dran
    welt.weiter(15)
    welt.fliegt("FRS61", 64.01, -12.0)
    _poll(p, welt)
    assert _fluege(pfad) == []


async def _nichts(_zuordnung):
    return None


def test_laufende_fluege_werden_vor_unbekannten_aufgefrischt(pfad):
    c = get_connection(pfad)
    for i in range(20):
        c.execute("INSERT INTO forum_callsign (callsign, cid, updated_at) VALUES (?, ?, '2026-01-01')",
                  (f"FRS9{i:02d}", 2000000 + i))
    c.commit()
    c.close()
    welt = Welt()
    p = _poller(pfad, welt)
    p._active_flights[CID] = {"id": 1, "dep": "", "arr": ""}
    gefragt = []

    async def status(_client, cid):
        gefragt.append(cid)
        return None

    zuordnung = {f"FRS9{i:02d}": 2000000 + i for i in range(20)}
    zuordnung["FRS61"] = CID
    with patch("app.ersatzweg.hole_status", new=status):
        asyncio.run(p._ersatz_status_pflegen(zuordnung))
    assert CID in gefragt and len(gefragt) == 10
