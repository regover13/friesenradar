"""Friesen als Lotsen (#61): Datenbank, Poller und Schnittstelle. Alle Namen sind erfunden."""
import asyncio
from datetime import datetime, timezone

import pytest

from app import database as db
from app.database import get_connection, init_db
from app.poller import VatsimPoller

UTC = timezone.utc


@pytest.fixture
def pfad(tmp_path):
    p = str(tmp_path / "t.db")
    init_db(p)
    c = get_connection(p)
    c.execute("INSERT INTO pilots (cid, name, added_at, active) VALUES (1000001, 'Erika Muster', '2026-01-01', 1)")
    c.execute("INSERT INTO pilots (cid, name, added_at, active) VALUES (1000002, 'Max Beispiel', '2026-01-01', 1)")
    c.execute("INSERT INTO pilots (cid, name, added_at, active) VALUES (1000003, 'Aus Geschaltet', '2026-01-01', 0)")
    c.execute("INSERT INTO forum_callsign (callsign, cid, updated_at) VALUES ('FRS77', 1000004, '2026-01-01')")
    c.commit()
    c.close()
    return p


def _poller(pfad):
    p = VatsimPoller(db_path=pfad, callsign_prefix="FRS", poll_interval=60)
    p.gesendet = []       # (dienst, cid, payload) aus dem Kniebrett-Kanal
    p.push = []           # (art, ...) statt echtem Web-Push
    p.broadcast_notify = lambda dienst, cid, payload, nur_cid=None: p.gesendet.append((dienst, cid, payload))

    async def _push_online(lotse, payload):
        p.push.append(("online", lotse["cid"], payload))

    async def _push_buchung(buchung, payload):
        p.push.append(("spaet", buchung["cid"], payload))

    async def _push_morgen(buchungen):
        p.push.append(("morgen", [b["id"] for b in buchungen]))

    p._lotse_push_online = _push_online
    p._lotse_push_buchung = _push_buchung
    p._lotsen_push_morgen = _push_morgen
    return p


def _feed(*lotsen):
    return {"controllers": [
        {"cid": cid, "name": "egal", "callsign": cs, "frequency": "121.805", "facility": 3,
         "text_atis": [], "logon_time": "2026-10-09T13:33:10Z"} for cid, cs in lotsen]}


# --- Datenbank -----------------------------------------------------------------------------

def test_bekannte_nummern_mit_namen(pfad):
    c = get_connection(pfad)
    try:
        bekannt = db.lotsen_bekannte(c)
    finally:
        c.close()
    assert bekannt == {1000001: "Erika Muster", 1000002: "Max Beispiel", 1000004: "FRS77"}, \
        "abgeschaltete Piloten fehlen; wer nur aus dem Forum bekannt ist, heisst wie sein Rufzeichen"


def test_gemeldete_buchungen_werden_gemerkt(pfad):
    c = get_connection(pfad)
    try:
        assert db.lotsen_gemeldete(c) == set()
        db.lotsen_merken(c, [11, 12], "2026-10-09T05:00:00Z")
        db.lotsen_merken(c, [12, 13], "2026-10-09T06:00:00Z")
        c.commit()
        assert db.lotsen_gemeldete(c) == {11, 12, 13}
    finally:
        c.close()


# --- Wer lotst gerade ----------------------------------------------------------------------

def test_erster_durchlauf_setzt_nur_den_stand(pfad):
    p = _poller(pfad)
    p._lotsen_aus_feed(_feed((1000001, "EDDP_GND")), set())
    assert [l["callsign"] for l in p.lotsen_online] == ["EDDP_GND"]
    assert p.lotsen_online[0]["name"] == "Erika Muster"
    assert "infotext" not in p.lotsen_online[0]
    assert p.gesendet == [], "nach einem Neustart keine Meldung fuer den, der schon lotste"


def test_wer_neu_lotst_wird_einmal_gemeldet(pfad):
    p = _poller(pfad)
    p._lotsen_aus_feed(_feed(), set())
    p._lotsen_aus_feed(_feed((1000001, "EDDP_GND")), set())
    assert len(p.gesendet) == 1
    dienst, cid, payload = p.gesendet[0]
    assert dienst == "online" and cid == 1000001
    assert payload["title"] == "Erika Muster lotst jetzt Leipzig Ground 🎧"
    assert payload["body"] == "EDDP_GND auf 121.805"
    p._lotsen_aus_feed(_feed((1000001, "EDDP_GND")), set())
    assert len(p.gesendet) == 1


