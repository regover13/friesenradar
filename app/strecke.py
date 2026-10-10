# -*- coding: utf-8 -*-
"""Die Parameter einer Deichkontrolle: Strecke, Abschnitte, Höhengrenzen, Fenster.

Reine Rechnung, keine Datenbank -- wie ``app/reddung.py``. Die Abdeckung selbst rechnet
``app/abdeckung.py``; dieses Modul entscheidet, MIT WELCHEN Werten.

**„Deichkontrolle" ist nur der Name** (Nutzer, 10.10.2026). Abgeflogen wird eine frei in der
Verwaltung geklickte Strecke: eine Grenze, eine Küste, ein Fluss, ein Bergkamm. Nichts hier
hängt an Deichen, deshalb heißt der Eventtyp im Code ``strecke``.

**Die Strecke wird in gleich lange Abschnitte geteilt, jeder doppelt so lang wie der Korridor
breit ist** (nach jeder Seite). Ein Abschnitt gilt als abgeflogen, wenn eine Spur innerhalb des
Korridors an seinem MITTELPUNKT vorbeiläuft. Wer genau auf der Strecke fliegt, kommt an jedem
Mittelpunkt mit Abstand null vorbei; wer parallel im Abstand ``d`` fliegt, mit Abstand ``d``.
Die Länge ist bewusst kein eigener Regler -- zwei Zahlen für eine Sache laufen auseinander.

**Die Höhe zählt über der STRECKE, nicht unter dem Flugzeug** (Nutzer, 10.10.2026: „wie bei
Reddung"). Je Abschnitt steht die Geländehöhe aus dem Höhenmodell in ``grund_json``; die
Höchsthöhe eines Abschnitts ist Gelände plus ``hoehe_max_ft``, in Fuß über Meer. Damit zählt am
Bergkamm richtig, wer auf Kammhöhe seitlich über dem Tal fliegt -- die Höhe über Grund aus dem
Simulator misst dort den Talboden. Gerundet wird nicht: Anders als beim Wrack der Reddung gibt
es hier nichts zu verbergen.
"""
from __future__ import annotations

import json

from app.abdeckung import (
    Fenster, Ziel, _km_je_grad_lon, _strecke_km, abschnitt_anzahl, abschnitte_aus_linie,
)

VORGABE_KORRIDOR_M = 500.0
VORGABE_HOEHE_FT = 1000.0
VORGABE_GS_MAX_KT = 140.0
VORGABE_GS_MIN_KT = 30.0
#: Finden einer Fundstelle -- dieselben Vorgaben wie bei der Reddung.
VORGABE_FUND_RADIUS_M = 150.0
VORGABE_FUND_HOEHE_FT = 1000.0

#: Grenzen der Eingabe. 2.000 Abschnitte sind 20 Abrufe beim Höhenmodell (100 Punkte je Abruf,
#: gemessen am 10.10.2026) und bei 500 m Korridor 2.000 km Strecke.
PUNKTE_MIN = 2
PUNKTE_MAX = 500
ABSCHNITTE_MAX = 2000
KORRIDOR_MIN_M = 50.0
KORRIDOR_MAX_M = 10000.0

#: Präfix der Zielschlüssel: ``a0``, ``a1`` … in Reihenfolge der Strecke.
PRAEFIX = "a"


def _zahl(ev: dict, feld: str, vorgabe: float) -> float:
    wert = ev.get(feld)
    return float(wert) if wert is not None else float(vorgabe)


def punkte(ev: dict) -> list[tuple[float, float]]:
    """Die geklickten Punkte als ``[(lat, lon), …]``. Leer bei fehlender oder kaputter Angabe."""
    roh = ev.get("punkte_json")
    if isinstance(roh, str):
        try:
            roh = json.loads(roh)
        except ValueError:
            return []
    out: list[tuple[float, float]] = []
    for p in roh or []:
        try:
            out.append((float(p[0]), float(p[1])))
        except (TypeError, ValueError, IndexError):
            return []
    return out


def korridor_km(ev: dict) -> float:
    return _zahl(ev, "korridor_m", VORGABE_KORRIDOR_M) / 1000.0


def abschnitt_km(ev: dict) -> float:
    """Sollänge eines Abschnitts: das Doppelte des Korridors."""
    return 2.0 * korridor_km(ev)


