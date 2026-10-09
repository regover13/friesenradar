"""ICAO-Typkürzel → Mustername, aus der Liste der ICAO (Doc 8643).

Wozu: Die Muster-Recherche (Wikipedia-Text, Foto) sucht nach einem NAMEN, nicht nach dem
Kürzel. Bis 16.4.0 kam der Name ausschließlich aus der Zuladungs-Recherche (Haiku mit
Websuche). Ging die leer aus, blieb das Muster 30 Tage ohne Namen, Text und Foto — auch wenn
das Kürzel ein ganz gewöhnliches war (P28U am 09.10.2026, P28R am 01.10.2026).

Nachgemessen am 09.10.2026 mit zwölf Probeläufen: Haiku muss das Muster aus dem nackten
Kürzel erraten. Gelingt das nicht, zwingt das JSON-Schema es trotzdem zu einer Antwort, und
die besteht dann aus lauter Nullen („unplausible Werte“ → ``None`` → ``nichts_gefunden``).
Gelingt es scheinbar, ist es teils falsch („Pitcairn PA-34“ für P34A). Die Liste der ICAO
beantwortet die Frage „welches Muster ist das?“ ohne Raten.

Die Liste liegt NICHT im Repo: Sie gehört der ICAO, und das Repo ist öffentlich. Sie wird
einmal geholt, neben der Datenbank abgelegt und alle 30 Tage aufgefrischt. Fehlt sie (erster
Start, ICAO nicht erreichbar), verhält sich alles wie vorher — der Name kommt dann wieder nur
aus der Zuladungs-Recherche.

⚠ Ein Kürzel, das hier fehlt, ist nicht zwingend ein Tippfehler des Piloten, aber fast immer
eine Eingabe außerhalb der ICAO-Liste („P34A“ statt PA34, „CH47“ statt H47). Daraus
folgt hier nichts: Solche Kürzel laufen weiter über die Zuladungs-Recherche.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

QUELLE_URL = "https://doc8643.icao.int/external/aircrafttypes"
DATEINAME = "icao_typen.json"
#: So lange gilt eine abgelegte Liste. Die ICAO ändert sie wenige Male im Jahr.
HALTBARKEIT_S = 30 * 24 * 3600
#: Mehr Varianten als diese nennt der Hinweis an die Zuladungs-Recherche nicht.
_HINWEIS_MAX = 4

# {kuerzel: [(hersteller, modell), ...]} in der Reihenfolge der ICAO-Liste.
_typen: dict[str, list[tuple[str, str]]] = {}
# Wie oft ein Hersteller in der GANZEN Liste steht — entscheidet, wessen Name gilt.
_hersteller_gewicht: Counter = Counter()


def aus_rohdaten(roh) -> dict[str, list[list[str]]]:
    """Die Antwort der ICAO auf das eindampfen, was gebraucht wird.

    Unbrauchbare Zeilen fallen still weg; doppelte (Hersteller, Modell) je Kürzel ebenfalls.
    """
    aus: dict[str, list[list[str]]] = {}
    if not isinstance(roh, list):
        return aus
    for zeile in roh:
        if not isinstance(zeile, dict):
            continue
        code = str(zeile.get("Designator") or "").strip().upper()
        hersteller = " ".join(str(zeile.get("ManufacturerCode") or "").split())
        modell = " ".join(str(zeile.get("ModelFullName") or "").split())
        if not code or not modell:
            continue
        eintrag = [hersteller, modell]
        liste = aus.setdefault(code, [])
        if eintrag not in liste:
            liste.append(eintrag)
    return aus


def setzen(typen: dict) -> None:
    """Die Liste im Speicher ersetzen (App-Start, nach dem Auffrischen, Tests)."""
    neu: dict[str, list[tuple[str, str]]] = {}
    gewicht: Counter = Counter()
    for code, eintraege in (typen or {}).items():
        sauber = [
            (str(e[0]), str(e[1])) for e in eintraege or []
            if isinstance(e, (list, tuple)) and len(e) == 2 and e[1]
        ]
        if not sauber:
            continue
        neu[str(code).strip().upper()] = sauber
        gewicht.update(h for h, _ in sauber)
    # Umbinden statt leeren und füllen: Das Auffrischen läuft in einem Thread, die
    # Muster-Recherche liest derweil. Ein Leser, der die Liste mitten im Tausch leer sähe,
    # schriebe für ein bekanntes Kürzel „nichts gefunden“ und sperrte es 30 Tage.
    global _typen, _hersteller_gewicht
    _typen, _hersteller_gewicht = neu, gewicht


def anzahl() -> int:
    return len(_typen)


def bekannt(code: str | None) -> bool:
    return (code or "").strip().upper() in _typen


#: Herstellernamen, die Abkürzungen sind und groß bleiben.
_ABKUERZUNGEN = frozenset({"PZL", "BAE", "IAI", "HAL", "WSK", "ATR", "AMD", "CASA", "SIAI"})


def _wort(teil: str) -> str:
    if teil in _ABKUERZUNGEN:
        return teil
    if teil.startswith("MC") and len(teil) > 3:
        return "Mc" + teil[2:].capitalize()
    return teil.capitalize()


def _hersteller_schreibweise(hersteller: str) -> str:
    """„PIPER“ → „Piper“, „PZL-OKECIE“ → „PZL-Okecie“, „MCDONNELL DOUGLAS“ → „McDonnell Douglas“."""
    return " ".join("-".join(_wort(t) for t in w.split("-")) for w in hersteller.split(" "))


_KUERZEL_TEILE = re.compile(r"^([A-Z]*)(\d+)")


def _modell_passt(code: str, modell: str) -> int:
    """Wie gut passt ein Modellname zum Kürzel? 2 = Buchstaben und Zahl, 1 = Zahl, 0 = nichts.

    Die ICAO führt je Kürzel auch militärische und fremde Bezeichnungen, und die stehen oft
    vorn: PC21 beginnt mit „E-27“, EC35 mit „HE-26“, DHC6 mit „CC-138 Twin Otter“. Gemessen am
    09.10.2026 führte genau das zu falschen Artikeln (DHC6 → Dash 7, DV20 → D-Jet). Der Name,
    aus dem das Kürzel gebildet wurde, trägt dessen Zahl: „PC-21“, „EC-135“, „DHC-6“.
    """
    m = _KUERZEL_TEILE.match(code)
    if not m:
        return 0
    buchstaben, zahl = m.groups()
    woerter = [re.sub(r"[^A-Z0-9]", "", w) for w in modell.upper().split()]
    # Am WORTANFANG, nicht irgendwo: Sonst gewinnt bei C208 die „AC-208“ (Kampfversion) vor
    # der „208 Caravan“, bei UH1 die „CUH-1H“ und bei C337 die „MC337“.
    if buchstaben and any(w.startswith(buchstaben + zahl) for w in woerter):
        return 2
    if any(w.startswith(zahl) for w in woerter):
        return 2          # „208 Caravan“, „228“, „337 Super Skymaster“
    return 1 if any(zahl in w for w in woerter) else 0


def _eintraege_sortiert(code: str) -> list[tuple[str, str]]:
    """Die Einträge eines Kürzels, der treffendste zuerst.

    Ein Kürzel steht oft bei mehreren Herstellern (P28U: Piper, dazu die Lizenzbauer AICSA,
    Chincul, Embraer, Neiva) und unter mehreren Modellnamen. Der Reihe nach entscheidet:

    1. der Modellname, der die Zahl des Kürzels trägt (``_modell_passt``),
    2. der Hersteller, dessen Name mit dem Buchstaben des Kürzels beginnt (D228 → Dornier,
       nicht Hindustan; BN2P → Britten-Norman, nicht Avions Fairey),
    3. der Hersteller, der in der ganzen Liste am häufigsten steht,
    4. die Reihenfolge der ICAO.
    """
    code = (code or "").strip().upper()
    eintraege = _typen.get(code) or []
    return sorted(
        eintraege,
        key=lambda e: (
            -_modell_passt(code, e[1]),
            0 if e[0][:1] == code[:1] else 1,
            -_hersteller_gewicht[e[0]],
        ),
    )


def name_fuer(code: str | None) -> str | None:
    """Ein Name für das Kürzel, mit dem sich Wikipedia fragen lässt — oder ``None``."""
    eintraege = _eintraege_sortiert(code or "")
    if not eintraege:
        return None
    hersteller, modell = eintraege[0]
    hersteller = _hersteller_schreibweise(hersteller)
    # „DORNIER“ + „Dornier 228“ soll nicht „Dornier Dornier 228“ ergeben.
    if hersteller and not modell.lower().startswith(hersteller.lower()):
        return f"{hersteller} {modell}"
    return modell


def suchbegriff(code: str | None) -> tuple[str, str] | None:
    """(Hersteller, Modellbezeichnung) für die Fotosuche — oder ``None``.

    Die Modellbezeichnung ist das erste Wort des Modellnamens, das eine Ziffer trägt:
    „PA-28RT-201T“ aus „PA-28RT-201T Turbo Arrow 4“, „PC-21“, „228“. Der Rest des Namens
    taugt für die Suche nicht — die ICAO schreibt „Turbo Arrow 4“, Commons „Turbo Arrow IV“.
    """
    eintraege = _eintraege_sortiert(code or "")
    if not eintraege:
        return None
    hersteller, modell = eintraege[0]
    for wort in modell.split():
        if any(z.isdigit() for z in wort):
            return _hersteller_schreibweise(hersteller), wort
    return None


def titel_passt(code: str | None, titel: str | None) -> bool:
    """Trägt der Artikeltitel die Zahl des Kürzels?

    P28U → „Piper PA-28“ (28), C82R → „Cessna 182 Skylane“ (182 endet auf 82), DR40 →
    „Robin DR 400“ (400 beginnt mit 40). Dagegen BE60 → „Beech Aircraft Corporation“ und
    UH1 → „Bell 212“: verworfen. Preis: Ein richtiger Artikel ohne Zahl im Titel
    („Beechcraft Baron“ für BE58) fällt ebenfalls durch, ebenso einer, dessen Kürzel eine
    Ziffer für die Variante trägt (B738 → „Boeing 737 Next Generation“, A359 → „Airbus A350“).
    Für diese Muster bleibt es wie vor 16.4.1; der Name lässt sich im Admin setzen. Ein Kürzel ohne Zahl (AEST) lässt sich so nicht prüfen und gilt als passend.
    """
    m = _KUERZEL_TEILE.match((code or "").strip().upper())
    if not m:
        return True
    zahl = m.group(2)
    return any(
        z.startswith(zahl) or z.endswith(zahl) for z in re.findall(r"\d+", titel or "")
    )


def hinweis_fuer(code: str | None) -> str:
    """Klartext für den Prompt der Zuladungs-Recherche; leer, wenn das Kürzel fehlt."""
    eintraege = _eintraege_sortiert(code or "")
    if not eintraege:
        return ""
    namen: list[str] = []
    for hersteller, modell in eintraege:
        name = f"{_hersteller_schreibweise(hersteller)} {modell}".strip()
        if name not in namen:
            namen.append(name)
        if len(namen) >= _HINWEIS_MAX:
            break
    return "laut ICAO Doc 8643: " + "; ".join(namen)


def _pfad(daten_dir: str | os.PathLike) -> Path:
    return Path(daten_dir) / DATEINAME


def laden(daten_dir: str | os.PathLike) -> int:
    """Die abgelegte Liste in den Speicher holen. Rückgabe: Anzahl Kürzel (0 = keine Datei)."""
    try:
        with open(_pfad(daten_dir), encoding="utf-8") as f:
            daten = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0
    typen = daten.get("typen") if isinstance(daten, dict) else None
    if not isinstance(typen, dict):
        return 0
    setzen(typen)
    return anzahl()


def faellig(daten_dir: str | os.PathLike, jetzt_s: float | None = None) -> bool:
    """Fehlt die Datei oder ist sie älter als ``HALTBARKEIT_S``?"""
    try:
        alter = (time.time() if jetzt_s is None else jetzt_s) - _pfad(daten_dir).stat().st_mtime
    except OSError:
        return True
    return alter >= HALTBARKEIT_S


def _holen() -> object:
    """Die Liste bei der ICAO abrufen. Ein POST ohne Inhalt, so verlangt es die Seite."""
    import httpx
    antwort = httpx.post(
        QUELLE_URL, content=b"", timeout=60.0, follow_redirects=True,
        headers={"User-Agent": "FriesenRadar/1.0 (+https://radar.friesenflieger.de)"},
    )
    antwort.raise_for_status()
    return antwort.json()


def auffrischen(daten_dir: str | os.PathLike, holen=None) -> int:
    """Liste holen, ablegen und in den Speicher nehmen. Rückgabe: Anzahl Kürzel.

    Eine leere oder unlesbare Antwort überschreibt NIE eine vorhandene Datei — sonst machte
    ein schlechter Tag der ICAO aus einer brauchbaren Liste gar keine. Wirft, wenn der Abruf
    scheitert; der Aufrufer protokolliert und versucht es beim nächsten Lauf wieder.
    """
    typen = aus_rohdaten((holen or _holen)())
    if len(typen) < 500:
        raise ValueError(f"ICAO-Liste unbrauchbar: nur {len(typen)} Kürzel")
    ziel = _pfad(daten_dir)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    vorlaeufig = ziel.with_suffix(".tmp")
    with open(vorlaeufig, "w", encoding="utf-8") as f:
        json.dump({"quelle": QUELLE_URL, "typen": typen}, f, ensure_ascii=False)
    os.replace(vorlaeufig, ziel)
    setzen(typen)
    return anzahl()
