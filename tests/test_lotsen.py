"""Friesen als Lotsen (#61): Erkennung, Buchungen, Endzeit und Meldungstexte.

Alle Namen, Nummern und Schichten hier sind erfunden."""
from datetime import datetime, timezone

import pytest

from app import lotsen

UTC = timezone.utc
CIDS = {1000001, 1000002}


def _lotse(**kw):
    basis = {"cid": 1000001, "name": "Erika Muster", "callsign": "EDDP_GND", "frequency": "121.805",
             "facility": 3, "text_atis": ["Leipzig Ground"], "logon_time": "2026-10-09T13:33:10.1Z"}
    basis.update(kw)
    return basis


def _buchung(**kw):
    basis = {"id": 1, "cid": 1000001, "type": "booking", "callsign": "EDDS_TWR",
             "start": "2026-10-11 18:00:00", "end": "2026-10-11 20:00:00"}
    basis.update(kw)
    return basis


# --- Station -------------------------------------------------------------------------------

@pytest.mark.parametrize("callsign, icao, art", [
    ("EDDP_GND", "EDDP", "Ground"), ("EDDS_TWR", "EDDS", "Tower"), ("EDDH_DEL", "EDDH", "Delivery"),
    ("EDDN_FRK_APP", "EDDN", "Approach"), ("EDDF_C_GND", "EDDF", "Ground"), ("eddh_e_gnd", "EDDH", "Ground"),
    ("EDDM_DEP", "EDDM", "Departure"),
])
def test_station_an_einem_flugplatz(callsign, icao, art):
    s = lotsen.station(callsign)
    assert s["icao"] == icao and s["art"] == art
    assert isinstance(s["lat"], float) and isinstance(s["lon"], float)


@pytest.mark.parametrize("callsign", [
    "EDWW_EMS_CTR", "EDGG_CTR", "EURM_FSS", "EDDF_ATIS", "MM_OBS", "EDDP", "", "XXXX_TWR", "EDWW_TWR",
])
def test_zentralen_beobachter_und_unbekanntes_sind_keine_station(callsign):
    """Nutzer 09.10.2026: Kontrollzentralen bleiben ganz weg. EDWW ist eine Zentrale, kein Platz."""
    assert lotsen.station(callsign) is None


def test_stationsname_ist_ort_plus_art():
    assert lotsen.station("EDDP_GND")["name"] == "Leipzig Ground"
    assert lotsen.station("EDDS_TWR")["name"] == "Stuttgart Tower"


# --- Wer lotst gerade ----------------------------------------------------------------------

def test_nur_bekannte_nummern_an_flugplatz_stationen():
    feed = {"controllers": [
        _lotse(),
        _lotse(cid=7777777, callsign="EDDH_TWR"),                    # kein Friese
        _lotse(cid=1000002, callsign="EDWW_EMS_CTR", facility=6),    # Zentrale
        _lotse(cid=1000002, callsign="XY_OBS", facility=0, frequency="199.998"),   # Beobachter
    ]}
    erg = lotsen.friesen_lotsen(feed, CIDS)
    assert [l["callsign"] for l in erg] == ["EDDP_GND"]
    l = erg[0]
    assert l["cid"] == 1000001 and l["frequenz"] == "121.805" and l["station"] == "Leipzig Ground"
    assert l["icao"] == "EDDP" and l["online_seit"] == "2026-10-09T13:33:10.1Z"
    assert "name" not in l, "den Namen liefert die eigene Pilotenliste, nicht der Feed"


def test_feed_ohne_lotsen_oder_mit_muell_bricht_nicht():
    assert lotsen.friesen_lotsen({}, CIDS) == []
    assert lotsen.friesen_lotsen({"controllers": [None, "x", {"cid": 1000001}]}, CIDS) == []


# --- Buchungen -----------------------------------------------------------------------------

JETZT = datetime(2026, 10, 9, 15, 0, tzinfo=UTC)


