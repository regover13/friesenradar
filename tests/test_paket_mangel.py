# -*- coding: utf-8 -*-
"""Hinweis nach einem Flug mit fehlendem oder altem Paket (Nutzerwunsch 12.10.2026).

Geprueft wird am LETZTEN beendeten Flug des Piloten: Hat waehrend des Fluges eine
FriesenBruegge gemeldet, und mit welcher Fassung? Dasselbe fuers Kniebrett. Der Banner laesst
sich wegklicken und kommt mit dem naechsten Flug wieder, solange der Mangel besteht.

Fehlt ein Paket ganz, gibt es nur den Banner. Eine Push-Meldung geht allein bei einem
VERALTETEN Paket raus -- wer nie etwas installiert hat, soll keine Meldungen bekommen.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import paket_hinweis as ph
from app.database import (bind_panel_device, bruegge_version_merken, bruegge_zuordnung_setzen,
                          get_connection, init_db, touch_panel_device)

CID = 1602713
AKTUELL = {"msfs": "1.19.0", "xplane": "1.5.0", "kniebrett": "3.0.0"}
JETZT = datetime(2026, 10, 12, 19, 20, tzinfo=timezone.utc)   # 20 min nach der Landung


@pytest.fixture()
def conn(tmp_path):
    p = str(tmp_path / "t.db")
    init_db(p)
    c = get_connection(p)
    yield c
    c.close()


def _flug(conn, logon="2026-10-12T18:00:00Z", logoff="2026-10-12T19:00:00Z", cid=CID,
          callsign="FRS49", minuten=60):
    conn.execute("INSERT OR IGNORE INTO pilots (cid, name, added_at, active) "
                 "VALUES (?, 'Test', '2026-01-01T00:00:00Z', 1)", (cid,))
    cur = conn.execute(
        "INSERT INTO flights (cid, callsign, logon_time, logoff_time, duration_min) "
        "VALUES (?, ?, ?, ?, ?)", (cid, callsign, logon, logoff, minuten))
    conn.commit()
    return cur.lastrowid


def _bruegge(conn, version, simulator="msfs2024", gesehen="2026-10-12T18:30:00Z",
             kennung="K1", cid=CID):
    bruegge_zuordnung_setzen(conn, kennung, cid, simulator)
    bruegge_version_merken(conn, kennung, version)
    conn.execute("UPDATE bruegge_zuordnung SET gesehen_am = ? WHERE kennung = ?",
                 (gesehen, kennung))
    conn.commit()


def _kniebrett(conn, version, gesehen="2026-10-12T18:30:00Z", geraet="d" * 40, cid=CID):
    bind_panel_device(conn, geraet, cid, "Tablet")
    touch_panel_device(conn, geraet, paket_version=version)
    conn.execute("UPDATE panel_devices SET last_seen_at = ? WHERE device_id = ?",
                 (gesehen, geraet))
    conn.commit()


def _arten(conn, **kw):
    return [z["art"] for z in ph.stand(conn, CID, AKTUELL, **kw)["zeilen"]]


# --- Was als Mangel gilt --------------------------------------------------------------------

def test_ohne_flug_gibt_es_nichts(conn):
    assert ph.stand(conn, CID, AKTUELL) == {"flug_id": None, "zeilen": [], "zeigen": False}


def test_flug_ohne_bruegge(conn):
    _flug(conn)
    assert _arten(conn) == ["bruegge_fehlt"]


def test_flug_mit_alter_bruegge(conn):
    _flug(conn)
    _bruegge(conn, "1.17.0", simulator="msfs2020")
    (z,) = ph.stand(conn, CID, AKTUELL)["zeilen"]
    assert z["art"] == "bruegge_alt"
    assert "1.17.0" in z["text"] and "1.19.0" in z["text"]
    assert "radar.friesenflieger.de/download" in z["text"]


def test_xplane_wird_gegen_das_xplane_paket_gehalten(conn):
    _flug(conn)
    _bruegge(conn, "1.5.0", simulator="xplane12")
    assert _arten(conn) == []


def test_bruegge_von_einem_frueheren_flug_zaehlt_nicht(conn):
    """Wer letzte Woche mit Bruegge flog und heute ohne, flog heute ohne."""
    _flug(conn)
    _bruegge(conn, "1.19.0", gesehen="2026-10-05T18:30:00Z")
    assert _arten(conn) == ["bruegge_fehlt"]


def test_bruegge_ohne_gemeldete_fassung_wird_nicht_verdaechtigt(conn):
    _flug(conn)
    _bruegge(conn, None, simulator="msfs2020")
    assert _arten(conn) == []


def test_altes_kniebrett(conn):
    _flug(conn)
    _bruegge(conn, "1.19.0", simulator="msfs2024")
    _kniebrett(conn, "2.3.1")
    (z,) = ph.stand(conn, CID, AKTUELL)["zeilen"]
    assert z["art"] == "kniebrett_alt" and "2.3.1" in z["text"] and "3.0.0" in z["text"]


def test_kniebrett_ohne_gemeldete_fassung_ist_aelter_als_2_0_0(conn):
    _flug(conn)
    _bruegge(conn, "1.19.0", simulator="msfs2024")
    _kniebrett(conn, None)
    (z,) = ph.stand(conn, CID, AKTUELL)["zeilen"]
    assert z["art"] == "kniebrett_alt" and "vor 2.0.0" in z["text"]


def test_fehlendes_kniebrett_nur_bei_msfs_2024(conn):
    _flug(conn)
    _bruegge(conn, "1.19.0", simulator="msfs2024")
    assert _arten(conn) == ["kniebrett_fehlt"]


@pytest.mark.parametrize("simulator", ["msfs2020", "xplane12"])
def test_fehlendes_kniebrett_in_anderen_simulatoren_ist_kein_mangel(conn, simulator):
    _flug(conn)
    _bruegge(conn, AKTUELL["xplane" if simulator == "xplane12" else "msfs"], simulator=simulator)
    assert _arten(conn) == []


def test_ohne_bruegge_ist_der_simulator_unbekannt_also_kein_wort_zum_fehlenden_kniebrett(conn):
    _flug(conn)
    assert "kniebrett_fehlt" not in _arten(conn)


# Das Kniebrett meldet sich nur beim START (``/auth/device``), und es startet mit dem Simulator
# -- also in aller Regel VOR der Anmeldung bei VATSIM. Bis 16.5.0 zaehlte nur ein Lebenszeichen
# WAEHREND des Flugs; damit galt das Kniebrett bei fast jedem als fehlend (Fund 13.10.2026: drei
# von vier Meldungen falsch, eine davon beim Nutzer selbst).

def test_kniebrett_vor_dem_flug_gestartet_fehlt_nicht(conn):
    _flug(conn)                                             # Anmeldung 18:00
    _bruegge(conn, "1.19.0")
    _kniebrett(conn, "3.0.0", gesehen="2026-10-12T17:54:00Z")
    assert _arten(conn) == []


def test_altes_kniebrett_von_voriger_woche_ist_alt_und_nicht_fehlend(conn):
    _flug(conn)
    _bruegge(conn, "1.19.0")
    _kniebrett(conn, "2.3.2", gesehen="2026-10-05T07:18:00Z")
    (z,) = ph.stand(conn, CID, AKTUELL)["zeilen"]
    assert z["art"] == "kniebrett_alt" and "2.3.2" in z["text"]


def test_von_mehreren_geraeten_zaehlt_das_zuletzt_gesehene(conn):
    _flug(conn)
    _bruegge(conn, "1.19.0")
    _kniebrett(conn, "2.0.0", gesehen="2026-09-01T10:00:00Z", geraet="a" * 40)
    _kniebrett(conn, "3.0.0", gesehen="2026-10-12T17:54:00Z", geraet="b" * 40)
    assert _arten(conn) == []


def test_ohne_bruegge_wird_ein_altes_kniebrett_trotzdem_genannt(conn):
    _flug(conn)
    _kniebrett(conn, "2.2.0", gesehen="2026-10-12T07:00:00Z")
    assert _arten(conn) == ["bruegge_fehlt", "kniebrett_alt"]


@pytest.mark.parametrize("simulator", ["msfs2020", "xplane12"])
def test_in_anderen_simulatoren_wird_das_kniebrett_gar_nicht_beurteilt(conn, simulator):
    """Das Kniebrett gibt es nur in MSFS 2024. Wer heute woanders flog, bekommt kein Wort zu
    einem Geraet, das irgendwann einmal gebunden wurde."""
    _flug(conn)
    _bruegge(conn, AKTUELL["xplane" if simulator == "xplane12" else "msfs"], simulator=simulator)
    _kniebrett(conn, "2.0.0", gesehen="2026-09-01T10:00:00Z")
    assert _arten(conn) == []


def test_ein_fremdes_kniebrett_zaehlt_nicht_fuer_mich(conn):
    _flug(conn)
    _flug(conn, cid=999)
    _bruegge(conn, "1.19.0")
    _kniebrett(conn, "3.0.0", cid=999)
    assert _arten(conn) == ["kniebrett_fehlt"]


def test_alles_aktuell_ist_still(conn):
    _flug(conn)
    _bruegge(conn, "1.19.0")
    _kniebrett(conn, "3.0.0")
    assert ph.stand(conn, CID, AKTUELL)["zeigen"] is False


def test_der_laufende_flug_zaehlt_noch_nicht(conn):
    """Geurteilt wird am Ende: Die Bruegge kann im Flug noch dazukommen."""
    _flug(conn, logoff=None, minuten=None)
    assert ph.stand(conn, CID, AKTUELL)["flug_id"] is None


def test_ein_verbindungstest_von_zwei_minuten_ist_kein_flug(conn):
    _flug(conn, logoff="2026-10-12T18:02:00Z", minuten=2)
    assert ph.stand(conn, CID, AKTUELL)["flug_id"] is None


def test_ein_zusammengefuehrter_flug_zaehlt_nicht_doppelt(conn):
    f = _flug(conn)
    conn.execute("UPDATE flights SET superseded_by = ? WHERE id = ?", (f + 1000, f))
    conn.commit()
    assert ph.stand(conn, CID, AKTUELL)["flug_id"] is None


def test_fremde_fluege_und_fremde_brueggen_gehen_niemanden_etwas_an(conn):
    _flug(conn, cid=999)
    assert ph.stand(conn, CID, AKTUELL)["flug_id"] is None
    _flug(conn)
    _bruegge(conn, "1.19.0", cid=999, kennung="F1")
    assert _arten(conn) == ["bruegge_fehlt"]


def test_ohne_hinterlegtes_paket_gibt_es_kein_urteil_ueber_die_fassung(conn):
    _flug(conn)
    _bruegge(conn, "1.0.0")
    _kniebrett(conn, "1.0.0")
    assert [z["art"] for z in ph.stand(conn, CID, {})["zeilen"]] == []


# Die Fassung kommt vom Geraet des Piloten und landet im Banner und in der Push-Meldung. Eine
# Bruegge laesst sich einem fremden Piloten unterschieben (gefaelschte Position, s. CLAUDE.md),
# also darf dort nichts stehen, was keine Versionsnummer ist.
@pytest.mark.parametrize("unfug", ["Bitte sofort anrufen", "1.2.3 <b>x</b>", "1.2.3; rm", "v1.2",
                                   "1..2", "1.2.3.4.5", "9" * 30])
def test_was_keine_versionsnummer_ist_kommt_in_keinen_text(conn, unfug):
    _flug(conn)
    _bruegge(conn, unfug, simulator="msfs2020")
    _kniebrett(conn, unfug)
    texte = " ".join(z["text"] for z in ph.stand(conn, CID, AKTUELL)["zeilen"])
    assert unfug not in texte
    assert all(unfug not in p["body"] for _, _, p in ph.push_faellig(conn, JETZT, AKTUELL))


def test_eine_unlesbare_bruegge_fassung_ist_kein_urteil(conn):
    _flug(conn)
    _bruegge(conn, "Bitte sofort anrufen", simulator="msfs2020")
    assert _arten(conn) == []


# --- Wegklicken ------------------------------------------------------------------------------

def test_weggeklickt_bleibt_weg_bis_zum_naechsten_flug_mit_mangel(conn):
    erster = _flug(conn)
    assert ph.stand(conn, CID, AKTUELL)["zeigen"] is True
    ph.wegklicken(conn, CID, erster)
    s = ph.stand(conn, CID, AKTUELL)
    assert s["zeigen"] is False and s["zeilen"], "der Mangel besteht, nur der Banner ist weg"
    zweiter = _flug(conn, logon="2026-10-13T18:00:00Z", logoff="2026-10-13T19:00:00Z")
    s = ph.stand(conn, CID, AKTUELL)
    assert s["flug_id"] == zweiter and s["zeigen"] is True


def test_wegklicken_eines_alten_flugs_versteckt_den_neuen_nicht(conn):
    """Zwei Geraete: Das eine klickt den Stand von gestern weg, nachdem heute geflogen wurde."""
    erster = _flug(conn)
    _flug(conn, logon="2026-10-13T18:00:00Z", logoff="2026-10-13T19:00:00Z")
    ph.wegklicken(conn, CID, erster)
    assert ph.stand(conn, CID, AKTUELL)["zeigen"] is True


def test_wegklicken_geht_nicht_rueckwaerts(conn):
    erster = _flug(conn)
    zweiter = _flug(conn, logon="2026-10-13T18:00:00Z", logoff="2026-10-13T19:00:00Z")
    ph.wegklicken(conn, CID, zweiter)
    ph.wegklicken(conn, CID, erster)
    assert ph.stand(conn, CID, AKTUELL)["zeigen"] is False


# --- Push: nur bei veraltetem Paket, einmal je Flug -------------------------------------------



def _faellig(conn, jetzt=JETZT, aktuell=AKTUELL):
    return ph.push_faellig(conn, jetzt, aktuell)


def test_fehlende_pakete_loesen_keinen_push_aus(conn):
    _flug(conn)
    assert _faellig(conn) == []


def test_altes_paket_loest_einen_push_aus(conn):
    f = _flug(conn)
    _bruegge(conn, "1.17.0")
    ((cid, flug, payload),) = _faellig(conn)
    assert (cid, flug) == (CID, f)
    assert "1.17.0" in payload["body"] and "1.19.0" in payload["body"]
    assert payload["title"] and payload["url"] == "/"


def test_der_push_nennt_nur_das_veraltete(conn):
    """Bruegge alt, Kniebrett fehlt (MSFS 2024): Im Push steht nur die Bruegge."""
    _flug(conn)
    _bruegge(conn, "1.17.0", simulator="msfs2024")
    ((_, _, payload),) = _faellig(conn)
    assert "FriesenBrügge" in payload["body"] and "Kniebrett" not in payload["body"]


def test_push_erst_eine_viertelstunde_nach_der_landung(conn):
    """So lange gilt ein Abbruch noch als derselbe Flug (Wiederverbinden)."""
    _flug(conn)
    _bruegge(conn, "1.17.0")
    assert _faellig(conn, jetzt=JETZT - timedelta(minutes=10)) == []


def test_kein_push_fuer_einen_flug_von_gestern(conn):
    """Nach einem Stillstand des Servers soll nichts Altes nachkommen."""
    _flug(conn)
    _bruegge(conn, "1.17.0")
    assert _faellig(conn, jetzt=JETZT + timedelta(hours=3)) == []


def test_ein_flug_wird_nur_einmal_gemeldet(conn):
    f = _flug(conn)
    _bruegge(conn, "1.17.0")
    assert len(_faellig(conn)) == 1
    ph.push_merken(conn, CID, f)
    assert _faellig(conn) == []


def test_push_merken_loescht_das_wegklicken_nicht(conn):
    f = _flug(conn)
    _bruegge(conn, "1.17.0")
    ph.wegklicken(conn, CID, f)
    ph.push_merken(conn, CID, f)
    assert ph.stand(conn, CID, AKTUELL)["zeigen"] is False


# --- Der Job im Poller ------------------------------------------------------------------------

def test_der_poller_schickt_nur_an_die_abos_des_piloten_und_merkt_es_vorher(tmp_path, monkeypatch):
    import asyncio
    from app import poller as pm
    p = str(tmp_path / "t.db")
    init_db(p)
    c = get_connection(p)
    f = _flug(c)
    _bruegge(c, "1.17.0", simulator="msfs2020")
    for endpunkt, besitzer in (("https://push/eigen", CID), ("https://push/fremd", 999)):
        c.execute("INSERT INTO push_subscriptions (endpoint, p256dh, auth, owner_cid, created_at) "
                  "VALUES (?, 'k', 'a', ?, '2026-01-01T00:00:00Z')", (endpunkt, besitzer))
    c.commit()
    gesendet = []

    async def _senden(key, mail, db, subs, payload, label="WebPush"):
        gemerkt = get_connection(db).execute(
            "SELECT push_flug_id FROM paket_hinweis WHERE cid = ?", (CID,)).fetchone()
        gesendet.append(([s["endpoint"] for s in subs], payload, gemerkt and gemerkt[0]))

    monkeypatch.setattr(pm, "send_web_push", _senden)
    po = pm.VatsimPoller.__new__(pm.VatsimPoller)
    po.db_path, po.vapid_private_key, po.vapid_contact_email = p, "schluessel", "a@b.c"
    po.paket_aktuell = lambda: AKTUELL
    asyncio.run(po._paket_push(jetzt=JETZT))
    asyncio.run(po._paket_push(jetzt=JETZT))
    assert len(gesendet) == 1, "ein Flug, eine Meldung"
    empfaenger, payload, gemerkt = gesendet[0]
    assert empfaenger == ["https://push/eigen"]
    assert "1.17.0" in payload["body"]
    assert gemerkt == f, "erst merken, dann senden: Ein Absturz dazwischen darf nichts doppelt schicken"
    c.close()


def test_ohne_hinterlegte_fassungen_schweigt_der_job(tmp_path):
    import asyncio
    from app import poller as pm
    p = str(tmp_path / "t.db")
    init_db(p)
    po = pm.VatsimPoller.__new__(pm.VatsimPoller)
    po.db_path, po.vapid_private_key, po.vapid_contact_email = p, "schluessel", "a@b.c"
    asyncio.run(po._paket_push(jetzt=JETZT))   # kein `paket_aktuell` gesetzt: kein Fehler
