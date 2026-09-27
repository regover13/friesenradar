"""Generator fuer simulierten Friesen-Verkehr auf der Live-Karte (Messestand-Modus).

Spielt echte, abgeschlossene Fluege aus der Vergangenheit (``flights`` + ``position_history``)
unter erfundener Identitaet ab, zeitlich auf "jetzt" verschoben -- die Bewegung, Hoehe,
Geschwindigkeit und Flugplan-Daten kommen damit automatisch aus echten Aufzeichnungen statt
aus einer nachgebauten Physik. Schreibt in eine eigene, von echten Live-Daten komplett
getrennte Tabelle. Siehe docs/superpowers/specs/2026-09-27-messeverkehr-design.md.

Nutzerkorrektur 27.09.2026, nachdem die erste (rein synthetische) Fassung live zu sehen war:
alle drei Fluege bei exakt derselben Hoehe/Geschwindigkeit/Flugzeugtyp, nicht auf Strecken, die
die Gruppe tatsaechlich fliegt, alle Callsigns im festen Muster FRS8xx, alle gleichzeitig
"online" -- vier eigene Tells. Diese Fassung ersetzt die alte Punkt-zu-Punkt-Interpolation.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from app.database import get_messeverkehr_positions, replace_messeverkehr_positions

ZIEL_ANZAHL_FLUEGE = 3  # Fallback, falls (aus welchem Grund auch immer) kein Bereich lesbar ist
_MAX_SLOTS = 10  # feste Obergrenze fuer den CID-Bereich, unabhaengig vom admin-Bereich
_CID_BASIS = -900000
_MIN_FLUGDAUER_MIN = 15
_MAX_FLUGDAUER_MIN = 90
_CALLSIGN_MIN = 10   # keine einstelligen -- wirken wie alte Gruendungsmitglieder-Callsigns
_CALLSIGN_MAX = 299  # keine vierstelligen -- bei FRS-Callsigns unueblich
_N_SUFFIX_ANTEIL = 0.25  # "Neu-Friese"-Kennung, ab und zu, nicht immer (Nutzerwunsch 27.09.2026)
# Plausibilitaets-Grenzen fuer die Anzeige (Nutzerfund 27.09.2026: 7.295.605 ft/129.601 kt
# wurden einmal ausgeliefert -- Ursache ungeklaert, siehe _position_bei). Kleine Flugzeuge in
# unseren Aufzeichnungen fliegen nie ueber FL450 oder 500 kt; grosszuegig genug, um echte
# Werte nie zu beschneiden, eng genug, um jede Art von Ausreisser abzufangen.
_MAX_PLAUSIBLE_ALTITUDE_FT = 45000
_MAX_PLAUSIBLE_GROUNDSPEED_KT = 500

# Interne Buchhaltung (welcher echte Flug wird gerade abgespielt) -- verlaesst den Server nie,
# siehe messeverkehr_fuer_anzeige() und _live_positions_mit_messeverkehr() in app/poller.py.
_INTERNE_REPLAY_SPALTEN = ("quelle_flight_id", "quelle_cid", "quelle_logon_time",
                           "quelle_logoff_time")


def _synthetischer_pilotenname(slot: int) -> str:
    """Name im selben Muster wie echte FriesenSpy-Piloten: (Vor-/voller Name) + Heimatflugplatz
    (ICAO) am Ende, z.B. "Tobias EDKB" -- Nutzerfund 27.09.2026 (Screenshot der Live-Liste):
    OHNE den Platz fielen die erfundenen Namen sofort auf. Manchmal nur Vorname, wie im echten
    Vorbild auch. Namen bewusst anders gewaehlt als real bekannte Vereinsmitglieder."""
    piloten = [
        ("Jan", "EDXW"),
        ("Frauke Boysen", "EDHL"),
        ("Karsten", "EDXR"),
        ("Insa Cornelsen", "EDHF"),
        ("Gerrit", "EDVE"),
    ]
    name, heimat = piloten[slot % len(piloten)]
    return f"{name} {heimat}"


def bekannte_echte_callsigns(conn) -> set[str]:
    """Alle Callsigns, die FriesenSpy je einem echten Piloten zugeordnet hat.

    Quelle: flights/live_positions/statsim_cache (alles, was seit FriesenSpy laeuft geflogen
    ist) plus forum_callsign (jeder, der sich je per Forum-SSO angemeldet hat). NICHT
    vollstaendig: Ein Mitglied, das sein Callsign nur im Forum reserviert hat, ohne je zu
    fliegen oder sich bei FriesenSpy einzuloggen, fehlt hier -- bestmoegliche automatische
    Quelle, bis eine autoritativere (volle Forum-Mitgliederliste) vorliegt.
    """
    ergebnis: set[str] = set()
    for tabelle in ("flights", "live_positions", "statsim_cache"):
        for row in conn.execute(
            f"SELECT DISTINCT UPPER(callsign) AS cs FROM {tabelle} WHERE callsign IS NOT NULL"
        ):
            if row["cs"]:
                ergebnis.add(row["cs"])
    for row in conn.execute("SELECT callsign FROM forum_callsign"):
        if row["callsign"]:
            ergebnis.add(row["callsign"].upper())
    for row in conn.execute("SELECT callsign FROM messeverkehr_ausschluss_callsigns"):
        if row["callsign"]:
            ergebnis.add(row["callsign"].upper())
    return ergebnis


def _freies_callsign(belegt: set[str]) -> str:
    """Zufaellige FRS-Nummer aus einer breiten Spanne, zwei- bis dreistellig, ab und zu mit
    'N'-Endung (Neu-Friese-Kennung). Ein festes Zahlenmuster (frueher: 800 + slot*10) sah
    selbst wie eine Kennzeichnung aus (Nutzerfund 27.09.2026)."""
    for _ in range(30):
        nummer = random.randint(_CALLSIGN_MIN, _CALLSIGN_MAX)
        suffix = "N" if random.random() < _N_SUFFIX_ANTEIL else ""
        kandidat = f"FRS{nummer}{suffix}"
        if kandidat not in belegt:
            return kandidat
    n = 1
    while f"FRSX{n}" in belegt:
        n += 1
    return f"FRSX{n}"


def _als_datetime(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _historischen_flug_waehlen(conn) -> dict | None:
    """Waehlt zufaellig einen abgeschlossenen, echten Flug mit brauchbarem Track (mind. zwei
    aufgezeichnete Positionen). Nur deutsche Strecken (ICAO-Praefix "ED" bei Start UND Ziel) --
    Nutzerwunsch 27.09.2026, nachdem eine internationale Strecke (Florida) auftauchte."""
    for _ in range(10):
        row = conn.execute(
            "SELECT id, cid, aircraft_short, aircraft_icao, departure, arrival, route, "
            "       flight_rules, cruise_tas, alternate, deptime, enroute_time, fuel_time, "
            "       logon_time, logoff_time "
            "FROM flights "
            "WHERE logon_time IS NOT NULL AND logoff_time IS NOT NULL "
            "  AND departure LIKE 'ED%' AND arrival LIKE 'ED%' "
            "  AND duration_min BETWEEN ? AND ? "
            "ORDER BY RANDOM() LIMIT 1",
            (_MIN_FLUGDAUER_MIN, _MAX_FLUGDAUER_MIN),
        ).fetchone()
        if row is None:
            return None
        flug = dict(row)
        anzahl = conn.execute(
            "SELECT COUNT(*) FROM position_history WHERE cid = ? AND ts >= ? AND ts <= ?",
            (flug["cid"], flug["logon_time"], flug["logoff_time"]),
        ).fetchone()[0]
        if anzahl >= 2:
            return flug
    return None


def _position_bei(conn, quelle_cid: int, zeitpunkt: datetime,
                  fenster_von: str, fenster_bis: str) -> dict | None:
    """Interpolierte Position aus position_history zum gegebenen Zeitpunkt -- AUSSCHLIESSLICH
    innerhalb von [fenster_von, fenster_bis] (des gewaehlten Quellflugs).

    PRODUKTIONSVORFALL 27.09.2026: Ohne diese Fensterung suchte die Funktion in der GESAMTEN
    Positionshistorie eines Piloten. Bei einer Aufzeichnungsluecke im gewaehlten Flug griff
    sie in einen zeitlich weit entfernten, voellig anderen Flug DESSELBEN Piloten -- ein
    simulierter Flug sprang dadurch binnen einem Zyklus quer über den Globus (Nutzerfund:
    "FRS122 ist mal schnell von Florida an die Elfenbeinkueste"). Die Fensterung macht das
    strukturell unmoeglich: Ausserhalb des Fensters gibt es keinen Bezugspunkt mehr, und die
    Funktion liefert None ("angekommen") statt eines Sprungs.

    None nur, wenn KEIN Punkt mehr bis ``fenster_bis`` folgt (Flug "angekommen"). Liegt der
    Zeitpunkt VOR dem ersten aufgezeichneten Punkt -- der Normalfall fuer Slot 0 beim Kopfstart
    (Nutzerfund 27.09.2026, Fable-Review: virtueller Start == quelle_logon, der reale erste
    Track-Punkt liegt aber immer etwas SPAETER als logon_time, weil er erst beim naechsten
    Poll-Zyklus entsteht) --, wird auf den ersten bekannten Punkt eingefroren, statt None zu
    liefern: Ohne diese Abfangung kaeme Slot 0 nie zustande, und dasselbe traf schon vorher
    jede Nachbesetzung (dort war vorsprung_sek ebenfalls immer 0.0).

    Der Kurs wird NICHT interpoliert (zirkulaer -- 350->10 Grad waere sonst faelschlich 180)
    -- der naehere Messpunkt liefert ihn.
    """
    zeitpunkt_iso = _iso(zeitpunkt)
    vorher = conn.execute(
        "SELECT latitude, longitude, altitude, groundspeed, heading, ts FROM position_history "
        "WHERE cid = ? AND ts <= ? AND ts >= ? ORDER BY ts DESC LIMIT 1",
        (quelle_cid, zeitpunkt_iso, fenster_von),
    ).fetchone()
    nachher = conn.execute(
        "SELECT latitude, longitude, altitude, groundspeed, heading, ts FROM position_history "
        "WHERE cid = ? AND ts >= ? AND ts <= ? ORDER BY ts ASC LIMIT 1",
        (quelle_cid, zeitpunkt_iso, fenster_bis),
    ).fetchone()
    if nachher is None:
        return None
    if vorher is None:
        return dict(nachher)
    if vorher["ts"] == nachher["ts"]:
        return dict(vorher)

    t0, t1 = _als_datetime(vorher["ts"]), _als_datetime(nachher["ts"])
    anteil = (zeitpunkt - t0).total_seconds() / max((t1 - t0).total_seconds(), 1e-6)
    anteil = min(max(anteil, 0.0), 1.0)

    def _interp(a, b):
        if a is None or b is None:
            return a if a is not None else b
        return a + (b - a) * anteil

    def _gekappt(wert, obergrenze):
        if wert is None:
            return wert
        return min(max(wert, 0.0), obergrenze)

    return {
        "latitude": _interp(vorher["latitude"], nachher["latitude"]),
        "longitude": _interp(vorher["longitude"], nachher["longitude"]),
        "altitude": _gekappt(_interp(vorher["altitude"], nachher["altitude"]),
                             _MAX_PLAUSIBLE_ALTITUDE_FT),
        "groundspeed": _gekappt(_interp(vorher["groundspeed"], nachher["groundspeed"]),
                                _MAX_PLAUSIBLE_GROUNDSPEED_KT),
        "heading": vorher["heading"] if anteil < 0.5 else nachher["heading"],
    }


def _neuer_flug(conn, slot: int, jetzt: datetime, belegte_callsigns: set[str],
                kopfstart: bool) -> dict | None:
    """Startet einen neuen simulierten Flug, indem ein echter historischer Flug ab jetzt
    abgespielt wird. None, wenn keine geeignete Historie gefunden wurde (z.B. leere DB).

    Beim Aktivieren (kopfstart) erscheint Slot 0 sofort, ohne Vorsprung -- Nutzerwunsch
    27.09.2026: "der erste Pilot erscheint sofort, sonst weiss ich nicht, ob es wirklich an
    ist". Nur die UEBRIGEN Slots verteilen sich zufaellig ueber die konfigurierte Staffelung.
    Eine spaetere Nachbesetzung (kopfstart=False, ein Flug ist angekommen) startet wie bisher
    immer sofort -- die Staffelung gilt nur fuer den allerersten Schwarm."""
    quelle = _historischen_flug_waehlen(conn)
    if quelle is None:
        return None
    quelle_logon = _als_datetime(quelle["logon_time"])
    quelle_logoff = _als_datetime(quelle["logoff_time"])
    dauer_sek = max((quelle_logoff - quelle_logon).total_seconds(), 1.0)

    vorsprung_sek = 0.0
    if kopfstart and slot > 0:
        from app.database import messeverkehr_staffelung_minuten
        max_staffelung_sek = messeverkehr_staffelung_minuten(conn) * 60.0
        vorsprung_sek = random.uniform(0.0, min(max_staffelung_sek, dauer_sek * 0.7))

    spawn_zeit = jetzt - timedelta(seconds=vorsprung_sek)
    virtueller_start = quelle_logon + timedelta(seconds=vorsprung_sek)
    position = _position_bei(conn, quelle["cid"], virtueller_start,
                             quelle["logon_time"], quelle["logoff_time"])
    if position is None:
        return None

    return {
        "cid": _CID_BASIS - slot,
        "callsign": _freies_callsign(belegte_callsigns),
        "aircraft": quelle["aircraft_short"],
        "aircraft_icao": quelle["aircraft_icao"],
        "departure": quelle["departure"],
        "arrival": quelle["arrival"],
        "route": quelle["route"],
        "flight_rules": quelle["flight_rules"],
        "cruise_tas": quelle["cruise_tas"],
        "alternate": quelle["alternate"],
        "deptime": quelle["deptime"],
        "enroute_time": quelle["enroute_time"],
        "fuel_time": quelle["fuel_time"],
        "latitude": position["latitude"],
        "longitude": position["longitude"],
        "altitude": position["altitude"],
        "groundspeed": position["groundspeed"],
        "heading": position["heading"],
        "logon_time": _iso(spawn_zeit),
        "updated_at": _iso(jetzt),
        "name": _synthetischer_pilotenname(slot),
        "quelle_flight_id": quelle["id"],
        "quelle_cid": quelle["cid"],
        "quelle_logon_time": quelle["logon_time"],
        "quelle_logoff_time": quelle["logoff_time"],
    }


def _fortschreiben(conn, flug: dict, jetzt: datetime) -> dict | None:
    """Rueckt einen laufenden Replay-Flug an die Position vor, die der echte Quellflug zum
    entsprechenden virtuellen Zeitpunkt hatte. None, wenn das Aufzeichnungsfenster zuende ist
    (Flug "angekommen") -- ODER wenn die Zeile keine (vollstaendige) Replay-Buchhaltung traegt.

    Der zweite Fall ist kein theoretisches Risiko: Beim Umstieg vom synthetischen Generator
    auf Historien-Replay (27.09.2026) lagen in der Produktions-DB noch Zeilen aus der alten
    Fassung, ganz ohne quelle_cid/quelle_logon_time/quelle_logoff_time. _als_datetime(None)
    riss damit den KOMPLETTEN Poll-Zyklus alle 15s ab -- nicht nur den Messeverkehr, auch die
    echten Live-Positionen blieben stehen. Eine unvollstaendige Zeile ist fachlich nichts
    anderes als ein "angekommener" Flug: sie wird verworfen und respawnt.
    """
    if not flug.get("quelle_cid") or not flug.get("quelle_logon_time") or not flug.get("quelle_logoff_time"):
        return None
    verstrichen = (jetzt - _als_datetime(flug["logon_time"])).total_seconds()
    virtueller_zeitpunkt = _als_datetime(flug["quelle_logon_time"]) + timedelta(seconds=verstrichen)
    position = _position_bei(conn, flug["quelle_cid"], virtueller_zeitpunkt,
                             flug["quelle_logon_time"], flug["quelle_logoff_time"])
    if position is None:
        return None

    flug = dict(flug)
    flug["latitude"] = position["latitude"]
    flug["longitude"] = position["longitude"]
    flug["altitude"] = position["altitude"]
    flug["groundspeed"] = position["groundspeed"]
    flug["heading"] = position["heading"]
    flug["updated_at"] = _iso(jetzt)
    return flug


def _ziel_anzahl(conn) -> int:
    """Wie viele Fluege gleichzeitig laufen sollen -- die konfigurierte Zielzahl selbst
    (Nutzerentscheidung 27.09.2026: kein Min/Max-Bereich mehr, nur noch ein Maximum)."""
    from app.database import messeverkehr_anzahl_max

    return max(0, messeverkehr_anzahl_max(conn))


def advance_messeverkehr(conn, jetzt: datetime, echte_callsigns: set[str]) -> list[dict]:
    """Schreibt den simulierten Verkehr um einen Schritt fort und persistiert ihn.

    ``echte_callsigns`` sind die Rufzeichen des GERADE echten Verkehrs (aus
    ``get_live_positions``) — kommen zur breiteren Liste aus ``bekannte_echte_callsigns``
    dazu, damit neue simulierte Callsigns weder aktuell noch historisch mit einem echten
    kollidieren. Gibt den neuen Bestand als Liste von Dicts zurück, ohne die interne
    Replay-Buchhaltung (siehe ``_INTERNE_REPLAY_SPALTEN``).
    """
    bestand = {f["cid"]: f for f in get_messeverkehr_positions(conn)}
    kopfstart = not bestand
    belegte_callsigns = bekannte_echte_callsigns(conn) | set(echte_callsigns)
    ziel_anzahl = min(_ziel_anzahl(conn), _MAX_SLOTS)

    aktualisiert: dict[int, dict] = {}
    for slot in range(ziel_anzahl):
        cid = _CID_BASIS - slot
        vorher = bestand.get(cid)
        if vorher is None:
            neuer = _neuer_flug(conn, slot, jetzt, belegte_callsigns, kopfstart)
        else:
            nachher = _fortschreiben(conn, vorher, jetzt)
            neuer = nachher if nachher is not None else _neuer_flug(
                conn, slot, jetzt, belegte_callsigns, kopfstart=False
            )
        if neuer is not None:
            aktualisiert[cid] = neuer
            belegte_callsigns.add(neuer["callsign"])

    replace_messeverkehr_positions(conn, list(aktualisiert.values()))
    # ORDER BY cid, wie get_messeverkehr_positions() -- sonst liefert dieser Rueckgabewert
    # (speist den SSE-Broadcast) eine ANDERE Reihenfolge als der REST-Lesepfad (speist
    # Erstladung + HTTP-Fallback), und die Live-Liste flackert zwischen beiden hin und her
    # (Nutzerfund 27.09.2026: "wechseln staendig die Position").
    geordnet = sorted(aktualisiert.values(), key=lambda f: f["cid"])
    return [{k: v for k, v in f.items() if k not in _INTERNE_REPLAY_SPALTEN}
            for f in geordnet]


def messeverkehr_fuer_anzeige(conn) -> list[dict]:
    """Liest den aktuellen Bestand simulierter Fluege, OHNE ihn fortzuschreiben.

    Fuer lesende Endpunkte (GET /api/live): Nur der Poller darf per advance_messeverkehr
    schreiben, sonst wuerde jeder oeffentliche Seitenaufruf die Simulation antreiben. Leer,
    solange das Feature-Flag aus ist. Ohne die interne Replay-Buchhaltung.
    """
    from app.database import ist_messeverkehr_aktiv

    if not ist_messeverkehr_aktiv(conn):
        return []
    return [{k: v for k, v in f.items() if k not in _INTERNE_REPLAY_SPALTEN}
            for f in get_messeverkehr_positions(conn)]