def _kanten(pts: list[tuple[float, float]]):
    """``(kanten, gesamt_km)`` -- dieselbe ebene Rechnung wie ``abschnitte_aus_linie``."""
    if len(pts) < 2:
        return [], 0.0
    km_lon = _km_je_grad_lon(sum(p[0] for p in pts) / len(pts))
    kanten, gesamt = [], 0.0
    for a, b in zip(pts, pts[1:]):
        laenge = _strecke_km(a[0], a[1], b[0], b[1], km_lon)
        kanten.append((a, b, laenge))
        gesamt += laenge
    return kanten, gesamt


def laenge_km(ev: dict) -> float:
    return _kanten(punkte(ev))[1]


def teilung(ev: dict) -> tuple[int, float]:
    """``(Zahl der Abschnitte, Länge eines Abschnitts in km)`` -- 0 und 0.0 ohne Strecke."""
    gesamt = laenge_km(ev)
    if gesamt <= 0.0:
        return 0, 0.0
    anzahl = abschnitt_anzahl(gesamt, abschnitt_km(ev))
    return anzahl, gesamt / anzahl


def ziele(ev: dict) -> list[Ziel]:
    """Die Abschnitte als Kreisziele um ihre Mittelpunkte, Radius gleich Korridor."""
    return abschnitte_aus_linie(punkte(ev), abschnitt_km(ev), korridor_km(ev), PRAEFIX)


def schluessel(nr: int) -> str:
    return f"{PRAEFIX}{nr}"


def geometrie(ev: dict) -> list[list[list[float]]]:
    """Je Abschnitt sein Stück der Strecke als ``[[lat, lon], …]`` -- für die Karte.

    Anders als das Ziel (ein Mittelpunkt) folgt das Stück den Knicken der Strecke: Anfang, alle
    geklickten Punkte dazwischen, Ende.
    """
    pts = punkte(ev)
    kanten, gesamt = _kanten(pts)
    anzahl, schritt = teilung(ev)
    if not anzahl:
        return []
    # Laufende Kilometer an jedem geklickten Punkt.
    kum = [0.0]
    for _a, _b, laenge in kanten:
        kum.append(kum[-1] + laenge)

    def bei(km: float) -> list[float]:
        km = min(max(km, 0.0), gesamt)
        for i, (a, b, laenge) in enumerate(kanten):
            if km <= kum[i + 1] or i == len(kanten) - 1:
                t = ((km - kum[i]) / laenge) if laenge > 0 else 0.0
                t = min(max(t, 0.0), 1.0)
                return [round(a[0] + t * (b[0] - a[0]), 6), round(a[1] + t * (b[1] - a[1]), 6)]
        return [pts[-1][0], pts[-1][1]]

    stuecke = []
    for k in range(anzahl):
        von, bis = k * schritt, (k + 1) * schritt
        stueck = [bei(von)]
        for i in range(1, len(pts) - 1):
            if von < kum[i] < bis:
                stueck.append([round(pts[i][0], 6), round(pts[i][1], 6)])
        stueck.append(bei(bis))
        stuecke.append(stueck)
    return stuecke


def grund(ev: dict) -> list[float] | None:
    """Geländehöhe je Abschnitt (ft über Meer) -- ``None``, wenn sie fehlt oder nicht zur
    heutigen Teilung passt (Strecke oder Korridor geändert, noch nicht neu geholt)."""
    roh = ev.get("grund_json")
    if isinstance(roh, str):
        try:
            roh = json.loads(roh)
        except ValueError:
            return None
    if not isinstance(roh, list) or len(roh) != teilung(ev)[0] or not roh:
        return None
    try:
        return [float(x) for x in roh]
    except (TypeError, ValueError):
        return None


def hoehe_je_ziel(ev: dict) -> dict[str, float] | None:
    """Höchsthöhe je Abschnitt in Fuß über Meer: Gelände dort plus ``hoehe_max_ft``.

    ``None`` ohne Geländehöhen -- dann wird NICHT gerechnet (Spec A7), statt ohne Höhenprüfung
    zu werten.
    """
    g = grund(ev)
    if g is None:
        return None
    hoch = _zahl(ev, "hoehe_max_ft", VORGABE_HOEHE_FT)
    return {schluessel(i): h + hoch for i, h in enumerate(g)}


