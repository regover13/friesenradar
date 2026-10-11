"""Ersatzweg bei stehendem VATSIM-Feed (GitHub-Issue #63).

Am 11.10.2026 lieferte ``vatsim-data.json`` über viele Stunden denselben Stand; das Netz
selbst lief. Steht der Hauptfeed, baut dieses Modul aus den Quellen, die weiterlaufen, einen
Feed in derselben Form nach -- der Poller arbeitet danach unverändert weiter:

- Funkliste (``transceivers-data.json``): Rufzeichen, Position, Höhe -- alle Piloten auf einmal.
- Status je Mitglied (``/v2/members/<cid>/status``): Anmeldezeit und Flugplan.
- Lotsenliste (``/v2/atc/online``): Rufzeichen, Nummer, Anmeldezeit -- ohne Frequenz.

Geschwindigkeit und Kurs fehlen in der Funkliste und werden aus aufeinanderfolgenden
Positionen gerechnet. Reine Funktionen und Abrufe; Zustand und Datenbank hält der Poller.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

TRANSCEIVERS_URL = "https://data.vatsim.net/v3/transceivers-data.json"
ATC_ONLINE_URL = "https://api.vatsim.net/v2/atc/online"
STATUS_URL = "https://api.vatsim.net/v2/members/{cid}/status"

# Der Hauptfeed erneuert sich rund alle 15 s. Ist sein Stand älter als das, steht er.
STILLSTAND_SEC = 120
# Statusabfrage je Flug: einmal, dann selten (Flugplan kann sich ändern); ohne Flugplan öfter.
STATUS_TAKT_SEC = 300
STATUS_TAKT_OHNE_PLAN_SEC = 120
STATUS_TAKT_FEHLER_SEC = 30
# Scheitert die Statusabfrage, gilt eine frühere Bestätigung höchstens so lange weiter.
BESTAETIGUNG_GILT_SEC = 360   # eine verpasste Auffrischung, nicht mehr
LOTSEN_TAKT_SEC = 60
# So viele Zyklen läuft ein laufender Flug ohne Eintrag in der Funkliste weiter.
KARENZ_ZYKLEN = 3
# Steht die Position so lange unverändert, steht das Flugzeug (und nicht nur die Funkliste).
_STAND_SEC = 40
# Schneller ist kein Flugzeug im Netz (höchster je gemessener echter Wert: 762 kt). Was
# darüber liegt, ist ein Sprung -- eine neue Verbindung an anderem Ort.
_GS_MAX_KT = 900
_SPRUNG_NM = 1.0
_M_IN_FT = 3.28084
_ERDRADIUS_NM = 3440.065
# In der Anzeige steht die Frequenz neben der Station; die Lotsenliste kennt keine.
KEINE_FREQUENZ_ANZEIGE = "–"


def _zeit(roh) -> datetime | None:
    """ISO-Zeit mit Z (auch mit sieben Nachkommastellen wie im Feed) -> UTC-Zeitpunkt."""
    s = str(roh or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1]
    if "." in s:
        kopf, bruch = s.split(".", 1)
        s = f"{kopf}.{bruch[:6]}"
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def feed_alter_s(vatsim_data, jetzt: datetime) -> float | None:
    """Alter des Feed-Standes in Sekunden; ``None``, wenn der Feed keinen Stand nennt."""
    if not isinstance(vatsim_data, dict):
        return None
    general = vatsim_data.get("general")
    if not isinstance(general, dict):
        return None
    t = _zeit(general.get("update_timestamp"))
    if t is None:
        return None
    return (jetzt - t).total_seconds()


def feed_steht(vatsim_data, jetzt: datetime) -> bool:
    """Steht der Hauptfeed? Ein Feed ohne Zeitstempel gilt als laufend (alte Form, Tests)."""
    alter = feed_alter_s(vatsim_data, jetzt)
    return alter is not None and alter > STILLSTAND_SEC


def gleiche_anmeldung(a, b) -> bool:
    """Dieselbe Verbindung? Der Feed nennt die Anmeldezeit mit Nachkommastellen, die
    Statusabfrage auf die Sekunde."""
    ta, tb = _zeit(a), _zeit(b)
    return ta is not None and tb is not None and abs((ta - tb).total_seconds()) <= 2.0


def funk_positionen(roh) -> dict[str, tuple[float, float, int]]:
    """Funkliste -> ``{RUFZEICHEN: (lat, lon, hoehe_ft)}``. Wer kein Funkgerät führt oder bei
    0/0 steht, fehlt."""
    erg: dict[str, tuple[float, float, int]] = {}
    for e in roh if isinstance(roh, list) else []:
        if not isinstance(e, dict):
            continue
        cs = str(e.get("callsign") or "").strip().upper()
        # Bodenstationen (EDGG_CTR, EDDH_ATIS, …_OBS) stehen auch in der Funkliste.
        if not cs or "_" in cs:
            continue
        for t in e.get("transceivers") or []:
            try:
                lat, lon = float(t["latDeg"]), float(t["lonDeg"])
                hoehe = float(t.get("heightMslM") or 0.0)
            except (KeyError, TypeError, ValueError):
                continue
            if (lat == 0.0 and lon == 0.0) or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                continue
            erg[cs] = (lat, lon, int(round(hoehe * _M_IN_FT)))
            break
    return erg


def _strecke_nm(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _ERDRADIUS_NM * math.asin(min(1.0, math.sqrt(a)))


def _kurs(lat1, lon1, lat2, lon2) -> int:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return int(round(math.degrees(math.atan2(y, x)))) % 360


class Fahrtrechner:
    """Geschwindigkeit und Kurs aus aufeinanderfolgenden Positionen je Rufzeichen.

    Die Funkliste trägt keinen Zeitstempel je Eintrag; ``t`` ist der Stand der Liste
    (``Last-Modified``) in Sekunden. Eine unveränderte Position heißt meist nur, dass die
    Liste zwischen zwei Abrufen nicht erneuert wurde -- erst nach ``_STAND_SEC`` gilt das
    Flugzeug als stehend.
    """

    def __init__(self) -> None:
        # cs -> [lat, lon, t, gs, hdg, bekannt]
        self._stand: dict[str, list] = {}
        # Rufzeichen, die im letzten Durchgang gesprungen sind (neue Verbindung an anderem Ort).
        self.spruenge: set[str] = set()

    def rechne(self, cs: str, lat: float, lon: float, t: float) -> tuple[int, int] | None:
        """``(gs_kt, kurs)`` oder ``None``, solange noch nichts feststeht (erster Punkt)."""
        s = self._stand.get(cs)
        if s is None:
            self._stand[cs] = [lat, lon, t, 0, 0, False]
            return None
        if lat == s[0] and lon == s[1]:
            if t - s[2] > _STAND_SEC:
                s[3], s[5] = 0, True
            return (s[3], s[4]) if s[5] else None
        dt = t - s[2]
        strecke = _strecke_nm(s[0], s[1], lat, lon)
        if dt < 1.0:
            # Derselbe Listenstand, andere Position: Über die Zeit lässt sich nichts rechnen.
            # Ein weiter Versatz ist trotzdem ein Sprung.
            if strecke > _SPRUNG_NM:
                self._stand[cs] = [lat, lon, t, 0, s[4], False]
                self.spruenge.add(cs)
                return None
            return (s[3], s[4]) if s[5] else None
        gs = strecke / dt * 3600.0
        if gs > _GS_MAX_KT:
            # Sprung (Neuverbindung an anderem Ort): Bezug neu setzen, Wert verwerfen.
            self._stand[cs] = [lat, lon, t, 0, s[4], False]
            self.spruenge.add(cs)
            return None
        # Unter 1 kt ist es Zittern am Boden; der Kurs daraus wäre gewürfelt.
        hdg = _kurs(s[0], s[1], lat, lon) if gs >= 1.0 else s[4]
        self._stand[cs] = [lat, lon, t, int(round(gs)), hdg, True]
        return int(round(gs)), hdg

    def behalte(self, rufzeichen) -> None:
        """Vergisst alle, die nicht mehr in der Liste stehen."""
        weg = set(self._stand) - set(rufzeichen)
        for cs in weg:
            del self._stand[cs]


def _typ_kurz(aircraft: str) -> str:
    """``LEG2/L-SDGRY/S`` -> ``LEG2``; FAA-Form ``H/B744/L`` -> ``B744``."""
    teile = [t for t in str(aircraft or "").split("/") if t]
    if not teile:
        return ""
    if len(teile[0]) == 1 and len(teile) > 1:
        return teile[1]
    return teile[0]


def _hhmm(std, minuten) -> str:
    try:
        return f"{int(std):02d}{int(minuten):02d}"
    except (TypeError, ValueError):
        return ""


def flugplan_aus_status(status) -> dict | None:
    """Flugplan aus der Statusabfrage in der Form des Hauptfeeds; ``None`` ohne Flugplan."""
    fp = status.get("fp") if isinstance(status, dict) else None
    if not isinstance(fp, dict):
        return None
    aircraft = str(fp.get("aircraft") or "")
    kurz = _typ_kurz(aircraft)
    regeln = str(fp.get("flight_type") or "").upper()
    return {
        "flight_rules": regeln[:1] if regeln[:1] in ("I", "V", "Y", "Z", "S", "D") else "",
        "aircraft": aircraft,
        "aircraft_faa": aircraft,
        "aircraft_short": kurz,
        "departure": str(fp.get("dep") or "").upper(),
        "arrival": str(fp.get("arr") or "").upper(),
        "alternate": str(fp.get("alt") or "").upper(),
        "cruise_tas": str(fp.get("cruisespeed") or ""),
        "altitude": str(fp.get("altitude") or ""),
        "deptime": str(fp.get("deptime") or ""),
        "enroute_time": _hhmm(fp.get("hrsenroute"), fp.get("minenroute")),
        "fuel_time": _hhmm(fp.get("hrsfuel"), fp.get("minsfuel")),
        "remarks": str(fp.get("rmks") or ""),
        "route": str(fp.get("route") or ""),
        "assigned_transponder": str(fp.get("assignedsquawk") or ""),
    }


def pilot_eintrag(cid, name: str, cs: str, lat: float, lon: float, hoehe_ft: int,
                  gs: int, hdg: int, logon: str, flugplan: dict | None, stand: str) -> dict:
    """Ein Pilot in der Form des Hauptfeeds."""
    return {
        "cid": cid, "name": name or "", "callsign": cs,
        "latitude": lat, "longitude": lon, "altitude": hoehe_ft,
        "groundspeed": gs, "heading": hdg,
        "flight_plan": flugplan, "logon_time": logon or "", "last_updated": stand,
        "ersatz": True,
    }


def lotsen_eintraege(roh) -> list[dict]:
    """Lotsenliste -> ``controllers`` in der Form des Hauptfeeds (ohne Frequenz und Namen)."""
    erg = []
    for e in roh if isinstance(roh, list) else []:
        if not isinstance(e, dict):
            continue
        try:
            cid = int(e.get("id"))
        except (TypeError, ValueError):
            continue
        cs = str(e.get("callsign") or "").strip().upper()
        if not cs:
            continue
        erg.append({"cid": cid, "name": "", "callsign": cs, "frequency": "",
                    "text_atis": [], "logon_time": str(e.get("start") or ""), "ersatz": True})
    return erg


async def hole_funkliste(client: httpx.AsyncClient) -> tuple[list, float | None]:
    """Funkliste und ihr Stand (``Last-Modified`` als Epoche, sonst ``None``)."""
    r = await client.get(TRANSCEIVERS_URL, timeout=20.0)
    r.raise_for_status()
    stand = None
    try:
        kopf = r.headers.get("last-modified")
        if kopf:
            stand = parsedate_to_datetime(kopf).timestamp()
    except (TypeError, ValueError):
        stand = None
    return r.json(), stand


async def hole_lotsenliste(client: httpx.AsyncClient) -> list:
    r = await client.get(ATC_ONLINE_URL, timeout=15.0)
    r.raise_for_status()
    return r.json()


async def hole_status(client: httpx.AsyncClient, cid: int) -> dict | None:
    """Status eines Mitglieds; ``None``, wenn es nicht verbunden ist (404)."""
    r = await client.get(STATUS_URL.format(cid=int(cid)), timeout=10.0)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    daten = r.json()
    return daten if isinstance(daten, dict) else None