def test_buchungen_der_naechsten_sieben_tage_nach_beginn_sortiert():
    roh = [
        _buchung(id=3, start="2026-10-16 14:59:00", end="2026-10-16 16:00:00"),   # knapp drin
        _buchung(id=1),
        _buchung(id=4, start="2026-10-16 15:01:00", end="2026-10-16 17:00:00"),   # zu spaet
        _buchung(id=5, cid=7777777),                                              # kein Friese
        _buchung(id=6, callsign="EDWW_EMS_CTR"),                                  # Zentrale
        _buchung(id=7, start="2026-10-09 12:00:00", end="2026-10-09 14:00:00"),   # schon vorbei
        _buchung(id=2, start="2026-10-09 14:00:00", end="2026-10-09 16:00:00", cid=1000002, callsign="EDDH_DEL"),
    ]
    erg = lotsen.buchungen_filtern(roh, CIDS, JETZT)
    assert [b["id"] for b in erg] == [2, 1, 3]
    b = erg[1]
    assert b == {"id": 1, "cid": 1000001, "callsign": "EDDS_TWR", "station": "Stuttgart Tower",
                 "icao": "EDDS", "lat": b["lat"], "lon": b["lon"],
                 "von": "2026-10-11T18:00:00Z", "bis": "2026-10-11T20:00:00Z"}


def test_kaputte_buchungen_fallen_weg():
    roh = [None, {}, _buchung(start="quatsch"), _buchung(end=None), _buchung(id=None)]
    assert lotsen.buchungen_filtern(roh, CIDS, JETZT) == []


# --- Endzeit -------------------------------------------------------------------------------

@pytest.mark.parametrize("text, erwartet", [
    (["Expected Logoff Time 2000z"], "20:00"),
    (["Leipzig Ground", "est OFF AT 1600Z"], "16:00"),
    (["online until 21:30z"], "21:30"),
    (["Bis 1900z online"], "19:00"),
    (["Leipzig Ground", "Briefing at vats.im/eddp"], None),
    (["ATIS M 1430Z RWY27"], None),
    (["until 2575z"], None),
    ([], None), (None, None),
])
def test_endzeit_aus_dem_infotext(text, erwartet):
    assert lotsen.endzeit_aus_infotext(text) == erwartet


def test_endzeit_infotext_geht_vor_buchung():
    b = [{"cid": 1000001, "callsign": "EDDP_GND", "von": "2026-10-09T13:00:00Z", "bis": "2026-10-09T17:00:00Z"}]
    assert lotsen.endzeit({"cid": 1000001, "callsign": "EDDP_GND", "infotext": ["logoff 1830z"]}, b, JETZT) == "18:30"
    assert lotsen.endzeit({"cid": 1000001, "callsign": "EDDP_GND", "infotext": []}, b, JETZT) == "17:00"


def test_endzeit_nur_aus_einer_laufenden_buchung_desselben_lotsen():
    spaeter = [{"cid": 1000001, "callsign": "EDDP_GND", "von": "2026-10-09T18:00:00Z", "bis": "2026-10-09T20:00:00Z"}]
    fremd = [{"cid": 1000002, "callsign": "EDDP_GND", "von": "2026-10-09T13:00:00Z", "bis": "2026-10-09T17:00:00Z"}]
    l = {"cid": 1000001, "callsign": "EDDP_GND", "infotext": []}
    assert lotsen.endzeit(l, spaeter, JETZT) is None
    assert lotsen.endzeit(l, fremd, JETZT) is None
    assert lotsen.endzeit(l, [], JETZT) is None


# --- Meldungstexte (freigegeben 09.10.2026) ------------------------------------------------

def test_meldung_lotse_geht_online():
    l = {"callsign": "EDDP_GND", "station": "Leipzig Ground", "frequenz": "121.805", "bis": "20:00"}
    assert lotsen.payload_lotse_online("Erika", l) == {
        "title": "Erika lotst jetzt Leipzig Ground 🎧",
        "body": "EDDP_GND auf 121.805, bis ca. 20:00 UTC", "url": "/"}
    l["bis"] = None
    assert lotsen.payload_lotse_online("Erika", l)["body"] == "EDDP_GND auf 121.805"


def test_meldung_am_morgen_fasst_den_tag_zusammen():
    eintraege = [("Erika", {"station": "Stuttgart Tower", "von": "2026-10-11T18:00:00Z", "bis": "2026-10-11T20:00:00Z"}),
                 ("Max", {"station": "Hamburg Delivery", "von": "2026-10-11T17:00:00Z", "bis": "2026-10-11T20:00:00Z"})]
    assert lotsen.payload_lotsen_heute(eintraege) == {
        "title": "Heute lotsen 🎧",
        "body": "Erika, Stuttgart Tower 18:00–20:00 UTC · Max, Hamburg Delivery 17:00–20:00 UTC",
        "url": "/"}