def test_kurzer_abriss_meldet_nicht_noch_einmal(pfad):
    p = _poller(pfad)
    p._lotsen_aus_feed(_feed(), set())
    p._lotsen_aus_feed(_feed((1000001, "EDDP_GND")), set())
    p._lotsen_aus_feed(_feed(), set())
    p._lotsen_aus_feed(_feed((1000001, "EDDP_GND")), set())
    assert len(p.gesendet) == 1


def test_abgeschaltete_und_ausgenommene_tauchen_nicht_auf(pfad):
    p = _poller(pfad)
    p._lotsen_aus_feed(_feed(), set())
    p._lotsen_aus_feed(_feed((1000003, "EDDH_TWR"), (1000002, "EDDS_TWR")), {1000002})
    assert p.lotsen_online == [] and p.gesendet == []


def test_endzeit_kommt_aus_der_laufenden_buchung(pfad):
    p = _poller(pfad)
    p._now = lambda: datetime(2026, 10, 9, 15, 0, tzinfo=UTC)
    p.lotsen_buchungen = [{"id": 5, "cid": 1000001, "callsign": "EDDP_GND", "station": "Leipzig Ground",
                           "von": "2026-10-09T13:00:00Z", "bis": "2026-10-09T17:00:00Z"}]
    p._lotsen_aus_feed(_feed(), set())
    p._lotsen_aus_feed(_feed((1000001, "EDDP_GND")), set())
    assert p.lotsen_online[0]["bis"] == "17:00"
    assert p.gesendet[0][2]["body"] == "EDDP_GND auf 121.805, bis ca. 17:00 UTC"


def test_ein_fehler_bei_den_lotsen_reisst_den_poll_nicht_mit(pfad):
    p = _poller(pfad)
    p._lotsen_aus_feed({"controllers": "kaputt"}, set())
    assert p.lotsen_online == []


# --- Gebuchte Schichten melden -------------------------------------------------------------

B_HEUTE = {"id": 11, "cid": 1000001, "name": "Erika Muster", "callsign": "EDDS_TWR", "station": "Stuttgart Tower",
           "von": "2026-10-09T18:00:00Z", "bis": "2026-10-09T20:00:00Z"}


def _melden(p, jetzt):
    asyncio.run(p._lotsen_melden(jetzt))


def test_ohne_ersten_abruf_wird_nichts_gemeldet_und_nichts_abgehakt(pfad):
    """Sonst gaelte der Tag nach einem Neustart um 7 Uhr als erledigt, bevor die Liste da ist."""
    p = _poller(pfad)
    _melden(p, datetime(2026, 10, 9, 5, 5, tzinfo=UTC))
    c = get_connection(pfad)
    try:
        assert db.get_app_setting(c, "lotsen_morgen_tag") is None
    finally:
        c.close()


def test_morgens_eine_sammelmeldung_dann_ruhe(pfad):
    p = _poller(pfad)
    p.lotsen_buchungen = [B_HEUTE]
    p._lotsen_buchungen_da = True
    _melden(p, datetime(2026, 10, 8, 12, 0, tzinfo=UTC))      # erster Lauf: nur Stand
    assert p.push == []
    _melden(p, datetime(2026, 10, 9, 4, 0, tzinfo=UTC))       # vor sieben
    assert p.push == []
    _melden(p, datetime(2026, 10, 9, 5, 1, tzinfo=UTC))       # 07:01 Sommerzeit
    assert p.push == [("morgen", [11])]
    assert [g[0] for g in p.gesendet] == ["prefile"], "im Kniebrett je Schicht eine Meldung"
    _melden(p, datetime(2026, 10, 9, 5, 2, tzinfo=UTC))
    assert p.push == [("morgen", [11])]


def test_spaete_buchung_kommt_sofort(pfad):
    p = _poller(pfad)
    p._lotsen_buchungen_da = True
    _melden(p, datetime(2026, 10, 8, 12, 0, tzinfo=UTC))
    _melden(p, datetime(2026, 10, 9, 5, 1, tzinfo=UTC))       # Sammelmeldung: nichts gebucht
    assert p.push == []
    p.lotsen_buchungen = [B_HEUTE]
    _melden(p, datetime(2026, 10, 9, 10, 0, tzinfo=UTC))
    assert len(p.push) == 1 and p.push[0][0] == "spaet" and p.push[0][1] == 1000001
    assert p.push[0][2]["title"] == "Erika Muster lotst heute Stuttgart Tower 🎧"
    assert p.gesendet[0][0] == "prefile" and p.gesendet[0][1] == 1000001
    _melden(p, datetime(2026, 10, 9, 10, 1, tzinfo=UTC))
    assert len(p.push) == 1


