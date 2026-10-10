# -*- coding: utf-8 -*-
"""Fundstellen der Deichkontrolle: Ablage, Fund, Objekte im Simulator (10.10.2026).

Spec: docs/superpowers/specs/2026-10-10-deichkontrolle-design.md, Abschnitt 15.
"""
from __future__ import annotations

import json
import math

import pytest

import app.database as db
from app.database import (
    bruegge_soll_alle, bruegge_soll_setzen, compute_strecke_stand, create_strecken_event,
    delete_strecken_event, get_connection, get_strecken_event, init_db, strecke_fortschreiben,
    strecke_fundstellen, strecke_fundstellen_setzen, strecke_objekte_abgleichen,
    strecke_stand_verwerfen, update_strecken_event,
)

LAT, LON = 53.72, 7.25
KM_LON = 111.32 * math.cos(math.radians(LAT))
START, ENDE = "2026-10-10T18:00:00Z", "2026-10-10T21:00:00Z"
MITTEN = "2026-10-10T19:00:00Z"
ART = "seehund_kuh"


def _ost(km):
    return LON + km / KM_LON


def _nord(km):
    return LAT + km / 111.32


GERADE = [[LAT, LON], [LAT, _ost(10.0)]]


def _zeit(sekunden):
    return "2026-10-10T18:%02d:%02dZ" % divmod(sekunden, 60)


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    init_db(p)
    c = get_connection(p)
    monkeypatch.setattr(db, "_spur_sektoren", (0.0, []))
    monkeypatch.setattr(db, "_strecken_boxen_stand", (0.0, []))
    yield c
    c.close()