def fenster(ev: dict) -> Fenster:
    """Geschwindigkeit wie bei der Reddung; die Höhe steht je Ziel (``hoehe_je_ziel``)."""
    return Fenster(
        hoehe_max_ft=float("inf"),
        gs_max_kt=_zahl(ev, "gs_max_kt", VORGABE_GS_MAX_KT),
        gs_min_kt=_zahl(ev, "gs_min_kt", VORGABE_GS_MIN_KT),
    )


def fund_radius_km(ev: dict) -> float:
    return _zahl(ev, "fund_radius_m", VORGABE_FUND_RADIUS_M) / 1000.0


def fund_hoehe_ft(ev: dict) -> float:
    """So hoch über dem Gelände an der Fundstelle darf man beim Finden höchstens sein."""
    return _zahl(ev, "fund_hoehe_ft", VORGABE_FUND_HOEHE_FT)


def fenster_finden(ev: dict) -> Fenster:
    """Finden einer Fundstelle: dieselbe Höchstgeschwindigkeit wie beim Abfliegen, aber **ohne
    Untergrenze** -- wer über der Stelle schwebt, hat sie gefunden (bei der Reddung so
    entschieden am 25.09.2026). Die Höhe steht je Fundstelle (Gelände dort plus Fundhöhe)."""
    return Fenster(hoehe_max_ft=float("inf"),
                   gs_max_kt=_zahl(ev, "gs_max_kt", VORGABE_GS_MAX_KT), gs_min_kt=0.0)


def box(ev: dict) -> tuple[float, float, float, float] | None:
    """Das umschließende Rechteck der Strecke als ``(sued, west, nord, ost)``."""
    pts = punkte(ev)
    if not pts:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


def regeln(ev: dict) -> dict:
    """Die Vorgaben des Abends für die Anzeige -- dieselben Zahlen, mit denen gerechnet wird."""
    return {
        "korridor_m": _zahl(ev, "korridor_m", VORGABE_KORRIDOR_M),
        "hoehe_max_ft": _zahl(ev, "hoehe_max_ft", VORGABE_HOEHE_FT),
        "gs_max_kt": _zahl(ev, "gs_max_kt", VORGABE_GS_MAX_KT),
        "gs_min_kt": _zahl(ev, "gs_min_kt", VORGABE_GS_MIN_KT),
        "fund_radius_m": _zahl(ev, "fund_radius_m", VORGABE_FUND_RADIUS_M),
        "fund_hoehe_ft": fund_hoehe_ft(ev),
    }


def pruefen(pts, korridor_m) -> list[tuple[float, float]]:
    """Eingabe der Verwaltung prüfen. Gibt die Punkte zurück oder wirft ``ValueError`` mit
    einem Satz, der so in der Verwaltung stehen kann."""
    try:
        sauber = [(float(p[0]), float(p[1])) for p in pts]
    except (TypeError, ValueError, IndexError):
        raise ValueError("Die Strecke ist nicht lesbar.")
    if len(sauber) < PUNKTE_MIN:
        raise ValueError("Eine Strecke braucht mindestens zwei Punkte.")
    if len(sauber) > PUNKTE_MAX:
        raise ValueError(f"Höchstens {PUNKTE_MAX} Punkte je Strecke.")
    if any(not (-90.0 <= la <= 90.0 and -180.0 <= lo <= 180.0) for la, lo in sauber):
        raise ValueError("Ein Punkt der Strecke liegt außerhalb der Karte.")
    try:
        korr = float(korridor_m)
    except (TypeError, ValueError):
        raise ValueError("Der Korridor muss eine Zahl sein.")
    if not (KORRIDOR_MIN_M <= korr <= KORRIDOR_MAX_M):
        raise ValueError(f"Der Korridor muss zwischen {KORRIDOR_MIN_M:.0f} m und "
                         f"{KORRIDOR_MAX_M:.0f} m liegen.")
    ev = {"punkte_json": sauber, "korridor_m": korr}
    anzahl, _ = teilung(ev)
    if anzahl == 0:
        raise ValueError("Die Punkte der Strecke liegen alle an derselben Stelle.")
    if anzahl > ABSCHNITTE_MAX:
        raise ValueError(
            f"Das ergäbe {anzahl} Abschnitte, höchstens {ABSCHNITTE_MAX} sind möglich. "
            "Den Korridor vergrößern oder die Strecke kürzen.")
    return sauber
