"""Friesen als Lotsen (#61): wer gerade lotst, wer eine Schicht gebucht hat, und was gemeldet wird.

Reine Funktionen ohne Netz und ohne Datenbank; Abruf, Merken und Versand macht der Poller.

Erkannt wird ein Friese hier über seine VATSIM-Nummer, nicht über das Rufzeichen: Ein Lotse
meldet sich als ``EDDP_GND`` an, nie als ``FRS…``. Für alles andere (Karte, Listen, Wertungen)
bleibt Friese, wer mit FRS-Rufzeichen fliegt.

Angezeigt werden nur Stationen an einem Flugplatz. Kontrollzentralen (``_CTR``, ``_FSS``)
bleiben ganz weg (Nutzerentscheidung 09.10.2026), Beobachter und ATIS ohnehin.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.geo import icao_to_coords, _airports_icao

BUCHUNGEN_URL = "https://atc-bookings.vatsim.net/api/booking"
VORSCHAU_TAGE = 7
_ORTSZEIT = ZoneInfo("Europe/Berlin")
_MORGEN_STUNDE = 7

# Letzter Teil des Rufzeichens -> Anzeigename. Was hier nicht steht, ist keine Station an
# einem Flugplatz und wird nicht angezeigt.
_ARTEN = {
    "DEL": "Delivery",
    "GND": "Ground",
    "TWR": "Tower",
    "APP": "Approach",
    "DEP": "Departure",
}

# airportsdata nennt die Orte englisch. Nur die, die im deutschen Lotsenbetrieb vorkommen.
_ORT_DEUTSCH = {
    "Nuremberg": "Nürnberg", "Munich": "München", "Cologne": "Köln", "Lubeck": "Lübeck",
    "Dusseldorf": "Düsseldorf", "Frankfurt am Main": "Frankfurt", "Munster": "Münster",
    "Saarbrucken": "Saarbrücken", "Monchengladbach": "Mönchengladbach",
}


def station(callsign: str) -> dict | None:
    """Zerlegt ein Lotsen-Rufzeichen. ``None``, wenn es keine Station an einem Flugplatz ist."""
    teile = [t for t in str(callsign or "").upper().split("_") if t]
    if len(teile) < 2:
        return None
    art = _ARTEN.get(teile[-1])
    icao = teile[0]
    if not art or len(icao) != 4:
        return None
    koord = icao_to_coords(icao)
    if koord is None:
        return None
    eintrag = _airports_icao().get(icao) or {}
    ort = (eintrag.get("city") or eintrag.get("name") or icao).strip()
    ort = _ORT_DEUTSCH.get(ort, ort)
    return {"icao": icao, "art": art, "name": f"{ort} {art}",
            "lat": float(koord[0]), "lon": float(koord[1])}


def friesen_lotsen(vatsim_data: dict, cids: set[int]) -> list[dict]:
    """Friesen, die laut Feed gerade an einem Flugplatz lotsen."""
    erg = []
    for c in (vatsim_data or {}).get("controllers") or []:
        if not isinstance(c, dict) or c.get("cid") not in cids:
            continue
        s = station(c.get("callsign", ""))
        if s is None:
            continue
        erg.append({
            "cid": c["cid"],
            "callsign": str(c.get("callsign", "")).upper(),
            "frequenz": str(c.get("frequency") or ""),
            "station": s["name"], "icao": s["icao"], "lat": s["lat"], "lon": s["lon"],
            "online_seit": c.get("logon_time") or "",
            "infotext": [str(z) for z in (c.get("text_atis") or []) if z],
        })
    erg.sort(key=lambda l: l["callsign"])
    return erg


def _zeit(roh) -> datetime | None:
    """``2026-10-11 18:00:00`` (Buchungsliste, UTC) oder ISO mit Z -> UTC-Zeitpunkt."""
    try:
        t = datetime.fromisoformat(str(roh).strip().replace("Z", "+00:00").replace(" ", "T"))
    except (ValueError, TypeError):
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def buchungen_filtern(roh: list, cids: set[int], jetzt: datetime, tage: int = VORSCHAU_TAGE) -> list[dict]:
    """Schichten bekannter Friesen an Flugplatz-Stationen, die noch nicht vorbei sind und in
    den nächsten ``tage`` Tagen beginnen. Nach Beginn sortiert."""
    grenze = jetzt + timedelta(days=tage)
    erg = []
    for b in roh or []:
        if not isinstance(b, dict) or b.get("cid") not in cids or b.get("id") is None:
            continue
        von, bis = _zeit(b.get("start")), _zeit(b.get("end"))
        if von is None or bis is None or bis <= jetzt or von > grenze:
            continue
        s = station(b.get("callsign", ""))
        if s is None:
            continue
        erg.append({"id": b["id"], "cid": b["cid"], "callsign": str(b["callsign"]).upper(),
                    "station": s["name"], "icao": s["icao"], "lat": s["lat"], "lon": s["lon"],
                    "von": _iso(von), "bis": _iso(bis)})
    erg.sort(key=lambda b: (b["von"], b["id"]))
    return erg


# "Expected Logoff Time 2000z", "est OFF AT 1600Z", "online until 21:30z", "bis 1900z".
# Bewusst eng: Eine nackte Uhrzeit ("ATIS M 1430Z") ist keine Endzeit.
_ENDE_RE = re.compile(
    r"(?:log\s*-?off|off\s*at|until|till|\bbis\b|closing|closes?)\D{0,15}?([0-2]\d):?([0-5]\d)\s*(?:z|utc)\b",
    re.IGNORECASE,
)


def endzeit_aus_infotext(zeilen) -> str | None:
    for zeile in zeilen or []:
        m = _ENDE_RE.search(str(zeile))
        if m and int(m.group(1)) < 24:
            return f"{m.group(1)}:{m.group(2)}"
    return None


def endzeit(lotse: dict, buchungen: list[dict], jetzt: datetime) -> str | None:
    """Voraussichtliches Ende als ``HH:MM`` (UTC): erst der Infotext, sonst die laufende
    Buchung desselben Lotsen an derselben Station. Sonst ``None``."""
    aus_text = endzeit_aus_infotext(lotse.get("infotext"))
    if aus_text:
        return aus_text
    for b in buchungen or []:
        if b.get("cid") != lotse.get("cid") or b.get("callsign") != lotse.get("callsign"):
            continue
        von, bis = _zeit(b.get("von")), _zeit(b.get("bis"))
        if von and bis and von <= jetzt < bis:
            return bis.strftime("%H:%M")
    return None


# --- Meldungstexte (freigegeben 09.10.2026) ------------------------------------------------

def _spanne(b: dict) -> str:
    von, bis = _zeit(b.get("von")), _zeit(b.get("bis"))
    return f"{von:%H:%M}–{bis:%H:%M} UTC" if von and bis else ""


def payload_lotse_online(name: str, lotse: dict) -> dict:
    body = f"{lotse['callsign']} auf {lotse['frequenz']}"
    if lotse.get("bis"):
        body += f", bis ca. {lotse['bis']} UTC"
    return {"title": f"{name} lotst jetzt {lotse['station']} 🎧", "body": body, "url": "/"}


def payload_lotsen_heute(eintraege: list[tuple[str, dict]]) -> dict:
    """Eine Meldung für den ganzen Tag. ``eintraege``: (Name, Buchung)."""
    teile = [f"{name}, {b['station']} {_spanne(b)}" for name, b in eintraege]
    return {"title": "Heute lotsen 🎧", "body": " · ".join(teile), "url": "/"}


def payload_lotse_spaet(name: str, buchung: dict) -> dict:
    return {"title": f"{name} lotst heute {buchung['station']} 🎧",
            "body": f"{buchung['callsign']}, {_spanne(buchung)}", "url": "/"}


# --- 7 Uhr deutscher Zeit ------------------------------------------------------------------

def ortstag(jetzt: datetime) -> str:
    """Deutscher Kalendertag (Sommer- und Winterzeit beachtet) als ``JJJJ-MM-TT``."""
    return jetzt.astimezone(_ORTSZEIT).strftime("%Y-%m-%d")


def nach_sieben(jetzt: datetime) -> bool:
    return jetzt.astimezone(_ORTSZEIT).hour >= _MORGEN_STUNDE


def beginnt_am(buchung: dict, tag: str) -> bool:
    von = _zeit(buchung.get("von"))
    return von is not None and ortstag(von) == tag


def melde_plan(buchungen: list[dict], jetzt: datetime, morgen_tag: str | None,
               gemeldet: set) -> dict:
    """Was jetzt zu melden ist.

    ``morgen_tag``: der Tag, für den die Sammelmeldung zuletzt erledigt wurde (``None`` =
    erster Lauf überhaupt). ``gemeldet``: Kennungen schon gemeldeter Buchungen.

    Rückgabe: ``morgen`` (Buchungen für die Sammelmeldung), ``spaet`` (einzeln sofort),
    ``morgen_tag`` (neuer Stand) und ``merken`` (Kennungen, die als gemeldet gelten).
    """
    heute = ortstag(jetzt)
    offen = [b for b in buchungen
             if beginnt_am(b, heute) and b["id"] not in gemeldet
             and (_zeit(b["bis"]) or jetzt) > jetzt]
    offen.sort(key=lambda b: (b["von"], b["id"]))
    ids = [b["id"] for b in offen]

    if morgen_tag is None:
        # Erster Lauf: nur den Stand setzen. Sonst käme am Tag des Einspielens eine
        # Sammelmeldung zu einer beliebigen Uhrzeit.
        return {"morgen": [], "spaet": [], "morgen_tag": heute, "merken": ids}
    if morgen_tag == heute:
        return {"morgen": [], "spaet": offen, "morgen_tag": heute, "merken": ids}
    if not nach_sieben(jetzt):
        return {"morgen": [], "spaet": [], "morgen_tag": morgen_tag, "merken": []}
    return {"morgen": offen, "spaet": [], "morgen_tag": heute, "merken": ids}
