"""Live-Stand von Kutter/Bummel kurz zwischenhalten (Großevent 25.11.2026).

Gemessen beim Geburtstags-Kutter: rund ein Abruf je Sekunde, jeder rechnete den kompletten
Stand neu (gut 1 s). Die Abrufe standen an der Sperre an und rechneten danach trotzdem selbst --
der Prozess hing dauerhaft an einem Kern, der VATSIM-Abruf kam 2-5 s zu spät dran.
"""
import app.main as main
from app.database import get_connection, init_db


def _conn(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    return get_connection(db)


def _zaehler():
    n = {"x": 0}

    def rechnen():
        n["x"] += 1
        return {"flights": [{"quip": None}], "n": n["x"]}
    return n, rechnen


def test_innerhalb_der_haltezeit_wird_nur_einmal_gerechnet(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "_LIVE_STAND_HALTEN_S", 10.0)
    conn = _conn(tmp_path)
    n, rechnen = _zaehler()
    for _ in range(5):
        main._frozen_or_compute(conn, "kutter", 1, finished=False, compute_fn=rechnen, now="x")
    assert n["x"] == 1


def test_nach_ablauf_wird_neu_gerechnet(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "_LIVE_STAND_HALTEN_S", 10.0)
    uhr = {"t": 1000.0}
    monkeypatch.setattr(main, "_uhr", lambda: uhr["t"])
    conn = _conn(tmp_path)
    n, rechnen = _zaehler()
    main._frozen_or_compute(conn, "kutter", 1, finished=False, compute_fn=rechnen, now="x")
    uhr["t"] += 9.9
    main._frozen_or_compute(conn, "kutter", 1, finished=False, compute_fn=rechnen, now="x")
    assert n["x"] == 1
    uhr["t"] += 0.2
    main._frozen_or_compute(conn, "kutter", 1, finished=False, compute_fn=rechnen, now="x")
    assert n["x"] == 2


def test_jeder_abruf_bekommt_eine_eigene_kopie(tmp_path, monkeypatch):
    # _kutter_progress schreibt Sprüche in die Flug-Dicts -- das darf den Vorrat nicht verändern.
    monkeypatch.setattr(main, "_LIVE_STAND_HALTEN_S", 10.0)
    conn = _conn(tmp_path)
    _, rechnen = _zaehler()
    a = main._frozen_or_compute(conn, "kutter", 1, finished=False, compute_fn=rechnen, now="x")
    a["flights"][0]["quip"] = "verändert"
    b = main._frozen_or_compute(conn, "kutter", 1, finished=False, compute_fn=rechnen, now="x")
    assert b["flights"][0]["quip"] is None


def test_events_und_arten_getrennt(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "_LIVE_STAND_HALTEN_S", 10.0)
    conn = _conn(tmp_path)
    n, rechnen = _zaehler()
    for kind, ref in (("kutter", 1), ("kutter", 2), ("bummel", 1)):
        main._frozen_or_compute(conn, kind, ref, finished=False, compute_fn=rechnen, now="x")
    assert n["x"] == 3


def test_in_der_testsuite_aus(tmp_path):
    # conftest stellt die Haltezeit auf 0: Tests, die Daten ändern und gleich neu abrufen,
    # sehen sonst einen alten Stand.
    conn = _conn(tmp_path)
    n, rechnen = _zaehler()
    main._frozen_or_compute(conn, "kutter", 1, finished=False, compute_fn=rechnen, now="x")
    main._frozen_or_compute(conn, "kutter", 1, finished=False, compute_fn=rechnen, now="x")
    assert n["x"] == 2


def test_produktion_haelt_zehn_sekunden():
    import importlib.util, pathlib
    src = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    assert "_LIVE_STAND_HALTEN_S = 10.0" in src