def _fs(km=3.0, nord_km=0.0, **extra):
    # Hoechstmenge mal Hoechstabstand darf hoechstens 200 sein -- die Abstaende richten sich
    # deshalb nach der Menge, wenn der Test sie nicht selbst vorgibt.
    menge = int(extra.get("menge_max", 9)) if isinstance(extra.get("menge_max", 9), int) else 9
    weit = max(min(20, 200 // max(menge, 1)), 1)
    f = {"lat": _nord(nord_km), "lon": _ost(km), "art": ART,"menge_min": 5, "menge_max": 9,
         "abstand_min_m": min(10, weit), "abstand_max_m": weit, "startwert": f"s{km}", "grund_ft": 0.0, }
    f.update(extra)
    return f


def _ev(conn, fundstellen=(), **extra):
    eid = create_strecken_event(conn, name="Probe", dtstart=START, dtend=ENDE, punkte=GERADE,
                                **extra)
    update_strecken_event(conn, eid, grund_json=json.dumps([0.0] * 10), grund_geholt_am=START)
    strecke_fundstellen_setzen(conn, eid, list(fundstellen))
    conn.commit()
    return eid


def _flug(conn, cid, von_km, bis_km, *, ab_s=10, alt=800.0, gs=100.0, nord_km=0.0,
          quelle=None):
    n = int(round((bis_km - von_km) / 0.05))
    for i in range(n + 1):
        conn.execute(
            "INSERT OR REPLACE INTO bruegge_spur (cid, ts, lat, lon, alt_msl_ft, gs_kt, quelle) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cid, _zeit(ab_s + i), _nord(nord_km), _ost(von_km + i * 0.05), alt, gs, quelle))
    conn.commit()
    return ab_s + n


# --- Ablage --------------------------------------------------------------------------------

def test_eine_fundstelle_wird_mit_gewuerfelter_lage_abgelegt(conn):
    eid = _ev(conn, [_fs()])
    (f,) = strecke_fundstellen(conn, eid)
    assert f["nr"] == 1 and f["art"] == ART
    assert 5 <= f["menge"] <= 9 and len(f["objekte"]) == f["menge"]
    assert f["objekte"][0]["lat"] == pytest.approx(LAT) and "kurs" in f["objekte"][0]
    assert f["gefunden_am"] is None and f["grund_ft"] == 0.0


def test_ohne_startwert_wird_einer_vergeben(conn):
    roh = _fs()
    del roh["startwert"]
    eid = _ev(conn, [roh])
    assert strecke_fundstellen(conn, eid)[0]["startwert"]


def test_eine_unveraenderte_fundstelle_behaelt_zeile_und_fundstand(conn):
    eid = _ev(conn, [_fs(3.0), _fs(6.0)])
    eins, zwei = strecke_fundstellen(conn, eid)
    conn.execute("UPDATE strecken_fundstellen SET gefunden_am = ?, gefunden_von = 7 WHERE id = ?",
                 (MITTEN, eins["id"]))
    # Das Formular schickt alle wieder, die zweite an einem anderen Ort, eine dritte dazu --
    # und ohne die Gelaendehoehe, die es nicht kennt.
    ohne = {k: v for k, v in _fs(3.0).items() if k != "grund_ft"}
    erg = strecke_fundstellen_setzen(conn, eid, [ohne, _fs(6.5), _fs(8.0)])
    assert (erg["geblieben"], erg["neu"], erg["weg"]) == (1, 2, 1)
    nach = strecke_fundstellen(conn, eid)
    assert nach[0]["id"] == eins["id"] and nach[0]["gefunden_von"] == 7
    assert nach[0]["grund_ft"] == 0.0, "die Hoehe bleibt, wenn keine neue mitkommt"
    assert nach[0]["objekte"] == eins["objekte"]
    assert zwei["id"] not in {f["id"] for f in nach}
    assert erg["objekte"] == sum(f["menge"] for f in nach)


def test_ein_neuer_startwert_ist_eine_neue_fundstelle(conn):
    eid = _ev(conn, [_fs(3.0)])
    (vor,) = strecke_fundstellen(conn, eid)
    conn.execute("UPDATE strecken_fundstellen SET gefunden_am = ?, gefunden_von = 7", (MITTEN,))
    strecke_fundstellen_setzen(conn, eid, [_fs(3.0, startwert="anders")])
    (nach,) = strecke_fundstellen(conn, eid)
    assert nach["id"] != vor["id"] and nach["gefunden_am"] is None
    assert nach["objekte"] != vor["objekte"]


def test_zwei_gleiche_eintraege_ergeben_zwei_fundstellen(conn):
    eid = _ev(conn, [_fs(3.0), _fs(3.0)])
    assert len(strecke_fundstellen(conn, eid)) == 2
    conn.execute("UPDATE strecken_fundstellen SET gefunden_am = ?, gefunden_von = 7", (MITTEN,))
    erg = strecke_fundstellen_setzen(conn, eid, [_fs(3.0), _fs(3.0)])
    assert (erg["geblieben"], erg["neu"], erg["weg"]) == (2, 0, 0)
    assert all(f["gefunden_von"] == 7 for f in strecke_fundstellen(conn, eid)), \
        "keine der beiden verliert beim Speichern ihren Fund"


def test_der_startwert_null_ist_ein_startwert(conn):
    eid = _ev(conn, [_fs(3.0, startwert=0)])
    (vor,) = strecke_fundstellen(conn, eid)
    assert vor["startwert"] == "0"
    erg = strecke_fundstellen_setzen(conn, eid, [_fs(3.0, startwert=0)])
    assert erg["geblieben"] == 1, "sonst wuerde bei jedem Speichern neu gewuerfelt"


def test_richtung_leer_und_richtung_null_sind_verschieden(conn):
    eid = _ev(conn, [_fs(3.0)])
    erg = strecke_fundstellen_setzen(conn, eid, [_fs(3.0, richtung=0)])
    assert (erg["geblieben"], erg["neu"]) == (0, 1)
    erg = strecke_fundstellen_setzen(conn, eid, [_fs(3.0, richtung=360)])
    assert erg["geblieben"] == 1, "0 und 360 sind dieselbe Richtung"


@pytest.mark.parametrize("aenderung, wort", [
    ({"lat": 99.0}, "außerhalb"),
    ({"art": ""}, "was dort stehen soll"),
    ({"menge_min": 0}, "mindestens ein Objekt"),
    ({"abstand_max_m": 5}, "Höchstabstand"),
])
def test_unsinnige_fundstellen_werden_mit_einem_satz_abgelehnt(conn, aenderung, wort):
    eid = _ev(conn)
    with pytest.raises(ValueError, match="Fundstelle 1.*" + wort):
        strecke_fundstellen_setzen(conn, eid, [_fs(**aenderung)])


def test_zu_viele_fundstellen_werden_abgelehnt(conn):
    eid = _ev(conn)
    with pytest.raises(ValueError, match="Höchstens"):
        strecke_fundstellen_setzen(
            conn, eid, [_fs(i * 0.1) for i in range(db.STRECKE_FUNDSTELLEN_MAX + 1)])


# --- Finden --------------------------------------------------------------------------------

def test_wer_tief_und_nah_darueber_fliegt_findet(conn):
    eid = _ev(conn, [_fs(3.0), _fs(8.0)])
    ev = get_strecken_event(conn, eid)
    _flug(conn, 7, 0.0, 4.0)
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(300))
    eins, zwei = stand["fundstellen"]
    assert eins["gefunden_von"] == 7 and eins["gefunden_am"].startswith("2026-10-10T18:0")
    assert zwei["gefunden_am"] is None
    conn.commit()
    assert strecke_fundstellen(conn, eid)[0]["gefunden_von"] == 7, "steht in der Tabelle"


def test_zu_weit_daneben_findet_nicht_deckt_die_strecke_aber_ab(conn):
    """400 m seitlich: im Korridor (500 m), aber ausserhalb des Fundradius (150 m)."""
    eid = _ev(conn, [_fs(3.0)])
    _flug(conn, 7, 0.0, 6.0, nord_km=0.4)
    stand = strecke_fortschreiben(conn, get_strecken_event(conn, eid), bis=_zeit(300))
    assert stand["abgedeckt"] >= 5
    assert stand["fundstellen"][0]["gefunden_am"] is None


def test_zu_hoch_darueber_findet_nicht(conn):
    eid = _ev(conn, [_fs(3.0, grund_ft=200.0)], hoehe_max_ft=5000)
    _flug(conn, 7, 0.0, 6.0, alt=1300.0)            # 1.100 ft ueber der Stelle
    stand = strecke_fortschreiben(conn, get_strecken_event(conn, eid), bis=_zeit(300))
    assert stand["abgedeckt"] >= 5, "fuer die Strecke reicht die Hoehe"
    assert stand["fundstellen"][0]["gefunden_am"] is None


def test_die_fundhoehe_zaehlt_ueber_dem_gelaende_an_der_fundstelle(conn):
    eid = _ev(conn, [_fs(3.0, grund_ft=600.0)], hoehe_max_ft=5000)
    _flug(conn, 7, 0.0, 6.0, alt=1300.0)            # 700 ft ueber der Stelle
    stand = strecke_fortschreiben(conn, get_strecken_event(conn, eid), bis=_zeit(300))
    assert stand["fundstellen"][0]["gefunden_von"] == 7


def test_auch_langsam_darueber_wird_gefunden(conn):
    """Keine Mindestgeschwindigkeit beim Finden -- fuer die Strecke zaehlt so ein Schweben nicht."""
    eid = _ev(conn, [_fs(3.0)])
    _flug(conn, 7, 2.9, 3.1, gs=9.0)
    stand = strecke_fortschreiben(conn, get_strecken_event(conn, eid), bis=_zeit(300))
    assert stand["fundstellen"][0]["gefunden_von"] == 7
    assert stand["abgedeckt"] == 0


def test_der_erste_fund_bleibt(conn):
    eid = _ev(conn, [_fs(3.0)])
    ev = get_strecken_event(conn, eid)
    ende = _flug(conn, 7, 2.0, 4.0)
    strecke_fortschreiben(conn, ev, bis=_zeit(ende + 5))
    _flug(conn, 8, 2.0, 4.0, ab_s=ende + 20)
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(ende + 200))
    assert stand["fundstellen"][0]["gefunden_von"] == 7


def test_eine_fundstelle_abseits_der_strecke_wird_gefunden(conn):
    """20 km noerdlich -- weiter weg als der Rand um die Strecke (15 km)."""
    eid = _ev(conn, [_fs(3.0, nord_km=20.0)])
    _flug(conn, 7, 2.0, 4.0, nord_km=20.0)
    stand = strecke_fortschreiben(conn, get_strecken_event(conn, eid), bis=_zeit(300))
    assert stand["fundstellen"][0]["gefunden_von"] == 7


def test_fehlt_einer_fundstelle_die_hoehe_laeuft_die_strecke_weiter(conn):
    """Eine Fundstelle ohne Gelaendehoehe ist bloss selbst nicht zu finden -- sie haelt nicht
    den ganzen Abend an. Die andere Fundstelle wird gefunden, die Strecke gezaehlt."""
    eid = _ev(conn, [_fs(3.0, grund_ft=None), _fs(2.0)])
    ev = get_strecken_event(conn, eid)
    ende = _flug(conn, 7, 0.0, 4.0)
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(ende + 5))
    assert not stand["ohne_grund"] and stand["abgedeckt"] == 4
    assert [f["gefunden_von"] for f in stand["fundstellen"]] == [None, 7]
    # Mit der Hoehe ist sie ab dann zu finden.
    db.strecke_fundstellen_grund_setzen(conn, {stand["fundstellen"][0]["id"]: 0.0})
    _flug(conn, 8, 2.5, 3.5, ab_s=ende + 20)
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(ende + 200))
    assert stand["fundstellen"][0]["gefunden_von"] == 8


