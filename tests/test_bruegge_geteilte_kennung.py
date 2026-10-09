# -*- coding: utf-8 -*-
"""Zwei Brüggen am selben Ort — der Fall vom 14.09.2026, und was ihn löst.

Zwei Piloten stehen auf demselben Vorfeld, beide mit Brügge. Der Server bekommt zwei
Meldungen, die einander zum Verwechseln ähnlich sehen, und muss sie auseinanderhalten.

**Erster Anlauf war `deutlich_besser`, und er war falsch.** Er hängte eine gemerkte
Zuordnung bei jeder Meldung um, sobald ein anderer Kandidat halb so weit weg war — ohne
Verstoßzähler. Das hat live so ausgesehen::

    19:30:22  Kennung 9e3711c100000000 haengt um, 1642160 -> 1602713 (572 m gegen 1175 m)

572/1175 = 0,486, also knapp „deutlich besser": Einem Piloten wurde seine Zuordnung bei
572 m Abstand an jemanden abgegeben, der 1,2 km entfernt war. Die Funktion ist entfernt.

**Danach trug `belegt`** — wessen CID gerade eine ANDERE Brügge meldete, war als Kandidat
vergeben. Diese Regel gehörte zum alten Zuordnungsweg der MSFS-Brügge und ist mit ihm
ausgebaut. Seit Protokoll 3 entsteht die Verwechslung nicht mehr über die Nähe: Im Stand
bindet eine Brügge nur auf 5 m und nur an eine Verbindung, die nach ihr kam; bei Gleichstand
entscheidet das Anrollen (`app/bruegge_bindung.py`, geprüft in tests/test_bruegge_bindung.py).

Hier bleiben die Ausgangslage des Vorfalls und die Regel, die nicht zurückkommen darf.
"""

from app import bruegge

# Die echten Koordinaten des Vorfalls (Wangerooge).
FRS49 = (53.787560, 7.909490)
FRS123 = (53.786790, 7.911000)

# Ungefähr mittig zwischen beiden: von hier aus hat keiner der beiden einen Vorsprung.
MITTE = ((FRS49[0] + FRS123[0]) / 2, (FRS49[1] + FRS123[1]) / 2)


def _kandidat(cid: int, rufz: str, lat: float, lon: float,
              alt_ft: float = 10.0) -> bruegge.Kandidat:
    return bruegge.Kandidat(cid=cid, callsign=rufz, lat=lat, lon=lon, alt_ft=alt_ft)


def _beide() -> list[bruegge.Kandidat]:
    return [_kandidat(1602713, "FRS49", *FRS49), _kandidat(1642160, "FRS123", *FRS123)]


# ---------------------------------------------------------------------------------------
# Die Ausgangslage — ohne sie prüfen die Tests darunter etwas anderes
# ---------------------------------------------------------------------------------------

def test_die_beiden_stehen_naeher_als_die_toleranz():
    d = bruegge.abstand_m(*FRS49, *FRS123)
    assert 100 < d < bruegge.PAARUNG_MIN_M, f"{d:.0f} m"


def test_bleibt_plausibel_sieht_den_fehler_NICHT():
    """Der Grund, warum es überhaupt schiefging: Die Plausibilitätsprüfung sagt brav ja."""
    fremder = _kandidat(1642160, "FRS123", *FRS123)
    assert bruegge.bleibt_plausibel(*FRS49, 10.0, 0.0, fremder) is True


# ---------------------------------------------------------------------------------------
# Und die Regel, die NICHT zurückkommen darf
# ---------------------------------------------------------------------------------------

def test_deutlich_besser_ist_entfernt_und_bleibt_es():
    """Eine gemerkte Zuordnung wird geprüft, nicht neu ausgehandelt.

    Wer die Funktion wieder einführt, hebelt die harte Bindung aus, die das Kniebrett seit
    v13.2.0 trägt.
    """
    assert not hasattr(bruegge, "deutlich_besser"), (
        "deutlich_besser haengte Zuordnungen ohne Verstosszaehler um "
        "(572 m gegen 1175 m, 14.09.2026) -- s. Begruendung in app/bruegge.py"
    )
