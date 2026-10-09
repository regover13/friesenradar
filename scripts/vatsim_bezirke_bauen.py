#!/usr/bin/env python3
"""Baut ``app/data/vatsim_bezirke.json``: Rufzeichen-Anfang eines Center-Lotsen -> Name und Ort.

Quelle ist das VATSpy Data Project von VATSIM (https://github.com/vatsimnetwork/vatspy-data-project,
Lizenz CC BY-SA 4.0): ``VATSpy.dat`` nennt je Kontrollbezirk Name und Rufzeichen-Anfang,
``Boundaries.geojson`` den Punkt, an dem die Beschriftung des Bezirks steht. Genommen wird
immer der Punkt des ganzen Bezirks, nicht der eines Teilsektors: Ein Center-Lotse steht in
FriesenRadar mitten in seinem Bezirk (Nutzer 09.10.2026).

Aufruf:  python scripts/vatsim_bezirke_bauen.py VATSpy.dat Boundaries.geojson
Die beiden Dateien vorher von GitHub laden; das Ergebnis wird eingecheckt, zur Laufzeit holt
die App nichts.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ZIEL = Path(__file__).resolve().parents[1] / "app" / "data" / "vatsim_bezirke.json"

# Fehlt im Datensatz: die beiden oberen Bezirke über Deutschland. Ort = ungefähre Mitte.
VON_HAND = {
    "EDUU": ["Rhein", 49.6, 10.2],
    "EDYY": ["Maastricht", 52.0, 6.6],
}


def _abschnitte(pfad: Path) -> dict[str, list[list[str]]]:
    erg: dict[str, list[list[str]]] = {}
    name = None
    for zeile in pfad.read_text(encoding="utf-8", errors="replace").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith(";"):
            continue
        if zeile.startswith("["):
            name = zeile.strip("[]")
            erg[name] = []
        elif name:
            erg[name].append(zeile.split("|"))
    return erg


def _sauber(name: str) -> str:
    name = re.sub(r"\s*\(.*?\)", "", name)          # "(Up to FL245)"
    name = name.split(" - ")[0]                     # "Swiss Radar - Switzerland"
    return name.strip()


def bauen(dat: Path, grenzen: Path) -> dict[str, list]:
    teile = _abschnitte(dat)
    punkt = {}
    ozean = set()
    for f in json.loads(grenzen.read_text(encoding="utf-8"))["features"]:
        p = f["properties"]
        try:
            ort = (round(float(p["label_lat"]), 3), round(float(p["label_lon"]), 3))
        except (KeyError, TypeError, ValueError):
            continue
        # Ein Bezirk kann zwei Flächen haben, eine über Land und eine über dem Meer
        # (New York). Der Lotse gehört in die über Land.
        if str(p.get("oceanic")) == "1":
            ozean.add(p["id"])
            punkt.setdefault(p["id"], ort)
        else:
            punkt[p["id"]] = ort

    # Name des ganzen Bezirks: die Zeile, die für den Bezirk selbst steht.
    bezirksname: dict[str, str] = {}
    for t in teile.get("FIRs", []):
        if len(t) >= 4 and "-" not in t[0] and "_" not in t[0]:
            bezirksname.setdefault(t[0], _sauber(t[1]))

    erg: dict[str, list] = {}
    for t in teile.get("FIRs", []):
        if len(t) < 4:
            continue
        icao, name, anfang, grenze = t[0], t[1], t[2], t[3]
        basis = re.split(r"[-_]", icao)[0]
        ort = punkt.get(basis) or punkt.get(grenze)
        if ort is None:
            continue
        eintrag = [bezirksname.get(basis) or _sauber(name), ort[0], ort[1]]
        # Unter dem Rufzeichen-Anfang ("LON") UND unter dem Kürzel des Bezirks ("EGTT"):
        # Beides kommt als Anfang eines Rufzeichens vor. Der erste Eintrag gewinnt.
        for schluessel in {(anfang.split("_")[0] if anfang else basis).upper(), basis.upper()}:
            if schluessel:
                erg.setdefault(schluessel, eintrag)

    for t in teile.get("UIRs", []):
        if len(t) < 3:
            continue
        schluessel = t[0].split("_")[0].upper()
        orte = [punkt[x] for x in t[2].split(",") if x in punkt]
        if schluessel in erg or not orte:
            continue
        erg[schluessel] = [_sauber(t[1]), round(sum(o[0] for o in orte) / len(orte), 3),
                           round(sum(o[1] for o in orte) / len(orte), 3)]

    erg.update(VON_HAND)
    return dict(sorted(erg.items()))


if __name__ == "__main__":
    daten = bauen(Path(sys.argv[1]), Path(sys.argv[2]))
    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    ZIEL.write_text(json.dumps(
        {"quelle": "VATSpy Data Project, https://github.com/vatsimnetwork/vatspy-data-project, CC BY-SA 4.0",
         "bezirke": daten}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(len(daten), "Bezirke ->", ZIEL)