def test_wer_nur_mit_dem_kniebrett_fliegt_findet_nichts(conn):
    eid = _ev(conn, [_fs(3.0)])
    _flug(conn, 7, 0.0, 4.0, quelle="kniebrett")
    stand = strecke_fortschreiben(conn, get_strecken_event(conn, eid), bis=_zeit(300))
    assert stand["fundstellen"][0]["gefunden_am"] is None


def test_den_stand_verwerfen_nimmt_die_funde_mit(conn):
    eid = _ev(conn, [_fs(3.0)])
    ev = get_strecken_event(conn, eid)
    _flug(conn, 7, 0.0, 4.0)
    strecke_fortschreiben(conn, ev, bis=_zeit(300))
    strecke_stand_verwerfen(conn, eid)
    assert strecke_fundstellen(conn, eid)[0]["gefunden_am"] is None
    # ... und das Fortschreiben findet sie wieder, solange die Punkte liegen.
    assert strecke_fortschreiben(conn, ev, bis=_zeit(300))["fundstellen"][0]["gefunden_von"] == 7


# --- Stand fuer die Anzeige ------------------------------------------------------------------

def _stand(conn, eid, monkeypatch, jetzt, **kw):
    monkeypatch.setattr(db, "_now_utc", lambda: jetzt)
    return compute_strecke_stand(conn, get_strecken_event(conn, eid), **kw)


