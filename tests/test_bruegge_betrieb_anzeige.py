"""Die Betriebstabelle der FriesenBruegge im Admin (Nutzer, 27.09.2026).

Zwei Irrefuehrungen: „ruht" verdeckte „bewaehrt" -- drei bewaehrte Bruegges sahen aus, als
haetten sie ihre Bewaehrung verloren. Und ein angemeldeter Pilot, der nicht unter FRS fliegt
(AUA37R), stand nur als nackte CID da und wurde fuer einen anderen gehalten.
"""
from __future__ import annotations

from pathlib import Path

import app.main as main

_ADMIN = (Path(__file__).resolve().parents[1] / "app" / "static" / "admin.html").read_text(encoding="utf-8")


def test_ein_fremdes_rufzeichen_kommt_aus_dem_vatsim_schnappschuss():
    melder = [{"cid": 1271544, "callsign": None, "name": None},
              {"cid": 1031301, "callsign": None, "name": "Reiner EDVM"},
              {"cid": 1602713, "callsign": "FRS49", "name": "Tobias EDKB"}]
    schnapp = [{"cid": 1271544, "cs": "AUA37R"}, {"cid": 1602713, "cs": "XYZ"}, {"cid": "kaputt"}]
    main._melder_rufzeichen_ergaenzen(melder, schnapp)
    assert melder[0]["callsign"] == "AUA37R"
    assert melder[1]["callsign"] is None, "ohne Verbindung bleibt es beim Namen"
    assert melder[2]["callsign"] == "FRS49", "ein vorhandenes Rufzeichen bleibt"


def test_ruht_verdeckt_bewaehrt_nicht_mehr():
    stelle = _ADMIN[_ADMIN.index("const bindung = "):_ADMIN.index("return '<tr' + blass")]
    assert "'bewährt · ruht'" in stelle
    assert stelle.index("'bewährt · ruht'") < stelle.index("'ruht'")
