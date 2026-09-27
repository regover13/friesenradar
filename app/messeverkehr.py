"""Generator fuer simulierten Friesen-Verkehr auf der Live-Karte (Messestand-Modus).

Reine Funktionen, kein Netzzugriff: berechnet Positionen entlang einer Punkt-zu-Punkt-Strecke
zwischen zwei Flugplaetzen und schreibt sie ueber app.database in eine eigene, von echten Daten
komplett getrennte Tabelle. Siehe docs/superpowers/specs/2026-09-27-messeverkehr-design.md.
"""
from __future__ import annotations

import math
import random
from datetime import datetime

from app.database import get_messeverkehr_positions, replace_messeverkehr_positions
from app.geo import haversine

# Feste Liste norddeutscher/friesischer Flugplaetze fuer plausible Kurzstrecken.
MESSEVERKEHR_FLUGPLAETZE = {
    "EDXW": (54.1826, 8.6875),   # Wyk auf Foehr
    "EDXH": (54.9098, 8.3406),   # Helgoland-Duene
    "EDHL": (53.8022, 10.7192),  # Luebeck
    "EDHF": (54.1147, 9.5350),   # Itzehoe-Hungriger Wolf
    "EDXR": (54.6725, 8.9433),   # Husum
    "EDVE": (52.3461, 10.5561),  # Braunschweig
}

ZIEL_ANZAHL_FLUEGE = 3
_REISEGESCHWINDIGKEIT_KT = 110.0
_REISEHOEHE_FT = 3500
_KT_IN_KM_PRO_S = 1.852 / 3600.0

# Synthetische CIDs: fest belegter, garantiert negativer Bereich, ein Slot je Ziel-Flug.
_CID_BASIS = -900000


def _synthetischer_pilotenname(slot: int) -> str:
    namen = ["Messe-Friese Nord", "Messe-Friese Sued", "Messe-Friese Ost",
             "Messe-Friese West", "Messe-Friese Mitte"]
    return namen[slot % len(namen)]


def _freies_callsign(slot: int, belegt: set[str]) -> str:
    """Erstes freies FRS-Callsign ab einer slot-abhaengigen Basisnummer.

    Weicht auf die naechste Nummer aus, falls sie gerade von einem ECHTEN Flug belegt ist.
    """
    basis = 800 + slot * 10
    for versuch in range(10):
        kandidat = f"FRS{basis + versuch}"
        if kandidat not in belegt:
            return kandidat
    return f"FRS{basis}X{random.randint(0, 99)}"


def _neuer_flug(slot: int, jetzt: datetime, belegt: set[str]) -> dict:
    platzcodes = list(MESSEVERKEHR_FLUGPLAETZE.keys())
    start, ziel = random.sample(platzcodes, 2)
    lat0, lon0 = MESSEVERKEHR_FLUGPLAETZE[start]
    return {
        "cid": _CID_BASIS - slot,
        "callsign": _freies_callsign(slot, belegt),
        "aircraft": "C172",
        "departure": start,
        "arrival": ziel,
        "latitude": lat0,
        "longitude": lon0,
        "altitude": _REISEHOEHE_FT,
        "groundspeed": int(_REISEGESCHWINDIGKEIT_KT),
        "heading": 0,
        "logon_time": jetzt.isoformat().replace("+00:00", "Z"),
        "updated_at": jetzt.isoformat().replace("+00:00", "Z"),
        "name": _synthetischer_pilotenname(slot),
        "_fortschritt_km": 0.0,
    }


def _fortschreiben(flug: dict, delta_s: float, jetzt: datetime) -> dict:
    lat0, lon0 = MESSEVERKEHR_FLUGPLAETZE[flug["departure"]]
    lat1, lon1 = MESSEVERKEHR_FLUGPLAETZE[flug["arrival"]]
    strecke_km = haversine(lat0, lon0, lat1, lon1) or 0.001

    fortschritt_km = (flug.get("_fortschritt_km", 0.0)
                       + delta_s * _KT_IN_KM_PRO_S * _REISEGESCHWINDIGKEIT_KT)
    anteil = min(fortschritt_km / strecke_km, 1.0)

    lat = lat0 + (lat1 - lat0) * anteil
    lon = lon0 + (lon1 - lon0) * anteil
    kurs = math.degrees(math.atan2(lon1 - lon0, lat1 - lat0)) % 360

    flug = dict(flug)
    flug["latitude"] = lat
    flug["longitude"] = lon
    flug["heading"] = int(kurs)
    flug["updated_at"] = jetzt.isoformat().replace("+00:00", "Z")
    flug["_fortschritt_km"] = fortschritt_km
    flug["_angekommen"] = anteil >= 1.0
    return flug


def advance_messeverkehr(conn, jetzt: datetime, echte_callsigns: set[str]) -> list[dict]:
    """Schreibt den simulierten Verkehr um einen Schritt fort und persistiert ihn.

    ``echte_callsigns`` sind die Rufzeichen des GERADE echten Verkehrs (aus
    ``get_live_positions``) — neue simulierte Flüge weichen ihnen aus.
    Gibt den neuen Bestand als Liste von Dicts zurück, ohne interne Zwischenfelder.
    """
    bestand = {f["cid"]: dict(f, _fortschritt_km=0.0) for f in get_messeverkehr_positions(conn)}

    aktualisiert: dict[int, dict] = {}
    for slot in range(ZIEL_ANZAHL_FLUEGE):
        cid = _CID_BASIS - slot
        vorher = bestand.get(cid)
        if vorher is None:
            aktualisiert[cid] = _neuer_flug(slot, jetzt, echte_callsigns)
            continue
        nachher = _fortschreiben(vorher, delta_s=15.0, jetzt=jetzt)
        if nachher.pop("_angekommen", False):
            aktualisiert[cid] = _neuer_flug(slot, jetzt, echte_callsigns)
        else:
            aktualisiert[cid] = nachher

    ergebnis = []
    for flug in aktualisiert.values():
        gespeichert = {k: v for k, v in flug.items() if not k.startswith("_")}
        ergebnis.append(gespeichert)

    replace_messeverkehr_positions(conn, ergebnis)
    return ergebnis
