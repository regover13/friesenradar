"""Hinweis nach einem Flug mit fehlendem oder altem Paket (Nutzerwunsch 12.10.2026).

Geurteilt wird am letzten BEENDETEN Flug eines Piloten: Hat währenddessen eine FriesenBrügge
gemeldet und mit welcher Fassung, dasselbe fürs Kniebrett. Der Banner auf Website und Kniebrett
lässt sich wegklicken und kommt mit dem nächsten Flug wieder, solange der Mangel besteht.

Zwei Regeln des Nutzers, die hier wohnen:

* **Fehlt ein Paket ganz, gibt es nur den Banner.** Eine Push-Meldung geht allein bei einem
  veralteten Paket raus. Am 12.10.2026 flogen 30 von 45 Aktiven ohne Brügge; sie sollen keine
  Meldungen für etwas bekommen, das sie nie installiert haben.
* **Ein fehlendes Kniebrett ist nur in MSFS 2024 ein Mangel**, und den Simulator nennt allein
  die Brügge. Ohne Brügge bleibt es beim Urteil über eine gemeldete alte Fassung.

„Fehlt“ heißt beim Kniebrett: Der Pilot hat NIE ein Gerät gebunden. Ob es beim Flug lief, lässt
sich nicht feststellen -- es meldet sich nur beim Start, und der liegt vor dem Flug.

Bekannte Grenze: „Brügge hat gemeldet“ heißt hier „wurde dem Piloten zugeordnet“
(``bruegge_zuordnung``). Läuft eine Brügge, ohne je zugeordnet zu werden, steht im Banner
trotzdem, der Flug sei ohne sie gelaufen.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta

DOWNLOAD = "radar.friesenflieger.de/download"

#: Erste Kniebrett-Fassung, die ihre Version überhaupt meldet. Steht auch im Frontend
#: (`_PAKET_ERSTE_MELDENDE` in index.html); `test_paket_hinweis.py` hält beide aneinander.
PAKET_ERSTE_MELDENDE = "2.0.0"

#: Kürzere Verbindungen sind ein Verbindungstest, kein Flug.
_MIN_FLUG_MIN = 5
#: Push frühestens so lange nach dem Ende: Bis dahin gilt ein Abbruch als derselbe Flug
#: (``VATSIM_REJOIN_DEBOUNCE_SEC``), und er könnte noch mit Brügge weitergehen.
_PUSH_AB = timedelta(minutes=15)
#: Und spätestens so lange danach. Stand der Server, soll nichts Altes nachkommen.
_PUSH_BIS = timedelta(minutes=90)

_ALT = ("bruegge_alt", "kniebrett_alt")

#: Die Fassung meldet das Gerät des Piloten, und sie landet im Banner und in der Push-Meldung.
#: Eine Brügge lässt sich einem fremden Piloten unterschieben (gefälschte Position, s. CLAUDE.md
#: „Die Brügge-Position ist fälschbar“) -- ohne diese Schranke stünde beliebiger Text in einer
#: Meldung, die von FriesenRadar zu kommen scheint.
_VERSION = re.compile(r"\d{1,4}(?:\.\d{1,4}){0,3}")


def _fassung(roh) -> str | None:
    """Die gemeldete Fassung, wenn sie wie eine aussieht -- sonst ``None`` (kein Urteil)."""
    v = str(roh or "").strip()
    return v if _VERSION.fullmatch(v) else None


def version_kleiner(a: str | None, b: str | None) -> bool:
    """Zahlenweiser Vergleich. Als Zeichenkette wäre ``"1.10.0" < "1.9.0"`` -- also genau
    verkehrt herum."""
    def teile(v: str | None) -> list[int]:
        try:
            return [int(x) for x in str(v or "").split(".")]
        except ValueError:
            return []
    za, zb = teile(a), teile(b)
    for i in range(max(len(za), len(zb))):
        x = za[i] if i < len(za) else 0
        y = zb[i] if i < len(zb) else 0
        if x != y:
            return x < y
    return False


def paket_ist_veraltet(installiert: str | None, aktuell: str | None) -> bool:
    """Spiegelt ``_paketVeraltet`` im Frontend -- s. dortiger Kommentar.

    ``installiert=None`` heißt „älter als 2.0.0", aber nur, wenn überhaupt schon eine
    meldende Fassung ausgeliefert wird. Liegt auf dem Server noch etwas Älteres, meldet auch
    das aktuelle Paket nichts und die Abwesenheit sagt gar nichts.
    """
    if not aktuell:
        return False
    if not installiert:
        return not version_kleiner(aktuell, PAKET_ERSTE_MELDENDE)
    return version_kleiner(installiert, aktuell)


def _paket_zu(simulator: str | None) -> str:
    return "xplane" if str(simulator or "") == "xplane12" else "msfs"


def _sekunde(ts: str) -> str:
    """``2026-10-08T19:28:58.6114062Z`` -> ``2026-10-08T19:28:58Z`` (vergleichbar als Text)."""
    return ts[:19] + "Z"


def _letzter_flug(conn: sqlite3.Connection, cid: int, bis: str | None = None):
    sql = ("SELECT id, logon_time, logoff_time FROM flights WHERE cid = ? "
           "AND logoff_time IS NOT NULL AND superseded_by IS NULL "
           "AND COALESCE(duration_min, 0) >= ? ")
    werte: list = [int(cid), _MIN_FLUG_MIN]
    if bis:
        sql += "AND logoff_time <= ? "
        werte.append(bis)
    return conn.execute(sql + "ORDER BY logon_time DESC LIMIT 1", werte).fetchone()


def maengel(conn: sqlite3.Connection, cid: int, logon: str, aktuell: dict) -> list[dict]:
    """Was fehlte oder war alt, seit der Flug begann? Reihenfolge: Brügge, dann Kniebrett."""
    ab = _sekunde(logon)
    zeilen: list[dict] = []
    b = conn.execute(
        "SELECT simulator, bruegge_version FROM bruegge_zuordnung WHERE cid = ? "
        "AND gesehen_am >= ? ORDER BY gesehen_am DESC LIMIT 1", (int(cid), ab)).fetchone()
    if b is None:
        zeilen.append({"art": "bruegge_fehlt",
                       "text": f"Dein letzter Flug lief ohne FriesenBrügge. Laden unter {DOWNLOAD}"})
    else:
        soll = aktuell.get(_paket_zu(b[0]))
        # Ohne gemeldete Fassung kein Urteil: Ein Hinweis auf Verdacht verbrennt das Vertrauen
        # in alle anderen.
        hat = _fassung(b[1])
        if hat and soll and version_kleiner(hat, soll):
            zeilen.append({"art": "bruegge_alt",
                           "text": f"Deine FriesenBrügge {hat} ist veraltet, aktuell ist "
                                   f"{soll}. Laden unter {DOWNLOAD}"})
    # Das Kniebrett gibt es nur in MSFS 2024. Nennt die Brügge einen anderen Simulator, wird
    # es gar nicht beurteilt.
    if b is not None and b[0] != "msfs2024":
        return zeilen
    # OHNE Zeitgrenze, anders als bei der Brügge: Das Kniebrett meldet sich nur beim Start
    # (``/auth/device``), und es startet mit dem Simulator -- also vor der Anmeldung bei
    # VATSIM. Ein Lebenszeichen WÄHREND des Flugs gibt es nicht. Wer je ein Gerät gebunden
    # hat, hat das Kniebrett; geurteilt wird über die Fassung des zuletzt gesehenen.
    k = conn.execute(
        "SELECT paket_version FROM panel_devices WHERE cid = ? "
        "ORDER BY COALESCE(last_seen_at, created_at) DESC LIMIT 1", (int(cid),)).fetchone()
    soll = aktuell.get("kniebrett")
    if k is not None:
        hat = _fassung(k[0])
        # Gemeldet, aber unlesbar: kein Urteil. Nur GAR NICHTS gemeldet heißt „vor 2.0.0“.
        if (hat or not k[0]) and paket_ist_veraltet(hat, soll):
            zeilen.append({"art": "kniebrett_alt",
                           "text": f"Dein Kniebrett-Paket {hat or 'vor 2.0.0'} ist veraltet, "
                                   f"aktuell ist {soll}. Laden unter {DOWNLOAD}"})
    elif b is not None:
        zeilen.append({"art": "kniebrett_fehlt",
                       "text": f"Für MSFS 2024 gibt es das FriesenKniebrett. Laden unter {DOWNLOAD}"})
    return zeilen


def stand(conn: sqlite3.Connection, cid: int, aktuell: dict) -> dict:
    """Der Banner dieses Piloten: letzter Flug, seine Mängel, und ob er zu zeigen ist."""
    flug = _letzter_flug(conn, cid)
    if flug is None:
        return {"flug_id": None, "zeilen": [], "zeigen": False}
    zeilen = maengel(conn, cid, flug[1], aktuell)
    weg = conn.execute("SELECT weg_flug_id FROM paket_hinweis WHERE cid = ?",
                       (int(cid),)).fetchone()
    weggeklickt = weg is not None and weg[0] is not None and weg[0] >= flug[0]
    return {"flug_id": flug[0], "zeilen": zeilen, "zeigen": bool(zeilen) and not weggeklickt}


def wegklicken(conn: sqlite3.Connection, cid: int, flug_id: int) -> None:
    """Banner für diesen Flug (und alle davor) ausblenden. Nie rückwärts: Ein zweites Gerät,
    das einen älteren Stand wegklickt, holt den neueren nicht zurück."""
    conn.execute(
        "INSERT INTO paket_hinweis (cid, weg_flug_id) VALUES (?, ?) "
        "ON CONFLICT(cid) DO UPDATE SET weg_flug_id = "
        "MAX(COALESCE(paket_hinweis.weg_flug_id, 0), excluded.weg_flug_id)",
        (int(cid), int(flug_id)))
    conn.commit()


def push_merken(conn: sqlite3.Connection, cid: int, flug_id: int) -> None:
    conn.execute(
        "INSERT INTO paket_hinweis (cid, push_flug_id) VALUES (?, ?) "
        "ON CONFLICT(cid) DO UPDATE SET push_flug_id = excluded.push_flug_id",
        (int(cid), int(flug_id)))
    conn.commit()


def push_faellig(conn: sqlite3.Connection, jetzt: datetime, aktuell: dict) -> list[tuple]:
    """``(cid, flug_id, payload)`` für jeden eben beendeten Flug mit VERALTETEM Paket, der
    noch nicht gemeldet wurde. Fehlende Pakete lösen nichts aus."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    von, bis = (jetzt - _PUSH_BIS).strftime(fmt), (jetzt - _PUSH_AB).strftime(fmt)
    cids = [r[0] for r in conn.execute(
        "SELECT DISTINCT cid FROM flights WHERE logoff_time >= ? AND logoff_time <= ? "
        "AND superseded_by IS NULL AND cid IS NOT NULL", (von, bis))]
    faellig = []
    for cid in cids:
        if conn.execute("SELECT 1 FROM flights WHERE cid = ? AND logoff_time IS NULL "
                        "AND superseded_by IS NULL", (cid,)).fetchone():
            continue   # fliegt schon wieder: Geurteilt wird am Ende des neuen Flugs
        flug = _letzter_flug(conn, cid, bis=bis)
        if flug is None or _sekunde(flug[2]) < von:
            continue
        gemeldet = conn.execute("SELECT push_flug_id FROM paket_hinweis WHERE cid = ?",
                                (cid,)).fetchone()
        if gemeldet is not None and gemeldet[0] is not None and gemeldet[0] >= flug[0]:
            continue
        alt = [z["text"] for z in maengel(conn, cid, flug[1], aktuell) if z["art"] in _ALT]
        if alt:
            faellig.append((cid, flug[0], {"title": "FriesenRadar: Paket veraltet 📦",
                                           "body": " ".join(alt), "url": "/"}))
    return faellig