def test_der_stand_zaehlt_fundstellen_und_funde_je_pilot(conn, monkeypatch):
    eid = _ev(conn, [_fs(3.0), _fs(8.0)])
    conn.execute("INSERT INTO pilots (cid, name, added_at) VALUES (7, 'Anna', ?)", (START,))
    _flug(conn, 7, 0.0, 4.0)
    s = _stand(conn, eid, monkeypatch, MITTEN)
    assert s["fundstellen"] == {"anzahl": 2, "gefunden": 1}
    assert s["je_pilot"] == [{"cid": 7, "name": "Anna", "abschnitte": 4, "km": 4.0, "funde": 1}]


def test_eine_nicht_gefundene_fundstelle_verraet_waehrend_des_events_nichts(conn, monkeypatch):
    eid = _ev(conn, [_fs(3.0), _fs(8.0)])
    _flug(conn, 7, 0.0, 4.0)
    s = _stand(conn, eid, monkeypatch, MITTEN, mit_geometrie=True)
    (einzige,) = s["fundstellen"]["liste"]
    assert einzige["nr"] == 1 and einzige["gefunden"] and einzige["cid"] == 7
    assert einzige["lon"] == pytest.approx(_ost(3.0)) and einzige["menge"] >= 5
    assert einzige["art_name"].startswith("Eine Seehund-Kuh")
    # (Die Abschnittsgrenze bei 8 km steht in der Strecke -- gesucht wird bei den Fundstellen.)
    assert f"{_ost(8.0):.4f}" not in json.dumps(s["fundstellen"]), "die Lage der zweiten fehlt"
    assert len(json.dumps(s).split('"menge"')) == 2, "und sie steht auch sonst nirgends"


def test_nach_dem_ende_erscheinen_auch_die_nicht_gefundenen(conn, monkeypatch):
    eid = _ev(conn, [_fs(3.0), _fs(8.0)])
    _flug(conn, 7, 0.0, 4.0)
    s = _stand(conn, eid, monkeypatch, "2026-10-10T21:00:01Z", mit_geometrie=True)
    assert [(f["nr"], f["gefunden"]) for f in s["fundstellen"]["liste"]] == [(1, True), (2, False)]
    assert "cid" not in s["fundstellen"]["liste"][1]


def test_ohne_fundstellen_bleibt_der_stand_schlank(conn, monkeypatch):
    s = _stand(conn, _ev(conn), monkeypatch, MITTEN, mit_geometrie=True)
    assert s["fundstellen"] == {"anzahl": 0, "gefunden": 0}


# --- Objekte im Simulator --------------------------------------------------------------------

