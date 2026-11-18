"""Sonderorden: von Hand vergebene Orden in der Ordensleiste (18.11.2026).

Erster Fall: Gebirgsflug Teil 4 „Tobl will heim“ am 16.11.2026, Patch für Reiner (FRS61),
Engelhard (FRS123) und Tobias (FRS49, mit eigenem Patch samt Callsign).
"""
from pathlib import Path

import app.main as main

ROOT = Path(__file__).resolve().parents[1]


def test_jeder_sonderorden_hat_sein_bild():
    for o in main._SONDERORDEN:
        assert o["bild"].startswith("/static/orden/")
        assert (ROOT / "app" / o["bild"].lstrip("/")).is_file(), o["bild"]


def test_gebirgsflug_fuer_die_drei_teilnehmer():
    g = [o for o in main._SONDERORDEN if o["name"] == "Gebirgsflug Teil 4"]
    assert {o["cid"] for o in g} == {1031301, 1642160, 1602713}
    assert all(o["datum"] == "2026-11-16T19:00:00Z" for o in g)
    eigen = next(o for o in g if o["cid"] == 1602713)
    assert eigen["bild"].endswith("-frs49.png")


def test_sonderorden_im_zeitraum(monkeypatch):
    monkeypatch.setattr(main, "_now_iso", lambda: "2026-11-18T04:00:00Z")
    eintraege = main._sonderorden_fuer(1031301, "2026-10-19T04:00:00Z")
    assert len(eintraege) == 1 and eintraege[0]["art"] == "sonder"
    assert main._sonderorden_fuer(1031301, "2026-11-17T00:00:00Z") == []   # vor dem Zeitraum
    assert main._sonderorden_fuer(999, "2026-01-01T00:00:00Z") == []