def test_meldung_bei_spaeter_buchung():
    b = {"callsign": "EDDH_DEL", "station": "Hamburg Delivery", "von": "2026-10-11T17:00:00Z", "bis": "2026-10-11T20:00:00Z"}
    assert lotsen.payload_lotse_spaet("Max", b) == {
        "title": "Max lotst heute Hamburg Delivery 🎧",
        "body": "EDDH_DEL, 17:00–20:00 UTC", "url": "/"}


# --- 7 Uhr deutscher Zeit, Sommer- und Winterzeit ------------------------------------------

@pytest.mark.parametrize("utc, tag, nach_sieben", [
    (datetime(2026, 10, 9, 4, 59, tzinfo=UTC), "2026-10-09", False),    # Sommerzeit: 06:59
    (datetime(2026, 10, 9, 5, 0, tzinfo=UTC), "2026-10-09", True),      # Sommerzeit: 07:00
    (datetime(2026, 11, 9, 5, 30, tzinfo=UTC), "2026-11-09", False),    # Winterzeit: 06:30
    (datetime(2026, 11, 9, 6, 0, tzinfo=UTC), "2026-11-09", True),      # Winterzeit: 07:00
    (datetime(2026, 10, 9, 22, 30, tzinfo=UTC), "2026-10-10", False),   # 00:30 am Folgetag
])
def test_ortstag_und_sieben_uhr(utc, tag, nach_sieben):
    assert lotsen.ortstag(utc) == tag
    assert lotsen.nach_sieben(utc) is nach_sieben


def test_heute_ist_der_deutsche_kalendertag_des_schichtbeginns():
    spaet = {"von": "2026-10-09T22:30:00Z"}      # 00:30 am 10.10. deutscher Zeit
    assert lotsen.beginnt_am(spaet, "2026-10-10") and not lotsen.beginnt_am(spaet, "2026-10-09")


# --- Was wann gemeldet wird ----------------------------------------------------------------

B_HEUTE = {"id": 11, "cid": 1000001, "von": "2026-10-09T18:00:00Z", "bis": "2026-10-09T20:00:00Z"}
B_MORGEN = {"id": 12, "cid": 1000001, "von": "2026-10-10T18:00:00Z", "bis": "2026-10-10T20:00:00Z"}
B_VORBEI = {"id": 13, "cid": 1000002, "von": "2026-10-09T06:00:00Z", "bis": "2026-10-09T08:00:00Z"}
ALLE = [B_HEUTE, B_MORGEN, B_VORBEI]


def test_erster_lauf_setzt_nur_den_stand():
    """Sonst kaeme am Tag des Einspielens eine Sammelmeldung zur falschen Zeit."""
    plan = lotsen.melde_plan(ALLE, datetime(2026, 10, 9, 15, 0, tzinfo=UTC), morgen_tag=None, gemeldet=set())
    assert plan == {"morgen": [], "spaet": [], "morgen_tag": "2026-10-09", "merken": [11]}


def test_vor_sieben_passiert_nichts():
    plan = lotsen.melde_plan(ALLE, datetime(2026, 10, 9, 4, 0, tzinfo=UTC), morgen_tag="2026-10-08", gemeldet=set())
    assert plan == {"morgen": [], "spaet": [], "morgen_tag": "2026-10-08", "merken": []}


def test_ab_sieben_kommt_die_sammelmeldung_einmal():
    jetzt = datetime(2026, 10, 9, 5, 5, tzinfo=UTC)
    plan = lotsen.melde_plan(ALLE + [dict(B_VORBEI, id=14, von="2026-10-09T03:00:00Z", bis="2026-10-09T04:00:00Z")],
                             jetzt, morgen_tag="2026-10-08", gemeldet=set())
    assert [b["id"] for b in plan["morgen"]] == [13, 11], "noch laufende und kommende von heute, nach Beginn"
    assert plan["spaet"] == [] and plan["morgen_tag"] == "2026-10-09" and plan["merken"] == [13, 11]