def _soll(conn, eid):
    return {r["id"]: r for r in bruegge_soll_alle(conn) if r["id"].startswith(f"strecke-{eid}-")}


def test_vor_dem_fund_stehen_die_objekte_nur_aus_der_naehe_im_soll(conn):
    eid = _ev(conn, [_fs(3.0)])
    (f,) = strecke_fundstellen(conn, eid)
    strecke_objekte_abgleichen(conn, get_strecken_event(conn, eid), now=MITTEN)
    soll = _soll(conn, eid)
    je_objekt = {i.split("-")[3] for i in soll}
    assert je_objekt == {str(i) for i in range(f["menge"])}
    assert all(r["nur_nah_m"] == 1000.0 and r["auf_boden"] == 1 and r["gilt_bis"] == ENDE
               for r in soll.values())
    assert all(r["kurs"] is not None for r in soll.values())
    assert not any("rauch" in i or "licht" in i for i in soll)


def test_nach_dem_fund_fuer_alle_sichtbar_mit_hellblauem_rauch_und_licht(conn):
    eid = _ev(conn, [_fs(3.0), _fs(8.0)])
    eins, zwei = strecke_fundstellen(conn, eid)
    conn.execute("UPDATE strecken_fundstellen SET gefunden_am = ?, gefunden_von = 7 WHERE id = ?",
                 (MITTEN, eins["id"]))
    strecke_objekte_abgleichen(conn, get_strecken_event(conn, eid), now=MITTEN)
    soll = _soll(conn, eid)
    gefunden = {i: r for i, r in soll.items() if f"-f{eins['id']}-" in i}
    verborgen = {i: r for i, r in soll.items() if f"-f{zwei['id']}-" in i}
    assert all(r["nur_nah_m"] is None for r in gefunden.values())
    assert {r["art"] for i, r in gefunden.items() if "-rauch" in i} == {"rauch_hellblau"}
    assert {r["art"] for i, r in gefunden.items() if "-licht" in i} == {"licht"}
    assert all(r["nur_nah_m"] == 1000.0 for r in verborgen.values())
    assert not any("rauch" in i for i in verborgen)
    # Die Objekte bleiben stehen -- es wird nichts aufgenommen.
    assert sum(1 for i in gefunden if i.split("-")[3].isdigit()) >= eins["menge"]


def test_der_abgleich_ist_wiederholbar(conn):
    eid = _ev(conn, [_fs(3.0)])
    ev = get_strecken_event(conn, eid)
    strecke_objekte_abgleichen(conn, ev, now=MITTEN)
    vor = {i: (r["lat"], r["lon"], r["art"]) for i, r in _soll(conn, eid).items()}
    strecke_objekte_abgleichen(conn, ev, now=MITTEN)
    assert {i: (r["lat"], r["lon"], r["art"]) for i, r in _soll(conn, eid).items()} == vor


@pytest.mark.parametrize("jetzt", ["2026-10-10T17:59:59Z", "2026-10-10T21:00:01Z"])
def test_vor_dem_beginn_und_nach_dem_ende_steht_nichts_im_soll(conn, jetzt):
    eid = _ev(conn, [_fs(3.0)])
    ev = get_strecken_event(conn, eid)
    strecke_objekte_abgleichen(conn, ev, now=MITTEN)
    assert _soll(conn, eid)
    strecke_objekte_abgleichen(conn, ev, now=jetzt)
    assert not _soll(conn, eid)


def test_was_nicht_mehr_gewollt_ist_faellt_weg_fremdes_bleibt(conn):
    eid = _ev(conn, [_fs(3.0), _fs(8.0)])
    ev = get_strecken_event(conn, eid)
    # Ein anderes Event mit aehnlicher Nummer und ein fremdes Objekt duerfen nicht mitgehen.
    bruegge_soll_setzen(conn, f"strecke-{eid}9-f1-0", "licht", LAT, LON)
    bruegge_soll_setzen(conn, "reddung-1-havarist", "licht", LAT, LON)
    strecke_objekte_abgleichen(conn, ev, now=MITTEN)
    vorher = len(_soll(conn, eid))
    strecke_fundstellen_setzen(conn, eid, [_fs(3.0)])
    strecke_objekte_abgleichen(conn, ev, now=MITTEN)
    assert 0 < len(_soll(conn, eid)) < vorher
    alle = {r["id"] for r in bruegge_soll_alle(conn)}
    assert f"strecke-{eid}9-f1-0" in alle and "reddung-1-havarist" in alle


