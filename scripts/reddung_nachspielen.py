"""Eine FriesenReddung im Zeitraffer nachspielen -- mit dem echten Poller, in einer Wegwerf-DB.

Gebaut am 28.09.2026, damit sich neue Reddung-Funktionen ohne Simulator prüfen lassen (Nutzer:
„ich bin die ganze Woche unterwegs"). Grundlage sind echte Flüge eines vergangenen Abends; die
Uhr wird in 30-s-Schritten vorgespult, und in jedem Schritt läuft genau der Poller-Code, der
auch live läuft (`VatsimPoller._check_reddung`). Admin-Aktionen (Aufnahme freigeben,
Eingrenzung, Fackel) laufen über die echten Endpunkt-Funktionen.

Zwei Unterbefehle:

    # 1. Einen Abend als anonymisierten Datensatz sichern -- aus einer KOPIE der DB, gezogen
    #    mit `.backup` (nie mit cp, WAL!). Namen fallen weg, CIDs und Rufzeichen werden ersetzt.
    python scripts/reddung_nachspielen.py sichern --db kopie.db --event 6 \\
        --aus tests/fixtures/reddung_2026-09-27_eifel.json

    # 2. Nachspielen, ein oder mehrere Szenarien (ohne Angabe: alle)
    python scripts/reddung_nachspielen.py spielen --fixture tests/fixtures/reddung_2026-09-27_eifel.json

Grenzen, die man kennen muss:

* **Die Spuren der FriesenBrügge sind nach 12 Stunden weg** (`bruegge_spur_aufraeumen`). Der
  Datensatz trägt deshalb nur VATSIM-Punkte (alle ~15 s); die Brügge-Meldungen werden daraus
  gespiegelt. Fund- und Aufnahmezeiten können darum um einige Sekunden vom echten Abend
  abweichen -- die Brügge meldet im Sekundentakt.
* **Die Geländehöhe am Wrack** lernte der Server am echten Abend aus der Brügge-Rückmeldung;
  im Szenario „gestern" wird sie beim Fund gesetzt, wie es damals ungefähr geschah.
* **Was im Simulator zu sehen ist**, prüft das nicht -- nur, was in `bruegge_soll` steht.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as _dtmod
import json
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_ISO = "%Y-%m-%dT%H:%M:%SZ"
_UTC = _dtmod.timezone.utc
_ECHT = _dtmod.datetime


# --- Die vorgespulte Uhr --------------------------------------------------------------------

class _Uhr(_ECHT):
    """`datetime` mit einstellbarem „jetzt". Wird in die App-Module eingesetzt, die sich ihr
    `datetime` beim Import geholt haben -- sonst liefe dort weiter die echte Uhr."""
    jetzt: _dtmod.datetime | None = None

    @classmethod
    def now(cls, tz=None):  # noqa: D401
        t = cls.jetzt or _ECHT.now(_UTC)
        return t.replace(tzinfo=None) if tz is None else t.astimezone(tz)

    @classmethod
    def utcnow(cls):
        return (cls.jetzt or _ECHT.now(_UTC)).replace(tzinfo=None)


def _uhr_einsetzen():
    """Setzt die Uhr ein und gibt eine Funktion zurück, die alles zurückstellt."""
    getauscht = []
    for name, mod in list(sys.modules.items()):
        if (name == "app" or name.startswith("app.")) and getattr(mod, "datetime", None) is _ECHT:
            setattr(mod, "datetime", _Uhr)
            getauscht.append(mod)
    _dtmod.datetime = _Uhr

    def zurueck():
        _dtmod.datetime = _ECHT
        for mod in getauscht:
            setattr(mod, "datetime", _ECHT)
    return zurueck


def _t(iso: str) -> _dtmod.datetime:
    return _ECHT.strptime(iso, _ISO).replace(tzinfo=_UTC)


def _iso(t: _dtmod.datetime) -> str:
    return t.strftime(_ISO)


# --- Sichern ---------------------------------------------------------------------------------

_EVENT_FELDER = ("name", "dtstart", "dtend", "sued", "west", "nord", "ost", "kante_km",
                 "korridor_km", "hoehe_max_ft", "gs_max_kt", "gs_min_kt", "fund_radius_m",
                 "fund_hoehe_ft", "havarist_lat", "havarist_lon", "havarist_art",
                 "havarist_grund_ft", "aufnehmen_noetig", "landung_noetig", "aufnahme_verfaellt")


def sichern(db: str, event_id: int, aus: str, *, rand_grad: float = 0.3,
            echt_extra: dict | None = None) -> dict:
    """Einen Abend anonymisiert als JSON ablegen. Gibt die Zuordnung echt -> anonym zurück --
    sie wird NICHT gespeichert (das Repo ist öffentlich)."""
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    ev = dict(c.execute("SELECT * FROM reddung_events WHERE id = ?", (event_id,)).fetchone())
    von = _iso(_t(ev["dtstart"]) - _dtmod.timedelta(minutes=10))
    bis = _iso(_t(ev["dtend"]) + _dtmod.timedelta(minutes=5))
    s, n = sorted((ev["sued"], ev["nord"]))
    w, o = sorted((ev["west"], ev["ost"]))
    nah = [r[0] for r in c.execute(
        "SELECT cid FROM position_history WHERE ts BETWEEN ? AND ? "
        "AND latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ? "
        "GROUP BY cid ORDER BY min(ts)",
        (von, bis, s - rand_grad, n + rand_grad, w - rand_grad, o + rand_grad))]
    zuordnung = {cid: 91001 + i for i, cid in enumerate(nah)}
    rufz = {cid: f"FRS9{i + 1:02d}" for i, cid in enumerate(nah)}
    punkte = [[zuordnung[r["cid"]], rufz[r["cid"]], r["latitude"], r["longitude"],
               r["altitude"], r["groundspeed"], r["heading"], r["ts"]]
              for r in c.execute(
                  "SELECT cid, latitude, longitude, altitude, groundspeed, heading, ts "
                  "FROM position_history WHERE ts BETWEEN ? AND ? ORDER BY ts", (von, bis))
              if r["cid"] in zuordnung]

    def anonym(spalte):
        ts, cid = ev.get(f"{spalte}_am"), ev.get(f"{spalte}_von")
        return None if not ts else {"cid": zuordnung.get(cid), "ts": ts}

    # Der Objektkatalog fuer Wrack, Fackeln und Licht -- ohne ihn stellte die Wegwerf-DB den
    # Havaristen nur fuer X-Plane hin (dort gibt es einen eingebauten Ersatz). Keine
    # persoenlichen Daten, nur Titel und Urteile.
    arten = [ev.get("havarist_art") or "flugzeug_echo", "licht"] + [
        r[0] for r in c.execute("SELECT art FROM bruegge_art WHERE art LIKE 'rauch_%'")]
    platz = ",".join("?" * len(arten))
    katalog = {
        "art": [dict(r) for r in c.execute(
            f"SELECT * FROM bruegge_art WHERE art IN ({platz})", arten)],
        "katalog": [dict(r) for r in c.execute(
            f"SELECT * FROM bruegge_katalog WHERE art IN ({platz})", arten)],
        "titel_lauf": [dict(r) for r in c.execute(
            f"SELECT l.* FROM bruegge_titel_lauf l JOIN bruegge_katalog k ON k.titel = l.titel "
            f"WHERE k.art IN ({platz})", arten)],
    }
    daten = {
        "quelle": f"FriesenReddung vom {ev['dtstart'][:10]}, anonymisiert "
                  f"(CIDs 91001…, Rufzeichen FRS9xx, keine Namen)",
        "event": {k: ev.get(k) for k in _EVENT_FELDER},
        "piloten": [{"cid": zuordnung[cid], "callsign": rufz[cid]} for cid in nah],
        "punkte": punkte,
        "objektkatalog": katalog,
        "echt": {"gefunden": anonym("gefunden"), "aufgenommen": anonym("aufgenommen"),
                 "eingeliefert": {**(anonym("eingeliefert") or {}),
                                  "icao": ev.get("eingeliefert_icao")},
                 **(echt_extra or {})},
    }
    Path(aus).write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"zuordnung": zuordnung, "rufzeichen": rufz}


# --- Nachspielen -----------------------------------------------------------------------------

@dataclass
class Szenario:
    name: str
    beschreibung: str
    event: dict = field(default_factory=dict)       # Felder, die den Datensatz überschreiben
    # "aus_der_naehe": wie im Betrieb vor 15.26.0 -- der Server lernt die Hoehe erst, wenn
    # jemand naeher als 1000 m ans Wrack kommt (dann stellt die Bruegge es auf und meldet).
    # "karte": seit 15.26.0 -- beim Anlegen aus dem Hoehenmodell.
    gelaende: str = "aus_der_naehe"
    aktionen: list = field(default_factory=list)    # [(Uhrzeit HH:MM:SS, Art, Daten)]


def szenarien(daten: dict) -> list[Szenario]:
    """Die Standard-Szenarien für einen gesicherten Abend."""
    e = daten["event"]
    tag = e["dtstart"][:10]
    echt = daten.get("echt") or {}
    freigabe = echt.get("freigabe_admin")          # HH:MM:SS, am echten Abend von Hand
    fr = [(freigabe, "freigeben", {})] if freigabe else []
    hl, hn = e["havarist_lat"], e["havarist_lon"]
    eng = {"eng_sued": round(hl - 0.02, 4), "eng_nord": round(hl + 0.02, 4),
           "eng_west": round(hn - 0.03, 4), "eng_ost": round(hn + 0.03, 4)}
    alt = {"hoehe_max_ft": 2000, "havarist_grund_ft": None}
    return [
        Szenario("gestern", "wie am Abend: 2000 ft AGL, Gelände erst beim Fund bekannt, "
                 "Aufnahme mit dem Fundradius, Freigabe von Hand",
                 {**alt, "aufnahme_radius_m": e.get("fund_radius_m") or 150}, "aus_der_naehe", fr),
        Szenario("gestern_fund150", "wie „gestern“, aber Fundradius 150 m",
                 {**alt, "fund_radius_m": 150, "aufnahme_radius_m": 150}, "aus_der_naehe", fr),
        Szenario("neu", "Gelände aus der Karte ab dem Start, Aufnahme-Radius 150 m",
                 {**alt, "aufnahme_radius_m": 150}, "karte", fr),
        Szenario("signal_start", "„neu“ + Fackel ab dem Start",
                 {**alt, "aufnahme_radius_m": 150, "signal_ab_start": 1}, "karte", fr),
        Szenario("signal_zelle", "„neu“ + Fackel 30 s nach dem Absuchen der Havarist-Zelle",
                 {**alt, "aufnahme_radius_m": 150, "signal_bei_zelle": 1}, "karte", fr),
        Szenario("signal_zelle_ohne_fund", "„neu“ + Zellen-Fackel, aber niemand kann finden "
                 "(Fundhöhe 1 ft) -- zeigt, wann die Fackel zündet",
                 {**alt, "aufnahme_radius_m": 150, "signal_bei_zelle": 1, "fund_hoehe_ft": 1},
                 "karte", []),
        Szenario("eingrenzung", "„neu“ + Eingrenzung um das Wrack um 18:30",
                 {**alt, "aufnahme_radius_m": 150}, "karte",
                 fr + [("18:30:00", "eingrenzen", eng)]),
    ]


@dataclass
class Bericht:
    szenario: str
    beschreibung: str
    zeitleiste: list = field(default_factory=list)
    ergebnis: dict = field(default_factory=dict)
    pushes: list = field(default_factory=list)


def _anfrage(settings, body=None, mit_app=False):
    from app.auth import ADMIN_COOKIE, CONFIRM_COOKIE, make_admin_token, make_confirm_token

    class Anfrage:
        def __init__(self):
            self.cookies = {
                ADMIN_COOKIE: make_admin_token(settings.SECRET_KEY, settings.ADMIN_PASSWORD),
                CONFIRM_COOKIE: make_confirm_token(settings.SECRET_KEY, settings.ADMIN_PASSWORD,
                                                   9_999_999_999)}
            self.headers = {}
            self._body = body or {}

        async def json(self):
            return self._body

        async def body(self):
            return json.dumps(self._body).encode()
    a = Anfrage()
    if mit_app:
        from app import main
        a.app = main.app
    return a


def spielen(daten: dict, sz: Szenario, *, takt_s: int = 30, gelaende_ft: float = 1863.5,
            gelaende_gemessen_ft: float = 1864.3) -> Bericht:
    """Ein Szenario durchspielen. Die Produktion wird nicht berührt."""
    from app import main
    from app import reddung as rd
    from app.abdeckung import raster_masse
    from app.database import (get_connection, get_progress_snapshot, get_reddung_event,
                              init_db, reddung_grund_merken, upsert_pilot)
    from app.geo import haversine
    from app.poller import VatsimPoller

    bericht = Bericht(sz.name, sz.beschreibung)
    ordner = tempfile.mkdtemp(prefix="reddung_nachspielen_")
    pfad = str(Path(ordner) / "sandkasten.db")
    init_db(pfad)
    settings = SimpleNamespace(DB_PATH=pfad, CALLSIGN_PREFIX="FRS", SECRET_KEY="nachspielen",
                               ADMIN_PASSWORD="nachspielen", VAPID_PRIVATE_KEY=None,
                               VAPID_CONTACT_EMAIL="", STATSIM_API_KEY=None)
    alt_settings, alt_gelaende = main.get_settings, main._gelaende_ft
    main.get_settings = lambda: settings

    async def gelaende(lat, lon):
        return gelaende_ft if sz.gelaende == "karte" else None
    main._gelaende_ft = gelaende

    class Poller(VatsimPoller):
        def broadcast_notify(self, dienst, cid, payload, **kw):  # noqa: D401
            bericht.pushes.append((_iso(_Uhr.jetzt), payload.get("body")))

    poller = Poller(db_path=pfad, callsign_prefix="FRS", poll_interval=60)
    main.app.state.poller = poller
    zurueck = _uhr_einsetzen()
    try:
        e = daten["event"]
        start, ende = _t(e["dtstart"]), _t(e["dtend"])
        _Uhr.jetzt = start - _dtmod.timedelta(minutes=5)
        c = get_connection(pfad)
        for p in daten["piloten"]:
            upsert_pilot(c, p["cid"], p["callsign"])
        for tabelle, zeilen in (("bruegge_art", daten.get("objektkatalog", {}).get("art", [])),
                                ("bruegge_katalog", daten.get("objektkatalog", {}).get("katalog", [])),
                                ("bruegge_titel_lauf", daten.get("objektkatalog", {}).get("titel_lauf", []))):
            # Nur Spalten, die dieses Schema kennt -- die Produktion kann eine Spalte mehr
            # haben (neuerer Stand, Messspalte), und daran darf das Nachspielen nicht scheitern.
            spalten = {r[1] for r in c.execute(f"PRAGMA table_info({tabelle})")}
            for z in zeilen:
                z = {k: v for k, v in z.items() if k in spalten}
                c.execute(f"INSERT OR REPLACE INTO {tabelle} ({', '.join(z)}) "
                          f"VALUES ({', '.join('?' * len(z))})", list(z.values()))
        c.commit()
        c.close()

        body = {k: v for k, v in {**e, **sz.event}.items() if v is not None}
        body["lagetext"] = "Nachgespielt: " + (e.get("name") or "FriesenReddung")
        eid = asyncio.run(main.admin_create_reddung_event(_anfrage(settings, body)))["id"]

        punkte = sorted(daten["punkte"], key=lambda p: p[7])
        naechster = 0
        tag = e["dtstart"][:10]
        aktionen = sorted(((f"{tag}T{zeit}Z", art, d) for zeit, art, d in sz.aktionen),
                          key=lambda a: a[0])
        erledigt: set[int] = set()
        zuvor: dict = {}
        _z, _s, _, _ = raster_masse(float(e["sued"]), float(e["west"]), float(e["nord"]),
                                    float(e["ost"]), float(e.get("kante_km") or 1.0))
        n_zellen = _z * _s

        def notiz(text):
            bericht.zeitleiste.append((_iso(_Uhr.jetzt)[11:19], text))

        t = _Uhr.jetzt
        while t <= ende + _dtmod.timedelta(minutes=3):
            _Uhr.jetzt = t
            jetzt = _iso(t)
            c = get_connection(pfad)
            # Punkte bis „jetzt" nachtragen -- erst dann sieht der Poller sie, wie im Betrieb.
            while naechster < len(punkte) and punkte[naechster][7] <= jetzt:
                cid, cs, lat, lon, alt, gs, hdg, ts = punkte[naechster]
                c.execute("INSERT INTO position_history (cid, callsign, latitude, longitude, "
                          "altitude, groundspeed, heading, ts) VALUES (?,?,?,?,?,?,?,?)",
                          (cid, cs, lat, lon, alt, gs, hdg, ts))
                c.execute("INSERT OR REPLACE INTO bruegge_spur (cid, ts, lat, lon, alt_msl_ft, "
                          "gs_kt) VALUES (?,?,?,?,?,?)", (cid, ts, lat, lon, alt, gs))
                # Die letzte Brügge-Meldung -- mit ihr erkennt der Poller die Einlieferung
                # (reddung_landung_aus_bruegge). `am_boden` kennt VATSIM nicht; wer steht
                # (<= 5 kt, wie _REDDUNG_STEHT_KT), gilt als am Boden. Ein schwebender
                # Hubschrauber wuerde so falsch gelesen -- am Platz, wo es zaehlt, landet man.
                c.execute("INSERT OR REPLACE INTO bruegge_positions (cid, lat, lon, alt_msl_ft, "
                          "gs_kt, kurs, am_boden, simulator, gemeldet_am) "
                          "VALUES (?,?,?,?,?,?,?,?,?)",
                          (cid, lat, lon, alt, gs, hdg, 1 if (gs or 0) <= 5 else 0, "msfs2024", ts))
                naechster += 1
            ev = dict(get_reddung_event(c, eid))
            # Wie vor 15.26.0: Die Hoehe lernt der Server erst, wenn die Bruegge das Wrack
            # aufgestellt hat -- und das bekommt nur, wer naeher als 1000 m ist, seitlich und in
            # der Hoehe ueber Grund (bruegge_soll_fuer, _HAVARIST_NAH_M).
            if sz.gelaende == "aus_der_naehe" and ev.get("havarist_grund_ft") is None:
                grenze = _iso(t - _dtmod.timedelta(seconds=takt_s))
                for cid, cs, lat, lon, alt, gs, hdg, ts in punkte[:naechster]:
                    if ts <= grenze:
                        continue
                    seitlich_m = haversine(lat, lon, e["havarist_lat"], e["havarist_lon"]) * 1000
                    agl_m = (alt - gelaende_gemessen_ft) * 0.3048
                    if seitlich_m <= 1000 and agl_m <= 1000:
                        reddung_grund_merken(c, eid, gelaende_gemessen_ft, "gemessen")
                        notiz(f"Geländehöhe gemessen: {gelaende_gemessen_ft} ft "
                              f"({cs} {seitlich_m:.0f} m vom Wrack)")
                        break
            c.commit()
            c.close()
            for i, (wann, art, d) in enumerate(aktionen):
                if i in erledigt or wann > jetzt:
                    continue
                erledigt.add(i)
                try:
                    if art == "freigeben":
                        asyncio.run(main.admin_reddung_aufnahme_freigeben(_anfrage(settings), eid))
                    elif art == "eingrenzen":
                        asyncio.run(main.admin_update_reddung_event(
                            _anfrage(settings, d, mit_app=True), eid))
                    elif art == "signal":
                        asyncio.run(main.admin_reddung_signal(_anfrage(settings), eid))
                    notiz(f"Admin: {art}")
                except Exception as fehler:  # noqa: BLE001 -- gehört in den Bericht
                    notiz(f"Admin: {art} abgelehnt ({getattr(fehler, 'detail', fehler)})")

            asyncio.run(poller._check_reddung())

            c = get_connection(pfad)
            ev = dict(get_reddung_event(c, eid))
            snap = get_progress_snapshot(c, "reddung", eid) or {}
            objekte = {r[0]: r[1] for r in c.execute("SELECT id, art FROM bruegge_soll")}
            c.close()
            name = {p["cid"]: p["callsign"] for p in daten["piloten"]}
            for spalte in ("signal", "gefunden", "aufgenommen", "eingeliefert", "aufgeloest"):
                wert = ev.get(f"{spalte}_am")
                if wert != zuvor.get(spalte):
                    wer = name.get(ev.get(f"{spalte}_von"), "")
                    wo = f" in {ev.get('eingeliefert_icao')}" if spalte == "eingeliefert" and wert else ""
                    notiz(f"{spalte}: {wert or '— zurückgesetzt'} {wer}{wo}".rstrip())
                    zuvor[spalte] = wert
            if objekte != zuvor.get("objekte"):
                sichtbar = ", ".join(f"{k.split('-', 2)[-1]}={v}" for k, v in sorted(objekte.items()))
                notiz(f"im Simulator: {sichtbar or 'nichts'}")
                zuvor["objekte"] = objekte
            t += _dtmod.timedelta(seconds=takt_s)

        c = get_connection(pfad)
        ev = dict(get_reddung_event(c, eid))
        snap = get_progress_snapshot(c, "reddung", eid) or {}
        je = {name.get(int(k), k): v for k, v in (snap.get("je_pilot") or {}).items()}
        zelle = rd.havarist_zelle(ev)
        oeffentlich = next((r for r in main.reddung_events() if r["id"] == eid), {})
        c.close()
        bericht.ergebnis = {
            "abgesucht": f"{len(snap.get('treffer') or {})} von {n_zellen} Zellen "
                         f"({100 * len(snap.get('treffer') or {}) / n_zellen:.0f} %)",
            "je_pilot": dict(sorted(je.items(), key=lambda kv: -kv[1])),
            "havarist_zelle_abgesucht": (snap.get("treffer") or {}).get(zelle),
            "grund_ft": (ev.get("havarist_grund_ft"), ev.get("havarist_grund_quelle")),
            "eingrenzung_oeffentlich": oeffentlich.get("eingrenzung"),
            "lagetext_oeffentlich": bool(oeffentlich.get("lagetext")),
            # Je Zelle: wann zuerst abgesucht, von wem -- fuer den Vergleich zweier Szenarien.
            "_treffer": {k: (v[1], name.get(v[0], v[0])) for k, v in (snap.get("treffer") or {}).items()},
        }
        return bericht
    finally:
        zurueck()
        _Uhr.jetzt = None
        main.get_settings, main._gelaende_ft = alt_settings, alt_gelaende


def _drucken(b: Bericht, daten: dict) -> None:
    print(f"\n=== {b.szenario}: {b.beschreibung}")
    for zeit, text in b.zeitleiste:
        print(f"  {zeit}  {text}")
    for zeit, text in b.pushes:
        print(f"  {zeit[11:19]}  Push: {text}")
    for k, v in b.ergebnis.items():
        if not k.startswith("_"):
            print(f"  → {k}: {v}")


def vergleich(vorher: Bericht, nachher: Bericht) -> dict:
    """Zelle für Zelle: Wäre sie in ``nachher`` früher abgesucht gewesen als in ``vorher``?

    Nutzer, 28.09.2026: Mit der falschen Suchhöhe („2000 ft AGL" = 2000 ft MSL, solange das
    Gelände unbekannt war) flogen die Piloten oft über eine Zelle, ohne dass sie zählte, drehten
    um und holten sie tiefer nach. Das zeigt sich hier als Zelle, die ``nachher`` deutlich
    früher fällt -- oder überhaupt erst.
    """
    a, b = vorher.ergebnis["_treffer"], nachher.ergebnis["_treffer"]
    frueher = {}
    for k, (ts_b, wer_b) in b.items():
        if k in a and ts_b < a[k][0]:
            frueher[k] = (_t(a[k][0]) - _t(ts_b)).total_seconds() / 60.0
    nur_nachher = sorted(set(b) - set(a))
    nur_vorher = sorted(set(a) - set(b))
    minuten = sorted(frueher.values())
    return {
        "zellen_vorher": len(a), "zellen_nachher": len(b),
        "frueher_abgesucht": len(frueher),
        "davon_mehr_als_2_min_frueher": sum(1 for m in minuten if m > 2),
        "mittel_min_frueher": round(sum(minuten) / len(minuten), 1) if minuten else 0.0,
        "median_min_frueher": round(minuten[len(minuten) // 2], 1) if minuten else 0.0,
        "nur_nachher_abgesucht": len(nur_nachher),
        "nur_vorher_abgesucht": len(nur_vorher),
    }


def main_cli(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="befehl", required=True)
    s = sub.add_parser("sichern")
    s.add_argument("--db", required=True)
    s.add_argument("--event", type=int, required=True)
    s.add_argument("--aus", required=True)
    s.add_argument("--echt", default="{}", help="zusätzliche Fakten als JSON, z. B. Freigabezeit")
    p = sub.add_parser("spielen")
    p.add_argument("--fixture", required=True)
    p.add_argument("--szenario", action="append")
    a = ap.parse_args(argv)
    if a.befehl == "sichern":
        z = sichern(a.db, a.event, a.aus, echt_extra=json.loads(a.echt))
        print("Zuordnung (nur hier, NICHT gespeichert):")
        for cid, anon in z["zuordnung"].items():
            print(f"  {cid} -> {anon} {z['rufzeichen'][cid]}")
        return
    daten = json.loads(Path(a.fixture).read_text(encoding="utf-8"))
    berichte = {}
    for sz in szenarien(daten):
        if a.szenario and sz.name not in a.szenario:
            continue
        berichte[sz.name] = spielen(daten, sz)
        _drucken(berichte[sz.name], daten)
    if "gestern" in berichte and "neu" in berichte:
        print("\n=== Vergleich gestern -> neu (Zelle für Zelle)")
        for k, v in vergleich(berichte["gestern"], berichte["neu"]).items():
            print(f"  {k}: {v}")
    print("\nam echten Abend:", json.dumps(daten.get("echt"), ensure_ascii=False))


if __name__ == "__main__":
    main_cli()
