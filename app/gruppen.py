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
    try:
        m_min, m_max = int(menge_min), int(menge_max)
    except (TypeError, ValueError):
        raise ValueError("Die Menge muss eine ganze Zahl sein.")
    if m_min < 1:
        raise ValueError("Eine Gruppe braucht mindestens ein Objekt.")
    if m_max < m_min:
        raise ValueError("Die Höchstmenge darf nicht unter der Mindestmenge liegen.")
    if m_max > MENGE_MAX:
        raise ValueError(f"Höchstens {MENGE_MAX} Objekte je Gruppe.")
    try:
        a_min, a_max = float(abstand_min_m), float(abstand_max_m)
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
            kurs = float(richtung) % 360.0
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
            # Dicht gepackt: von der Mitte nach außen gehen, bis Platz ist. Endet immer.
            winkel = wuerfel.uniform(0.0, 2.0 * math.pi)
            weit = a_max
            while not frei(weit * math.sin(winkel), weit * math.cos(winkel)):
                weit += a_min
            orte.append((weit * math.sin(winkel), weit * math.cos(winkel)))

    m_je_grad_lon = _M_JE_GRAD * max(math.cos(math.radians(float(lat))), 0.01)
    raus = []
    for x, y in orte:
        kurs = kurs_fest if kurs_fest is not None else wuerfel.uniform(0.0, 360.0)
        raus.append({"lat": round(float(lat) + y / _M_JE_GRAD, 7),
                     "lon": round(float(lon) + x / m_je_grad_lon, 7),
                     "kurs": round(kurs, 1)})
    return raus