def test_spaete_buchung_fuer_heute_kommt_sofort_und_nur_einmal():
    jetzt = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)
    plan = lotsen.melde_plan(ALLE, jetzt, morgen_tag="2026-10-09", gemeldet={13})
    assert plan["morgen"] == [] and [b["id"] for b in plan["spaet"]] == [11] and plan["merken"] == [11]
    plan = lotsen.melde_plan(ALLE, jetzt, morgen_tag="2026-10-09", gemeldet={11, 13})
    assert plan["spaet"] == [] and plan["merken"] == []


def test_ohne_buchung_heute_keine_sammelmeldung_aber_der_tag_gilt_als_erledigt():
    plan = lotsen.melde_plan([B_MORGEN], datetime(2026, 10, 9, 6, 0, tzinfo=UTC), morgen_tag="2026-10-08", gemeldet=set())
    assert plan == {"morgen": [], "spaet": [], "morgen_tag": "2026-10-09", "merken": []}


# --- Erster echter Lauf, 09.10.2026: Meldung mit Platzhalter-Frequenz und ohne Ende ---------

def test_wer_noch_keine_frequenz_gesetzt_hat_lotst_noch_nicht():
    """Direkt nach dem Anmelden steht im Feed 199.998, bis der Lotse seine Frequenz schaltet.
    Die erste echte Meldung nannte genau diese Zahl."""
    feed = {"controllers": [_lotse(frequency="199.998")]}
    assert lotsen.friesen_lotsen(feed, CIDS) == []
    feed = {"controllers": [_lotse(frequency="121.805")]}
    assert len(lotsen.friesen_lotsen(feed, CIDS)) == 1


def test_endzeit_gilt_auch_wenn_er_kurz_vor_schichtbeginn_anfaengt():
    """Der Lotse meldete sich 42 Sekunden vor Beginn seiner gebuchten Schicht an; die Meldung
    kam deshalb ohne "bis ca."."""
    b = [{"cid": 1000001, "callsign": "EDDP_GND", "von": "2026-10-09T17:30:00Z", "bis": "2026-10-09T20:00:00Z"}]
    l = {"cid": 1000001, "callsign": "EDDP_GND", "infotext": []}
    assert lotsen.endzeit(l, b, datetime(2026, 10, 9, 17, 29, 18, tzinfo=UTC)) == "20:00"
    assert lotsen.endzeit(l, b, datetime(2026, 10, 9, 17, 0, 0, tzinfo=UTC)) == "20:00"
    assert lotsen.endzeit(l, b, datetime(2026, 10, 9, 16, 59, 0, tzinfo=UTC)) is None, "mehr als eine halbe Stunde vorher nicht"
    assert lotsen.endzeit(l, b, datetime(2026, 10, 9, 20, 0, 0, tzinfo=UTC)) is None


# --- Name in den Meldungen ohne Heimatflugplatz (Nutzer 09.10.2026) ------------------------

@pytest.mark.parametrize("roh, kurz", [
    ("Erika EDWS", "Erika"), ("Erika Muster EDDB", "Erika Muster"), ("Erika Muster", "Erika Muster"),
    ("HANS EDDH", "HANS"), ("EDDH", "EDDH"), ("FRS77", "FRS77"), ("Erika  EDWS ", "Erika"), ("", ""),
    ("Max D", "Max D"), ("Erika edws", "Erika edws"),
])
def test_name_ohne_heimatflugplatz(roh, kurz):
    assert lotsen.meldename(roh) == kurz


def test_alle_drei_meldungen_nennen_den_namen_ohne_flugplatz():
    l = {"callsign": "EDDW_GND", "station": "Bremen Ground", "frequenz": "121.755", "bis": "20:00"}
    b = {"callsign": "EDDW_GND", "station": "Bremen Ground", "von": "2026-10-09T17:30:00Z", "bis": "2026-10-09T20:00:00Z"}
    assert lotsen.payload_lotse_online("Erika EDWS", l)["title"] == "Erika lotst jetzt Bremen Ground 🎧"
    assert lotsen.payload_lotse_spaet("Erika EDWS", b)["title"] == "Erika lotst heute Bremen Ground 🎧"
    assert lotsen.payload_lotsen_heute([("Erika EDWS", b)])["body"] == "Erika, Bremen Ground 17:30–20:00 UTC"
