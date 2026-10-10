# -*- coding: utf-8 -*-
"""Eine Gruppe von Objekten um einen Ort streuen -- eine Kolonie, nicht Reih und Glied.

Reine Rechnung, keine Datenbank, **eventunabhängig**. Gebaut für die Fundstellen der
Deichkontrolle (#22), gedacht auch für die Kolonien des FriesenKiekers (#20) und, mit einem
Objekt je Gruppe, für die Stationen der FriesenBaake (#24). Wer die Lage braucht, ruft
``streuen`` und legt das Ergebnis selbst ab; wann ein Objekt an den Simulator geht, entscheidet
der Aufrufer (heute „erst aus der Nähe“, bei der Baake später „erst nach der vorigen Station“).

**Wiederholbar:** Derselbe Startwert ergibt dieselbe Lage, auf jedem Rechner und in jeder
Python-Fassung -- der Startwert geht als Zeichenkette in ``random.Random``, und das rechnet
daraus über SHA-512 seinen Zustand. Ein Startwert je Pilot ergäbe je Pilot eine eigene Lage.

**Die gewürfelte Zahl ist ``len(streuen(...))``** und gehört vom Aufrufer gespeichert: Der
Kieker wertet später die Schätzung des Piloten dagegen.

So entsteht die Lage: Das erste Objekt steht in der Mitte. Jedes weitere hängt sich in einer
gewürfelten Richtung und einem gewürfelten Abstand (zwischen Mindest- und Höchstabstand) an ein
schon gesetztes -- so wächst ein Haufen mit Lücken und Ausläufern statt eines Rings. Näher als
der Mindestabstand kommt keines einem anderen.
"""
from __future__ import annotations

import math
import random
import secrets

#: Grenzen der Eingabe. 60 Objekte je Gruppe sind viel für eine Stelle, und ``bruegge_soll``
#: fasst insgesamt 200.
MENGE_MAX = 60
ABSTAND_MIN_M = 1.0
ABSTAND_MAX_M = 2000.0

#: So oft wird für ein Objekt ein Platz gewürfelt, bevor es an den Rand ausweicht.
_VERSUCHE = 40

_M_JE_GRAD = 111_320.0


def startwert() -> str:
    """Ein frischer Startwert -- für „neu würfeln“."""
    return secrets.token_hex(6)


def pruefen(menge_min, menge_max, abstand_min_m, abstand_max_m,
            richtung=None) -> tuple[int, int, float, float, float | None]:
    """Die Angaben einer Gruppe prüfen. Gibt sie bereinigt zurück oder wirft ``ValueError`` mit
    einem Satz, der so in der Verwaltung stehen kann."""
    # ⚠ Jede Zahl auf Endlichkeit pruefen: Mit NaN ist jeder Vergleich falsch, die Grenzen
    # griffen nicht, und ``streuen`` faende nie einen freien Platz -- eine Endlosschleife in der
    # Event-Loop (Befund der Pruefung vom 10.10.2026).
    try:
        f_min, f_max = float(menge_min), float(menge_max)
        if not (math.isfinite(f_min) and math.isfinite(f_max)
                and f_min.is_integer() and f_max.is_integer()):
            raise ValueError
        m_min, m_max = int(f_min), int(f_max)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Die Menge muss eine ganze Zahl sein.")
    if m_min < 1:
        raise ValueError("Eine Gruppe braucht mindestens ein Objekt.")
    if m_max < m_min:
        raise ValueError("Die Höchstmenge darf nicht unter der Mindestmenge liegen.")
    if m_max > MENGE_MAX:
        raise ValueError(f"Höchstens {MENGE_MAX} Objekte je Gruppe.")
    try:
        a_min, a_max = float(abstand_min_m), float(abstand_max_m)
        if not (math.isfinite(a_min) and math.isfinite(a_max)):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Der Abstand muss eine Zahl sein.")
    if not (ABSTAND_MIN_M <= a_min <= ABSTAND_MAX_M):
        raise ValueError(f"Der Mindestabstand muss zwischen {ABSTAND_MIN_M:g} m und "
                         f"{ABSTAND_MAX_M:g} m liegen.")
    if a_max < a_min:
        raise ValueError("Der Höchstabstand darf nicht unter dem Mindestabstand liegen.")
    if a_max > ABSTAND_MAX_M:
        raise ValueError(f"Der Höchstabstand darf höchstens {ABSTAND_MAX_M:g} m sein.")
    kurs = None
    if richtung is not None and richtung != "":
        try:
            kurs = float(richtung)
            if not math.isfinite(kurs):
                raise ValueError
            kurs %= 360.0
        except (TypeError, ValueError):
            raise ValueError("Die Richtung muss eine Zahl in Grad sein.")
    return m_min, m_max, a_min, a_max, kurs


