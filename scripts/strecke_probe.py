#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eine Deichkontrolle zum Ansehen anlegen -- mit erfundenen Piloten, die Teile abgeflogen sind.

Für die Testinstanz und für lokale Probeläufe. Legt ein laufendes Event an (Beginn vor 20
Minuten, Ende in 3 Stunden), holt die Geländehöhen beim Höhenmodell und schreibt Sekundenpunkte
für vier erfundene Piloten nach ``bruegge_spur``:

* zwei fliegen sauber an der Strecke entlang,
* einer fliegt außerhalb des Korridors,
* einer fliegt zu hoch.

So sieht man in der Ansicht abgeflogene und offene Abschnitte und Piloten mit 0 km.

    python scripts/strecke_probe.py --db /daten/radar.db

⚠ **Nie gegen die echte Datenbank.** Das Skript schreibt erfundene Piloten und Positionen. Es
weigert sich bei einem Pfad unter ``/opt/friesenradar`` und bei ``friesenradar.db``.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import strecke as st                                              # noqa: E402
from app.database import (                                                 # noqa: E402
    create_strecken_event, get_connection, get_strecken_event, update_strecken_event,
)

# Eine Beispielstrecke, grob von Hand geklickt. Der Name sagt nichts über den Inhalt.
BEISPIEL = [[53.888, 9.146], [53.930, 9.200], [54.000, 9.270], [54.035, 9.290], [54.090, 9.300],
            [54.125, 9.335], [54.155, 9.420], [54.210, 9.530], [54.260, 9.620], [54.295, 9.665],
            [54.310, 9.720], [54.365, 9.820], [54.372, 9.950], [54.365, 10.030], [54.368, 10.140]]

#: (CID, Name, von/bis als Anteil der Strecke, Versatz in m, Höhe über der Strecke in ft)
PILOTEN = [
    (9000001, "Probe Anton", 0.00, 0.34, 120, 600),
    (9000002, "Probe Berta", 0.30, 0.55, -350, 800),
    (9000003, "Probe Cäsar", 0.62, 0.78, 1400, 700),       # außerhalb des Korridors
    (9000004, "Probe Dora", 0.82, 0.97, 100, 2600),        # zu hoch
]


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _hoehen(punkte: list[tuple[float, float]]) -> list[float]:
    """Geländehöhen in ft vom Höhenmodell, in Blöcken zu 100. Bei einem Fehler 0 ft überall --
    für eine Probe reicht das, und das Skript sagt es."""
    raus: list[float] = []
    try:
        for i in range(0, len(punkte), 100):
            teil = punkte[i:i + 100]
            url = ("https://api.open-meteo.com/v1/elevation?latitude="
                   + ",".join(f"{p[0]:.5f}" for p in teil)
                   + "&longitude=" + ",".join(f"{p[1]:.5f}" for p in teil))
            req = urllib.request.Request(url, headers={"User-Agent": "FriesenRadar/Probe"})
            with urllib.request.urlopen(req, timeout=10) as r:
                raus.extend(round(float(m) * 3.28084, 1) for m in json.load(r)["elevation"])
    except Exception as e:                                                  # noqa: BLE001
        print(f"Höhenmodell nicht erreicht ({e}) -- rechne mit 0 ft überall.")
        return [0.0] * len(punkte)
    return raus


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=os.environ.get("DB_PATH"), help="Pfad der Datenbank")
    ap.add_argument("--name", default="Deichkontrolle Probe")
    ap.add_argument("--korridor", type=float, default=500.0, help="Korridor in Metern")
    args = ap.parse_args()
    if not args.db:
        ap.error("--db fehlt (oder DB_PATH setzen)")
    pfad = os.path.realpath(args.db)
    if pfad.startswith("/opt/friesenradar") or os.path.basename(pfad) == "friesenradar.db":
        print("Abbruch: Das sieht nach der echten Datenbank aus. Dieses Skript schreibt "
              "erfundene Piloten und Positionen.", file=sys.stderr)
        return 2

    # Auf volle Minuten: Die Verwaltung kennt keine Sekunden, und ein Event mit Sekunden im
    # Beginn saehe dort bei jedem Speichern wie „Zeiten geaendert" aus.
    jetzt = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = jetzt - timedelta(minutes=20)
    st.pruefen(BEISPIEL, args.korridor)
    conn = get_connection(pfad)
    try:
        eid = create_strecken_event(conn, name=args.name, dtstart=_iso(start),
                                    dtend=_iso(jetzt + timedelta(hours=3)), punkte=BEISPIEL,
                                    korridor_m=args.korridor)
        conn.commit()
        ev = get_strecken_event(conn, eid)
    finally:
        conn.close()

    ziele = st.ziele(ev)
    grund = _hoehen([(z[1], z[2]) for z in ziele])

    # Die Strecke in 50-m-Schritten, mit seitlichem Versatz -- ein Punkt je Sekunde bei ~100 kt.
    pts = st.punkte(ev)
    lat0 = sum(p[0] for p in pts) / len(pts)
    km_lat, km_lon = 111.32, 111.32 * math.cos(math.radians(lat0))
    xy = [(p[1] * km_lon, p[0] * km_lat) for p in pts]
    kum = [0.0]
    for a, b in zip(xy, xy[1:]):
        kum.append(kum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    gesamt = kum[-1]

    def bei(km: float, versatz_km: float) -> tuple[float, float]:
        i = 1
        while i < len(kum) - 1 and kum[i] < km:
            i += 1
        a, b = xy[i - 1], xy[i]
        laenge = (kum[i] - kum[i - 1]) or 1.0
        t = (km - kum[i - 1]) / laenge
        dx, dy = (b[0] - a[0]) / laenge, (b[1] - a[1]) / laenge
        x = a[0] + (b[0] - a[0]) * t - dy * versatz_km
        y = a[1] + (b[1] - a[1]) * t + dx * versatz_km
        return y / km_lat, x / km_lon

    anzahl, schritt = st.teilung(ev)
    conn = get_connection(pfad)
    try:
        update_strecken_event(conn, eid, grund_json=json.dumps(grund), grund_geholt_am=_iso(jetzt))
        for cid, name, von, bis, versatz_m, ueber_ft in PILOTEN:
            conn.execute("INSERT OR IGNORE INTO pilots (cid, name, added_at) VALUES (?, ?, ?)",
                         (cid, name, _iso(jetzt)))
            km, t = von * gesamt, start + timedelta(seconds=30)
            while km <= bis * gesamt:
                lat, lon = bei(km, versatz_m / 1000.0)
                nr = min(int(km / schritt), anzahl - 1)
                conn.execute(
                    "INSERT OR REPLACE INTO bruegge_spur (cid, ts, lat, lon, alt_msl_ft, gs_kt) "
                    "VALUES (?, ?, ?, ?, ?, 100)",
                    (cid, _iso(t), lat, lon, grund[nr] + ueber_ft))
                km += 0.05
                t += timedelta(seconds=1)
        conn.commit()
    finally:
        conn.close()
    print(f"Event {eid} „{args.name}“ angelegt: {gesamt:.1f} km, {anzahl} Abschnitte, "
          f"vier erfundene Piloten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