def test_loeschen_nimmt_fundstellen_und_objekte_mit(conn):
    eid = _ev(conn, [_fs(3.0)])
    strecke_objekte_abgleichen(conn, get_strecken_event(conn, eid), now=MITTEN)
    delete_strecken_event(conn, eid)
    assert not _soll(conn, eid) and not strecke_fundstellen(conn, eid)


# --- Befunde der Pruefung vom 10.10.2026 -----------------------------------------------------

def test_eine_nachtraegliche_fundstelle_wird_auch_beim_neurechnen_nicht_rueckwirkend_gefunden(conn):
    """Pilot 7 fliegt ueber km 3, DANACH kommt dort eine Fundstelle dazu. Wird spaeter von vorn
    neu gerechnet (etwa weil das Ende verlaengert wird), darf er sie nicht gefunden haben --
    als er dort war, stand nichts da."""
    eid = _ev(conn)
    ev = get_strecken_event(conn, eid)
    ende = _flug(conn, 7, 0.0, 4.0)
    strecke_fortschreiben(conn, ev, bis=_zeit(ende + 5))
    strecke_fundstellen_setzen(conn, eid, [_fs(3.0)], gilt_ab=_zeit(ende + 10))
    strecke_stand_verwerfen(conn, eid)
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(ende + 60))
    assert stand["abgedeckt"] == 4 and stand["fundstellen"][0]["gefunden_am"] is None
    # Wer danach darueber fliegt, findet sie.
    _flug(conn, 8, 2.0, 4.0, ab_s=ende + 100)
    stand = strecke_fortschreiben(conn, ev, bis=_zeit(ende + 300))
    assert stand["fundstellen"][0]["gefunden_von"] == 8


def test_die_nummer_fuer_mitglieder_folgt_den_funden_nicht_der_verwaltung(conn, monkeypatch):
    """Sonst verrieten die Luecken zwischen den Nummern, wo noch etwas liegt."""
    eid = _ev(conn, [_fs(2.0), _fs(5.0), _fs(8.3)])
    _flug(conn, 7, 7.5, 9.0)                         # findet zuerst die DRITTE der Verwaltung
    s = _stand(conn, eid, monkeypatch, MITTEN, mit_geometrie=True)
    (einzige,) = s["fundstellen"]["liste"]
    assert einzige["nr"] == 1 and einzige["lon"] == pytest.approx(_ost(8.3))
    s = _stand(conn, eid, monkeypatch, "2026-10-10T21:00:01Z", mit_geometrie=True)
    assert [(f["nr"], f["gefunden"]) for f in s["fundstellen"]["liste"]] == [
        (1, True), (2, False), (3, False)]


def test_im_umkreis_einer_fundstelle_abseits_der_strecke_wird_mitgeschrieben(conn, monkeypatch):
    """Die Wache der Sekundenpunkte muss die Fundstellen kennen -- sonst gaebe es dort keine
    Punkte, aus denen ein Fund entstehen koennte."""
    _ev(conn, [_fs(3.0, nord_km=40.0)])
    monkeypatch.setattr(db, "_now_utc", lambda: MITTEN)
    lage = {"lat": _nord(40.0), "lon": _ost(3.0), "alt_msl_ft": 800.0, "gs_kt": 100.0}
    assert db.bruegge_spur_schreiben(conn, 7, lage) is True
    assert db.bruegge_spur_schreiben(conn, 7, {**lage, "lat": _nord(80.0)}) is False


def test_zwei_events_am_selben_abend_zaehlen_zusammen(conn):
    a = _ev(conn, [_fs(3.0, menge_min=10, menge_max=10)])
    b = _ev(conn, [_fs(4.0, menge_min=20, menge_max=20), _fs(5.0, menge_min=1, menge_max=1)])
    spaeter = create_strecken_event(conn, name="naechste Woche", punkte=GERADE,
                                    dtstart="2026-10-17T18:00:00Z", dtend="2026-10-17T21:00:00Z")
    assert db.strecke_soll_bedarf_andere(conn, a, START, ENDE) == 25      # 20 + 1 + je 2
    assert db.strecke_soll_bedarf_andere(conn, b, START, ENDE) == 12
    assert db.strecke_soll_bedarf_andere(conn, spaeter, "2026-10-17T18:00:00Z",
                                         "2026-10-17T21:00:00Z") == 0