def streuen(lat: float, lon: float, menge_min: int, menge_max: int,
            abstand_min_m: float, abstand_max_m: float, seed,
            richtung: float | None = None) -> list[dict]:
    """Die Lage einer Gruppe: ``[{"lat", "lon", "kurs"}, …]``, das erste Objekt in der Mitte.

    ``richtung`` ist die Blickrichtung aller Objekte in Grad; ohne Angabe wird sie je Objekt
    gewürfelt (Robben liegen kreuz und quer, ein Pfeil zeigt in eine Richtung).
    """
    m_min, m_max, a_min, a_max, kurs_fest = pruefen(
        menge_min, menge_max, abstand_min_m, abstand_max_m, richtung)
    try:
        lat, lon = float(lat), float(lon)
        if not (math.isfinite(lat) and math.isfinite(lon)):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("Der Ort ist nicht lesbar.")
    wuerfel = random.Random(str(seed))
    menge = wuerfel.randint(m_min, m_max)

    # In Metern um die Mitte rechnen (x nach Osten, y nach Norden), am Ende in Grad.
    orte: list[tuple[float, float]] = [(0.0, 0.0)]

    def frei(x: float, y: float) -> bool:
        # Ein Hauch Toleranz: Der gewürfelte Abstand zum Anker darf genau der Mindestabstand sein.
        return all(math.hypot(x - ox, y - oy) >= a_min - 1e-9 for ox, oy in orte)

    while len(orte) < menge:
        gesetzt = False
        for _ in range(_VERSUCHE):
            ax, ay = orte[wuerfel.randrange(len(orte))]
            winkel = wuerfel.uniform(0.0, 2.0 * math.pi)
            weit = wuerfel.uniform(a_min, a_max)
            x, y = ax + weit * math.sin(winkel), ay + weit * math.cos(winkel)
            if frei(x, y):
                orte.append((x, y))
                gesetzt = True
                break
        if not gesetzt:
            # Dicht gepackt: an den Rand der Gruppe hängen. In einer gewürfelten Richtung das
            # ÄUSSERSTE Objekt nehmen und von ihm aus weiter in dieselbe Richtung gehen -- alle
            # anderen liegen dann dahinter, also mindestens so weit weg wie der Schritt selbst.
            # So bleibt beides gewahrt: nie näher als der Mindestabstand, und nie weiter als
            # der Höchstabstand vom nächsten Objekt.
            winkel = wuerfel.uniform(0.0, 2.0 * math.pi)
            ux, uy = math.sin(winkel), math.cos(winkel)
            ax, ay = max(orte, key=lambda o: o[0] * ux + o[1] * uy)
            weit = wuerfel.uniform(a_min, a_max)
            orte.append((ax + weit * ux, ay + weit * uy))

    m_je_grad_lon = _M_JE_GRAD * max(math.cos(math.radians(float(lat))), 0.01)
    raus = []
    for x, y in orte:
        kurs = kurs_fest if kurs_fest is not None else wuerfel.uniform(0.0, 360.0)
        # Auf der Karte bleiben: am Pol kappen, an der Datumsgrenze umlaufen.
        o_lat = min(max(float(lat) + y / _M_JE_GRAD, -90.0), 90.0)
        o_lon = (float(lon) + x / m_je_grad_lon + 180.0) % 360.0 - 180.0
        raus.append({"lat": round(o_lat, 7), "lon": round(o_lon, 7), "kurs": round(kurs, 1)})
    return raus