# --- Buchungsliste holen -------------------------------------------------------------------

class _Antwort:
    def __init__(self, daten):
        self._daten = daten

    def raise_for_status(self):
        pass

    def json(self):
        return self._daten


def test_abruf_fuellt_die_liste_mit_namen(pfad):
    p = _poller(pfad)
    p._now = lambda: datetime(2026, 10, 9, 15, 0, tzinfo=UTC)

    class _Client:
        async def get(self, url, **kw):
            assert "atc-bookings.vatsim.net" in url
            assert "FriesenRadar" in kw["headers"]["User-Agent"]
            return _Antwort([
                {"id": 1, "cid": 1000001, "callsign": "EDDS_TWR", "start": "2026-10-11 18:00:00", "end": "2026-10-11 20:00:00"},
                {"id": 2, "cid": 9999999, "callsign": "EDDH_TWR", "start": "2026-10-11 18:00:00", "end": "2026-10-11 20:00:00"},
            ])

    p._http_client = _Client()
    asyncio.run(p._lotsen_buchungen_holen())
    assert [(b["id"], b["name"]) for b in p.lotsen_buchungen] == [(1, "Erika Muster")]
    assert p._lotsen_buchungen_da is True


def test_gescheiterter_abruf_behaelt_die_alte_liste(pfad):
    p = _poller(pfad)
    p.lotsen_buchungen = [B_HEUTE]

    class _Client:
        async def get(self, url, **kw):
            raise RuntimeError("Netz weg")

    p._http_client = _Client()
    asyncio.run(p._lotsen_buchungen_holen())
    assert p.lotsen_buchungen == [B_HEUTE]


def test_die_jobs_sind_angemeldet():
    import inspect
    quelle = inspect.getsource(VatsimPoller._register_jobs)
    assert "self._lotsen_buchungen_holen" in quelle and "self._lotsen_melden" in quelle


def test_der_poll_liest_die_lotsen_aus_dem_feed():
    import inspect
    assert "self._lotsen_aus_feed(vatsim_data, excluded_cids)" in inspect.getsource(VatsimPoller._poll_once)


# --- Schnittstelle -------------------------------------------------------------------------

class _App:
    class state:
        poller = None


class _Anfrage:
    app = _App


def test_schnittstelle_liefert_online_und_geplant(pfad, monkeypatch):
    import app.main as main
    p = _poller(pfad)
    p.lotsen_online = [{"cid": 1000001, "name": "Erika Muster", "callsign": "EDDP_GND", "station": "Leipzig Ground",
                        "frequenz": "121.805", "icao": "EDDP", "lat": 51.4, "lon": 12.2,
                        "online_seit": "2026-10-09T13:33:10Z", "bis": "17:00"}]
    laeuft = {"id": 5, "cid": 1000001, "name": "Erika Muster", "callsign": "EDDP_GND", "station": "Leipzig Ground",
              "icao": "EDDP", "lat": 51.4, "lon": 12.2, "von": "2026-10-09T13:00:00Z", "bis": "2026-10-09T17:00:00Z"}
    vorbei = dict(B_HEUTE, id=6, von="2026-10-09T10:00:00Z", bis="2026-10-09T12:00:00Z")
    p.lotsen_buchungen = [vorbei, laeuft, B_HEUTE]
    _App.state.poller = p
    monkeypatch.setattr(main, "_lotsen_jetzt", lambda: datetime(2026, 10, 9, 15, 0, tzinfo=UTC))
    erg = asyncio.run(main.get_lotsen(_Anfrage()))
    assert [l["callsign"] for l in erg["online"]] == ["EDDP_GND"]
    assert [b["id"] for b in erg["geplant"]] == [11], \
        "wer schon an der gebuchten Station lotst, steht nur noch in der Live-Liste; Vergangenes faellt weg"


def test_schnittstelle_steht_hinter_der_anmeldung():
    import app.main as main
    assert not "/api/lotsen".startswith(main._GATE_ALLOW_PREFIXES)
