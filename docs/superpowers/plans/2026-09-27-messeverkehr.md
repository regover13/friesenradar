# Messeverkehr Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Live-Karte von FriesenSpy zeigt für eine kleine, fest hinterlegte Gruppe von
Betrachtern (CID-Allowlist) zusätzlichen, aber vom Server erzeugten Friesen-Verkehr – ununterscheidbar
von echtem Verkehr, sowohl in der Live-Liste als auch auf der Karte –, damit am Messestand der FS
Conference (21.11.2026) nie eine leere Karte zu sehen ist.

**Architecture:** Eine neue, von `live_positions` komplett getrennte Tabelle
(`messeverkehr_flights`, CIDs strikt negativ) trägt die simulierten Flüge. Ein reines
Generator-Modul (`app/messeverkehr.py`) schreibt sie pro Poll-Zyklus fort. Der Poller mischt sie den
ausgehenden `positions`-Daten bei (internes Merkmal `_messeverkehr`), und genau zwei Ausgangsstellen
(`GET /api/live`, SSE-`_event_generator`) filtern sie anhand einer Allowlist-Prüfung heraus bzw.
entfernen das interne Merkmal, bevor Daten den Server verlassen. Keine Frontend-Änderung nötig, weil
die Datenform identisch zu echten Live-Positionen bleibt.

**Tech Stack:** Python 3.11, FastAPI, SQLite (WAL), APScheduler (über den bestehenden Poller),
pytest.

**Spec:** [`docs/superpowers/specs/2026-09-27-messeverkehr-design.md`](../specs/2026-09-27-messeverkehr-design.md)

## Global Constraints

- Simulierte Flüge bekommen **immer `cid < 0`** — nie 0, nie positiv.
- Simulierte Flüge werden **nie** in `live_positions`, `flights`, `position_history`,
  `statsim_cache`, `statsim_position_history` oder eine Event-Wertung geschrieben.
- Das interne Merkmal `_messeverkehr` (bzw. das entsprechende Dict-Feld) verlässt den Server **nie**
  — es wird an jeder Ausgangsstelle entfernt, auch für berechtigte Betrachter.
- Keine Datenbank-Transaktion umspannt einen Netzabruf (hier ohnehin irrelevant, da der Generator
  keine Netzzugriffe macht — trotzdem: `conn.commit()` zeitnah, keine offene Transaktion über
  mehrere Funktionsaufrufe halten).
- Standard-Verbindungsaufbau ausschließlich über `get_connection(settings.DB_PATH)` (WAL,
  `busy_timeout`, `row_factory=sqlite3.Row`) — nie `sqlite3.connect()` direkt.
- Admin-Endpunkte hinter `require_admin(request)`, wie alle bestehenden `/api/admin/*`-Routen.
- Neue Tabellen als `CREATE TABLE IF NOT EXISTS` in der bestehenden `_DDL`-Zeichenkette
  (`app/database.py`), nicht als separate Migration-Datei — dem Muster der übrigen Tabellen dort
  folgend.

## Review Focus

- **Kein `viewer_cid`** (nicht eingeloggt / Board-Login aus): `cid_hat_messeverkehr_erlaubnis` muss
  bei `None` sicher `False` liefern, nicht werfen — sonst sehen nicht angemeldete Besucher der
  öffentlichen Seite plötzlich gar keine Live-Daten mehr (500 statt leerer Liste).
- **Feature-Flag aus** (Vorgabe): `advance_messeverkehr` darf dann nichts erzeugen, und die
  Ausgangsstellen dürfen dann auch für erlaubte CIDs nichts beimischen — sonst bleibt eine alte
  Momentaufnahme in `messeverkehr_flights` stehen und taucht wieder auf, sobald jemand die Prüfung
  umgeht.
- **Callsign-Kollision mit echtem Verkehr:** Ein simulierter Flug darf nie ein Callsign wählen, das
  gerade in `live_positions` (echt) vorkommt — sonst erscheinen zwei Flugzeuge mit demselben Rufzeichen
  auf derselben Karte, was sofort auffällt.
- **SSE-Reconnect mitten im Poll-Zyklus:** `viewer_cid`/Berechtigung wird beim Verbindungsaufbau
  einmal ermittelt (wie `viewer_cid` es heute schon tut) — eine nachträgliche Änderung der Allowlist
  wirkt erst nach Reconnect. Das ist gewollt (kein Redesign nötig), muss aber nicht heimlich anders
  funktionieren als bei `viewer_cid`.
- **`/api/traffic` (Fremdverkehr) bleibt unberührt:** Dieser Endpunkt speist sich aus
  `poller.traffic_snapshot` (VATSIM-Fremdverkehr), einer komplett anderen Quelle als
  `messeverkehr_flights` — ein Test muss zeigen, dass dort nichts Simuliertes auftaucht.

---

## Task 1: Datenbank-Schema und Grundfunktionen

**Files:**
- Modify: `app/database.py` (DDL-Block ab Zeile 101, direkt nach den `position_history`-Indizes;
  neue Funktionen ans Ende der Datei anhängen, wie bei `get_live_positions`/`cid_ist_authentifiziert`
  um Zeile 2879 ff.)
- Test: `tests/test_messeverkehr_db.py`

**Interfaces:**
- Produziert für Task 2/3/4:
  - `get_messeverkehr_positions(conn: sqlite3.Connection) -> list[dict]`
  - `replace_messeverkehr_positions(conn: sqlite3.Connection, flights: list[dict]) -> None`
  - `cid_hat_messeverkehr_erlaubnis(conn: sqlite3.Connection, cid: int | None) -> bool`
  - `list_messeverkehr_erlaubt(conn: sqlite3.Connection) -> list[dict]`
  - `add_messeverkehr_erlaubt(conn: sqlite3.Connection, cid: int, von: str | None) -> None`
  - `remove_messeverkehr_erlaubt(conn: sqlite3.Connection, cid: int) -> None`
  - `ist_messeverkehr_aktiv(conn: sqlite3.Connection) -> bool`
  - `set_messeverkehr_aktiv(conn: sqlite3.Connection, aktiv: bool) -> None`

- [ ] **Step 1: Schema-Test schreiben (schlägt fehl, Tabellen fehlen noch)**

```python
# tests/test_messeverkehr_db.py
import sqlite3

import pytest

from app.database import (
    init_db,
    get_connection,
    get_messeverkehr_positions,
    replace_messeverkehr_positions,
    cid_hat_messeverkehr_erlaubnis,
    list_messeverkehr_erlaubt,
    add_messeverkehr_erlaubt,
    remove_messeverkehr_erlaubt,
    ist_messeverkehr_aktiv,
    set_messeverkehr_aktiv,
)


@pytest.fixture
def conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    c = get_connection(db_path)
    yield c
    c.close()


def test_messeverkehr_positions_leer_ohne_daten(conn):
    assert get_messeverkehr_positions(conn) == []


def test_replace_messeverkehr_positions_ersetzt_bestand(conn):
    flug = {
        "cid": -1, "callsign": "FRS801", "aircraft": "C172",
        "departure": "EDXW", "arrival": "EDHL", "latitude": 54.1,
        "longitude": 8.3, "altitude": 3500, "groundspeed": 110,
        "heading": 90, "logon_time": "2026-11-21T10:00:00Z",
        "updated_at": "2026-11-21T10:05:00Z", "name": "Messe-Friese 1",
    }
    replace_messeverkehr_positions(conn, [flug])
    conn.commit()
    rows = get_messeverkehr_positions(conn)
    assert len(rows) == 1
    assert rows[0]["cid"] == -1
    assert rows[0]["callsign"] == "FRS801"

    # Ein zweiter Aufruf ERSETZT den Bestand, haengt nicht an.
    replace_messeverkehr_positions(conn, [])
    conn.commit()
    assert get_messeverkehr_positions(conn) == []


def test_messeverkehr_positions_erzwingt_negative_cid(conn):
    flug = {
        "cid": 5, "callsign": "FRS802", "aircraft": "C172",
        "departure": "EDXW", "arrival": "EDHL", "latitude": 54.1,
        "longitude": 8.3, "altitude": 3500, "groundspeed": 110,
        "heading": 90, "logon_time": "2026-11-21T10:00:00Z",
        "updated_at": "2026-11-21T10:05:00Z", "name": "Messe-Friese 2",
    }
    with pytest.raises(ValueError, match="cid"):
        replace_messeverkehr_positions(conn, [flug])


def test_erlaubnis_ohne_eintrag_ist_false(conn):
    assert cid_hat_messeverkehr_erlaubnis(conn, 123456) is False


def test_erlaubnis_none_cid_ist_false(conn):
    assert cid_hat_messeverkehr_erlaubnis(conn, None) is False


def test_add_list_remove_messeverkehr_erlaubt(conn):
    add_messeverkehr_erlaubt(conn, 123456, "Tobias")
    conn.commit()
    assert cid_hat_messeverkehr_erlaubnis(conn, 123456) is True
    eintraege = list_messeverkehr_erlaubt(conn)
    assert len(eintraege) == 1
    assert eintraege[0]["cid"] == 123456
    assert eintraege[0]["hinzugefuegt_von"] == "Tobias"

    remove_messeverkehr_erlaubt(conn, 123456)
    conn.commit()
    assert cid_hat_messeverkehr_erlaubnis(conn, 123456) is False
    assert list_messeverkehr_erlaubt(conn) == []


def test_messeverkehr_aktiv_default_false(conn):
    assert ist_messeverkehr_aktiv(conn) is False


def test_set_messeverkehr_aktiv(conn):
    set_messeverkehr_aktiv(conn, True)
    conn.commit()
    assert ist_messeverkehr_aktiv(conn) is True
    set_messeverkehr_aktiv(conn, False)
    conn.commit()
    assert ist_messeverkehr_aktiv(conn) is False
```

- [ ] **Step 2: Test laufen lassen, muss fehlschlagen**

Run: `pytest tests/test_messeverkehr_db.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_messeverkehr_positions'`

- [ ] **Step 3: DDL ergänzen**

In `app/database.py`, direkt nach den Indizes von `position_history` (nach Zeile 114,
`CREATE INDEX IF NOT EXISTS idx_flights_cid ON flights(cid);`) in die `_DDL`-Zeichenkette einfügen:

```sql
CREATE TABLE IF NOT EXISTS messeverkehr_flights (
    cid          INTEGER PRIMARY KEY,
    callsign     TEXT,
    aircraft     TEXT,
    departure    TEXT,
    arrival      TEXT,
    latitude     REAL,
    longitude    REAL,
    altitude     INTEGER,
    groundspeed  INTEGER,
    heading      INTEGER,
    logon_time   TEXT,
    updated_at   TEXT,
    name         TEXT
);

CREATE TABLE IF NOT EXISTS messeverkehr_erlaubt (
    cid              INTEGER PRIMARY KEY,
    hinzugefuegt_am  TEXT NOT NULL,
    hinzugefuegt_von TEXT
);
```

- [ ] **Step 4: Funktionen implementieren**

Ans Ende von `app/database.py` anhängen:

```python
# ---------------------------------------------------------------------------
# Messeverkehr (docs/superpowers/specs/2026-09-27-messeverkehr-design.md)
# ---------------------------------------------------------------------------

def get_messeverkehr_positions(conn: sqlite3.Connection) -> list[dict]:
    """Aktuelle simulierte Flüge — gleiche Feldform wie get_live_positions()."""
    rows = conn.execute("SELECT * FROM messeverkehr_flights").fetchall()
    return [_row_to_dict(r) for r in rows]


def replace_messeverkehr_positions(conn: sqlite3.Connection, flights: list[dict]) -> None:
    """Ersetzt den kompletten Bestand simulierter Flüge (kein commit).

    Jede cid MUSS negativ sein — das ist die einzige Schranke, die verhindert, dass ein
    simulierter Flug je mit einer echten VATSIM-CID kollidiert oder in einer Stelle landet,
    die cid > 0 voraussetzt.
    """
    for f in flights:
        if f["cid"] >= 0:
            raise ValueError(f"messeverkehr cid muss negativ sein, war {f['cid']!r}")
    conn.execute("DELETE FROM messeverkehr_flights")
    conn.executemany(
        "INSERT INTO messeverkehr_flights "
        "(cid, callsign, aircraft, departure, arrival, latitude, longitude, altitude, "
        " groundspeed, heading, logon_time, updated_at, name) "
        "VALUES (:cid, :callsign, :aircraft, :departure, :arrival, :latitude, :longitude, "
        " :altitude, :groundspeed, :heading, :logon_time, :updated_at, :name)",
        flights,
    )


def cid_hat_messeverkehr_erlaubnis(conn: sqlite3.Connection, cid: int | None) -> bool:
    """True, wenn diese CID den Messeverkehr sehen darf. None → immer False."""
    if cid is None:
        return False
    row = conn.execute(
        "SELECT 1 FROM messeverkehr_erlaubt WHERE cid = ?", (cid,)
    ).fetchone()
    return row is not None


def list_messeverkehr_erlaubt(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT cid, hinzugefuegt_am, hinzugefuegt_von FROM messeverkehr_erlaubt "
        "ORDER BY hinzugefuegt_am"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def add_messeverkehr_erlaubt(conn: sqlite3.Connection, cid: int, von: str | None) -> None:
    """Fügt eine CID zur Messeverkehr-Allowlist hinzu (kein commit)."""
    conn.execute(
        "INSERT INTO messeverkehr_erlaubt (cid, hinzugefuegt_am, hinzugefuegt_von) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(cid) DO UPDATE SET hinzugefuegt_am = excluded.hinzugefuegt_am, "
        "hinzugefuegt_von = excluded.hinzugefuegt_von",
        (cid, _now_utc(), von),
    )


def remove_messeverkehr_erlaubt(conn: sqlite3.Connection, cid: int) -> None:
    """Entfernt eine CID von der Messeverkehr-Allowlist (kein commit)."""
    conn.execute("DELETE FROM messeverkehr_erlaubt WHERE cid = ?", (cid,))


def ist_messeverkehr_aktiv(conn: sqlite3.Connection) -> bool:
    return get_app_setting(conn, "messeverkehr_enabled", "0") == "1"


def set_messeverkehr_aktiv(conn: sqlite3.Connection, aktiv: bool) -> None:
    """Schaltet den Messeverkehr an/aus (kein commit)."""
    set_app_setting(conn, "messeverkehr_enabled", "1" if aktiv else "0")
```

`_now_utc` und `get_app_setting`/`set_app_setting` existieren bereits in `app/database.py`
(siehe `set_app_setting` um Zeile 1729) — nicht neu schreiben, nur verwenden.

- [ ] **Step 5: Test laufen lassen, muss bestehen**

Run: `pytest tests/test_messeverkehr_db.py -v`
Expected: PASS (9 Tests)

- [ ] **Step 6: Commit**

```bash
git add app/database.py tests/test_messeverkehr_db.py
git commit -m "feat: Datenbankgrundlage fuer simulierten Messeverkehr"
```

---

## Task 2: Generator-Modul

**Files:**
- Create: `app/messeverkehr.py`
- Test: `tests/test_messeverkehr_generator.py`

**Interfaces:**
- Consumes: `get_messeverkehr_positions`, `replace_messeverkehr_positions` (Task 1) —
  wird von Task 3 (Poller) aufgerufen, nicht direkt von hier.
- Produziert für Task 3:
  - `advance_messeverkehr(conn: sqlite3.Connection, jetzt: datetime, echte_callsigns: set[str]) -> list[dict]`
    (liest den bisherigen Bestand über `get_messeverkehr_positions`, schreibt den neuen über
    `replace_messeverkehr_positions`, gibt den neuen Bestand zusätzlich zurück)

- [ ] **Step 1: Test für einen einzelnen Flug-Fortschritt schreiben**

```python
# tests/test_messeverkehr_generator.py
from datetime import datetime, timedelta, timezone

import pytest

from app.database import (
    init_db, get_connection, get_messeverkehr_positions, replace_messeverkehr_positions,
)
from app.messeverkehr import advance_messeverkehr, MESSEVERKEHR_FLUGPLAETZE, ZIEL_ANZAHL_FLUEGE


@pytest.fixture
def conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    c = get_connection(db_path)
    yield c
    c.close()


def test_advance_ohne_bestand_erzeugt_neue_fluege(conn):
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    assert len(ergebnis) == ZIEL_ANZAHL_FLUEGE
    for flug in ergebnis:
        assert flug["cid"] < 0
        assert flug["callsign"].startswith("FRS")
        assert flug["departure"] in MESSEVERKEHR_FLUGPLAETZE
        assert flug["arrival"] in MESSEVERKEHR_FLUGPLAETZE
        assert flug["departure"] != flug["arrival"]


def test_advance_vermeidet_kollision_mit_echtem_callsign(conn):
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    # Alle "billigen" ersten Nummern eines Laufs als real belegt vortaeuschen, um zu pruefen,
    # dass der Generator ausweicht statt zu kollidieren.
    belegt = {f"FRS{800 + i}" for i in range(ZIEL_ANZAHL_FLUEGE)}
    ergebnis = advance_messeverkehr(conn, jetzt, echte_callsigns=belegt)
    conn.commit()
    callsigns = {f["callsign"] for f in ergebnis}
    assert callsigns.isdisjoint(belegt)


def test_advance_bewegt_bestehenden_flug_weiter(conn):
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    erster = advance_messeverkehr(conn, jetzt, echte_callsigns=set())
    conn.commit()
    start_lat = erster[0]["latitude"]
    start_lon = erster[0]["longitude"]

    spaeter = jetzt + timedelta(seconds=15)
    zweiter = advance_messeverkehr(conn, spaeter, echte_callsigns=set())
    conn.commit()
    gleicher_flug = next(f for f in zweiter if f["cid"] == erster[0]["cid"])
    # Nach 15s Flugzeit muss sich die Position sichtbar veraendert haben.
    assert (gleicher_flug["latitude"], gleicher_flug["longitude"]) != (start_lat, start_lon)


def test_advance_haelt_bestand_konstant_ueber_viele_zyklen(conn):
    jetzt = datetime(2026, 11, 21, 10, 0, 0, tzinfo=timezone.utc)
    for i in range(50):
        ergebnis = advance_messeverkehr(conn, jetzt + timedelta(seconds=15 * i),
                                          echte_callsigns=set())
        conn.commit()
        assert len(ergebnis) == ZIEL_ANZAHL_FLUEGE
```

- [ ] **Step 2: Test laufen lassen, muss fehlschlagen**

Run: `pytest tests/test_messeverkehr_generator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.messeverkehr'`

- [ ] **Step 3: Modul implementieren**

```python
# app/messeverkehr.py
"""Generator fuer simulierten Friesen-Verkehr auf der Live-Karte (Messestand-Modus).

Reine Funktionen, kein Netzzugriff: berechnet Positionen entlang einer Punkt-zu-Punkt-Strecke
zwischen zwei Flugplaetzen und schreibt sie ueber app.database in eine eigene, von echten Daten
komplett getrennte Tabelle. Siehe docs/superpowers/specs/2026-09-27-messeverkehr-design.md.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timezone

from app.database import get_messeverkehr_positions, replace_messeverkehr_positions
from app.geo import haversine

# Feste Liste norddeutscher/friesischer Flugplaetze fuer plausible Kurzstrecken.
MESSEVERKEHR_FLUGPLAETZE = {
    "EDXW": (54.1826, 8.6875),   # Wyk auf Foehr
    "EDXH": (54.9098, 8.3406),   # Helgoland-Duene
    "EDHL": (53.8022, 10.7192),  # Luebeck
    "EDHF": (54.1147, 9.5350),   # Itzehoe-Hungriger Wolf
    "EDXR": (54.6725, 8.9433),   # Husum
    "EDVE": (52.3461, 10.5561),  # Braunschweig
}

ZIEL_ANZAHL_FLUEGE = 3
_REISEGESCHWINDIGKEIT_KT = 110.0
_REISEHOEHE_FT = 3500
_KT_IN_KM_PRO_S = 1.852 / 3600.0

# Synthetische CIDs: fest belegter, garantiert negativer Bereich, ein Slot je Ziel-Flug.
_CID_BASIS = -900000


def _synthetischer_pilotenname(slot: int) -> str:
    namen = ["Messe-Friese Nord", "Messe-Friese Sued", "Messe-Friese Ost",
             "Messe-Friese West", "Messe-Friese Mitte"]
    return namen[slot % len(namen)]


def _freies_callsign(slot: int, belegt: set[str]) -> str:
    """Erstes freies FRS-Callsign ab einer slot-abhaengigen Basisnummer.

    Weicht auf die naechste Nummer aus, falls sie gerade von einem ECHTEN Flug belegt ist
    (Review Focus: Callsign-Kollision mit echtem Verkehr).
    """
    basis = 800 + slot * 10
    for versuch in range(10):
        kandidat = f"FRS{basis + versuch}"
        if kandidat not in belegt:
            return kandidat
    # Praktisch unerreichbar (10 Versuche je Slot), aber kein Endlos-Risiko:
    return f"FRS{basis}X{random.randint(0, 99)}"


def _neuer_flug(slot: int, jetzt: datetime, belegt: set[str]) -> dict:
    platzcodes = list(MESSEVERKEHR_FLUGPLAETZE.keys())
    start, ziel = random.sample(platzcodes, 2)
    lat0, lon0 = MESSEVERKEHR_FLUGPLAETZE[start]
    return {
        "cid": _CID_BASIS - slot,
        "callsign": _freies_callsign(slot, belegt),
        "aircraft": "C172",
        "departure": start,
        "arrival": ziel,
        "latitude": lat0,
        "longitude": lon0,
        "altitude": _REISEHOEHE_FT,
        "groundspeed": int(_REISEGESCHWINDIGKEIT_KT),
        "heading": 0,
        "logon_time": jetzt.isoformat().replace("+00:00", "Z"),
        "updated_at": jetzt.isoformat().replace("+00:00", "Z"),
        "name": _synthetischer_pilotenname(slot),
        "_fortschritt_km": 0.0,
    }


def _fortschreiben(flug: dict, delta_s: float, jetzt: datetime) -> dict:
    lat0, lon0 = MESSEVERKEHR_FLUGPLAETZE[flug["departure"]]
    lat1, lon1 = MESSEVERKEHR_FLUGPLAETZE[flug["arrival"]]
    strecke_km = haversine(lat0, lon0, lat1, lon1) or 0.001

    fortschritt_km = flug.get("_fortschritt_km", 0.0) + delta_s * _KT_IN_KM_PRO_S * _REISEGESCHWINDIGKEIT_KT
    anteil = min(fortschritt_km / strecke_km, 1.0)

    lat = lat0 + (lat1 - lat0) * anteil
    lon = lon0 + (lon1 - lon0) * anteil
    kurs = math.degrees(math.atan2(lon1 - lon0, lat1 - lat0)) % 360

    flug = dict(flug)
    flug["latitude"] = lat
    flug["longitude"] = lon
    flug["heading"] = int(kurs)
    flug["updated_at"] = jetzt.isoformat().replace("+00:00", "Z")
    flug["_fortschritt_km"] = fortschritt_km
    flug["_angekommen"] = anteil >= 1.0
    return flug


def advance_messeverkehr(conn, jetzt: datetime, echte_callsigns: set[str]) -> list[dict]:
    """Schreibt den simulierten Verkehr um einen Schritt fort und persistiert ihn.

    ``echte_callsigns`` sind die Rufzeichen des GERADE echten Verkehrs (aus
    ``get_live_positions``) — neue simulierte Flüge weichen ihnen aus.
    Gibt den neuen Bestand als Liste von Dicts zurück, OHNE das interne Feld
    ``_fortschritt_km``/``_angekommen`` (das bleibt Sache dieses Moduls).
    """
    bestand = {f["cid"]: dict(f, _fortschritt_km=0.0) for f in get_messeverkehr_positions(conn)}
    belegte_slots = {(c - _CID_BASIS) * -1: True for c in bestand}  # slot = -(cid - basis)

    aktualisiert: dict[int, dict] = {}
    for slot in range(ZIEL_ANZAHL_FLUEGE):
        cid = _CID_BASIS - slot
        vorher = bestand.get(cid)
        if vorher is None:
            aktualisiert[cid] = _neuer_flug(slot, jetzt, echte_callsigns)
            continue
        nachher = _fortschreiben(vorher, delta_s=15.0, jetzt=jetzt)
        if nachher.pop("_angekommen", False):
            aktualisiert[cid] = _neuer_flug(slot, jetzt, echte_callsigns)
        else:
            aktualisiert[cid] = nachher

    ergebnis = []
    for flug in aktualisiert.values():
        gespeichert = {k: v for k, v in flug.items() if not k.startswith("_")}
        ergebnis.append(gespeichert)

    replace_messeverkehr_positions(conn, ergebnis)
    return ergebnis
```

- [ ] **Step 4: Test laufen lassen, muss bestehen**

Run: `pytest tests/test_messeverkehr_generator.py -v`
Expected: PASS (4 Tests)

- [ ] **Step 5: Commit**

```bash
git add app/messeverkehr.py tests/test_messeverkehr_generator.py
git commit -m "feat: Generator fuer simulierten Messeverkehr"
```

---

## Task 3: Poller-Integration

**Files:**
- Modify: `app/poller.py:1637-1668` (nach `conn.commit()`, vor `self.broadcast_sse(...)`)
- Test: `tests/test_messeverkehr_poller.py`

**Interfaces:**
- Consumes: `advance_messeverkehr` (Task 2), `ist_messeverkehr_aktiv` (Task 1)
- Produziert: `broadcast_sse({"type": "positions", "data": [...]})` enthält jetzt zusätzlich
  Einträge mit `entry["_messeverkehr"] = True`, wenn das Feature an ist — Task 4 konsumiert dieses
  Merkmal.

- [ ] **Step 1: Test für die Poller-Erweiterung schreiben**

Poller-Tests laufen in dieser Codebasis gegen echte `VatsimPoller`-Instanzen mit gemocktem
VATSIM-Client (siehe bestehende `tests/test_poller_*.py` für das genaue Fixture-Muster). Da der
Zyklus komplex ist, wird hier stattdessen die neu eingefügte Codezeile isoliert getestet, indem
direkt die Stelle im Modul geprüft wird, an der die Liste zusammengebaut wird — dafür wird die
Zusammenbau-Logik als eigene, kleine Funktion `_live_positions_mit_messeverkehr` extrahiert statt
inline im Zyklus zu stehen:

```python
# tests/test_messeverkehr_poller.py
from app.database import (
    init_db, get_connection, set_messeverkehr_aktiv, replace_messeverkehr_positions,
)
from app.poller import _live_positions_mit_messeverkehr


def _conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return get_connection(db_path)


def test_ohne_flag_bleibt_liste_unveraendert(tmp_path):
    conn = _conn(tmp_path)
    echte = [{"cid": 123, "callsign": "FRS1", "latitude": 1.0, "longitude": 2.0}]
    ergebnis = _live_positions_mit_messeverkehr(conn, echte)
    assert ergebnis == echte
    conn.close()


def test_mit_flag_werden_simulierte_fluege_markiert_beigemischt(tmp_path):
    conn = _conn(tmp_path)
    set_messeverkehr_aktiv(conn, True)
    conn.commit()
    echte = [{"cid": 123, "callsign": "FRS1", "latitude": 1.0, "longitude": 2.0}]
    ergebnis = _live_positions_mit_messeverkehr(conn, echte)
    assert len(ergebnis) > len(echte)
    simulierte = [e for e in ergebnis if e.get("_messeverkehr")]
    assert len(simulierte) > 0
    assert all(e["cid"] < 0 for e in simulierte)
    conn.close()


def test_traffic_snapshot_bleibt_von_messeverkehr_getrennt():
    """Review Focus: /api/traffic speist sich aus poller.traffic_snapshot, einer ANDEREN
    Quelle als live_positions. Textbasierte Regressionsprobe nach dem Muster von
    test_kutter_eventloop.py (CLAUDE.md) -- prüft, dass die Zeile, die traffic_snapshot setzt,
    NICHT über _live_positions_mit_messeverkehr läuft."""
    import inspect
    import app.poller as poller_modul

    quelltext = inspect.getsource(poller_modul)
    zeilen = quelltext.splitlines()
    treffer = [z for z in zeilen if "traffic_snapshot" in z and "=" in z and "def " not in z]
    assert treffer, "keine Zuweisung an traffic_snapshot gefunden -- Testannahme prüfen"
    assert not any("_live_positions_mit_messeverkehr" in z for z in treffer)
```

- [ ] **Step 2: Test laufen lassen, muss fehlschlagen**

Run: `pytest tests/test_messeverkehr_poller.py -v`
Expected: FAIL — `ImportError: cannot import name '_live_positions_mit_messeverkehr'`

- [ ] **Step 3: Funktion in `app/poller.py` ergänzen und in den Zyklus einhängen**

Oberhalb von `class VatsimPoller` (oder direkt darüber, als Modulfunktion) einfügen:

```python
def _live_positions_mit_messeverkehr(conn, live_positions: list[dict]) -> list[dict]:
    """Mischt simulierten Messeverkehr in die echten Live-Positionen, wenn das Feature an ist.

    Jeder beigemischte Eintrag traegt ``_messeverkehr: True`` -- dieses Merkmal verlaesst den
    Server nie unveraendert (siehe Sichtbarkeitsfilter in app/main.py, Task 4 des Plans).
    """
    from app.database import ist_messeverkehr_aktiv
    from app.messeverkehr import advance_messeverkehr
    from datetime import datetime, timezone

    if not ist_messeverkehr_aktiv(conn):
        return live_positions

    echte_callsigns = {p.get("callsign") for p in live_positions if p.get("callsign")}
    simulierte = advance_messeverkehr(conn, datetime.now(timezone.utc), echte_callsigns)
    for s in simulierte:
        s["_messeverkehr"] = True
    return live_positions + simulierte
```

In der bestehenden Zyklus-Methode (Zeile 1640-1668) direkt nach `live_positions = get_live_positions(conn)`
einfügen:

```python
                live_positions = get_live_positions(conn)
                live_positions = _live_positions_mit_messeverkehr(conn, live_positions)
```

(Die Zeile `self.friesen_snapshot = list(live_positions)` danach bleibt unverändert — sie
verwendet jetzt automatisch die gemischte Liste. Das ist gewollt: `/api/traffic` (Fremdverkehr,
`traffic_snapshot`) ist eine ANDERE Quelle und bleibt unberührt, siehe Review Focus im Spec.)

- [ ] **Step 4: Test laufen lassen, muss bestehen**

Run: `pytest tests/test_messeverkehr_poller.py -v`
Expected: PASS (3 Tests)

- [ ] **Step 5: Bestehende Poller-Tests laufen lassen (Regression)**

Run: `pytest tests/test_poller_*.py -v`
Expected: PASS — die Änderung darf am Verhalten ohne Feature-Flag nichts ändern (Test 1 oben
sichert das bereits ab, das ist die Regressionsprobe im echten Poller-Kontext).

- [ ] **Step 6: Commit**

```bash
git add app/poller.py tests/test_messeverkehr_poller.py
git commit -m "feat: Poller mischt simulierten Messeverkehr in Live-Broadcast"
```

---

## Task 4: Sichtbarkeitsfilter an den Ausgangsstellen

**Files:**
- Modify: `app/main.py:3274-3283` (`GET /api/live`)
- Modify: `app/main.py:3704-3748` (`_event_generator`, SSE)
- Test: `tests/test_messeverkehr_sichtbarkeit.py`

**Interfaces:**
- Consumes: `cid_hat_messeverkehr_erlaubnis` (Task 1), `_current_cid` (bestehend, `app/main.py:4701`)
- Produziert: Ausgelieferte JSON-Positionsdaten enthalten `_messeverkehr` nie mehr — weder als
  Feld noch implizit über die Anwesenheit negativer CIDs bei nicht berechtigten Betrachtern.

- [ ] **Step 1: Test für die Filterfunktion schreiben**

Die Filterlogik wird als eigene, kleine Funktion `_positions_fuer_betrachter` extrahiert, damit sie
ohne vollen HTTP-Request-Aufbau testbar ist:

```python
# tests/test_messeverkehr_sichtbarkeit.py
from app.database import init_db, get_connection, add_messeverkehr_erlaubt
from app.main import _positions_fuer_betrachter


def _conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return get_connection(db_path)


_POSITIONEN = [
    {"cid": 123, "callsign": "FRS1", "latitude": 1.0},
    {"cid": -900000, "callsign": "FRS801", "latitude": 2.0, "_messeverkehr": True},
]


def test_nicht_berechtigter_betrachter_sieht_nur_echte(tmp_path):
    conn = _conn(tmp_path)
    ergebnis = _positions_fuer_betrachter(conn, _POSITIONEN, viewer_cid=999999)
    assert len(ergebnis) == 1
    assert ergebnis[0]["cid"] == 123
    conn.close()


def test_kein_viewer_cid_sieht_nur_echte(tmp_path):
    conn = _conn(tmp_path)
    ergebnis = _positions_fuer_betrachter(conn, _POSITIONEN, viewer_cid=None)
    assert len(ergebnis) == 1
    assert ergebnis[0]["cid"] == 123
    conn.close()


def test_berechtigter_betrachter_sieht_beide_ohne_markierung(tmp_path):
    conn = _conn(tmp_path)
    add_messeverkehr_erlaubt(conn, 123456, "Test")
    conn.commit()
    ergebnis = _positions_fuer_betrachter(conn, _POSITIONEN, viewer_cid=123456)
    assert len(ergebnis) == 2
    assert all("_messeverkehr" not in e for e in ergebnis)
```

- [ ] **Step 2: Test laufen lassen, muss fehlschlagen**

Run: `pytest tests/test_messeverkehr_sichtbarkeit.py -v`
Expected: FAIL — `ImportError: cannot import name '_positions_fuer_betrachter'`

- [ ] **Step 3: Filterfunktion in `app/main.py` ergänzen**

In der Nähe von `_current_cid` (um Zeile 4701) einfügen:

```python
def _positions_fuer_betrachter(conn, positions: list[dict], viewer_cid: int | None) -> list[dict]:
    """Filtert eine Liste von Live-Positionen für einen konkreten Betrachter.

    Wer nicht auf der Messeverkehr-Allowlist steht, bekommt ``_messeverkehr``-Einträge gar
    nicht erst zu sehen. Wer berechtigt ist, bekommt sie — aber ohne das interne Merkmal, das
    den Server sonst nie verlassen darf (siehe Global Constraints im Plan).
    """
    from app.database import cid_hat_messeverkehr_erlaubnis

    darf_sehen = cid_hat_messeverkehr_erlaubnis(conn, viewer_cid)
    ergebnis = []
    for p in positions:
        if p.get("_messeverkehr") and not darf_sehen:
            continue
        if "_messeverkehr" in p:
            p = {k: v for k, v in p.items() if k != "_messeverkehr"}
        ergebnis.append(p)
    return ergebnis
```

- [ ] **Step 4: `GET /api/live` anpassen**

```python
@app.get("/api/live")
async def get_live(request: Request):
    """Aktuelle Live-Positionen aller online Friesen."""
    settings = get_settings()
    conn = get_connection(settings.DB_PATH)
    try:
        positions = get_live_positions(conn)
        positions = _live_positions_mit_messeverkehr(conn, positions)
        positions = _positions_fuer_betrachter(conn, positions, _current_cid(request, settings))
    finally:
        conn.close()
    return positions
```

`_live_positions_mit_messeverkehr` aus `app/poller.py` importieren (oben bei den übrigen
`from app.poller import ...`-Importzeilen ergänzen, falls `poller` dort noch nicht in dieser Form
importiert ist).

- [ ] **Step 5: SSE-`_event_generator` anpassen**

Direkt nach der bestehenden Ermittlung von `viewer_cid` (Zeile 3704-3711) eine einmalige
Berechtigungsprüfung ergänzen:

```python
    claims = verify_user_token(request.cookies.get(USER_COOKIE, ""), settings.SECRET_KEY)
    try:
        viewer_cid = int(claims["cid"]) if claims and claims.get("cid") else None
    except (TypeError, ValueError):
        viewer_cid = None

    # Einmal pro Verbindung ermitteln, nicht pro Nachricht (wie viewer_cid selbst).
    _conn_pruef = get_connection(settings.DB_PATH)
    try:
        darf_messeverkehr_sehen = cid_hat_messeverkehr_erlaubnis(_conn_pruef, viewer_cid)
    finally:
        _conn_pruef.close()
```

Und im bestehenden `elif nur_friesen and data.get("type") == "bruegge" and "fremd" in data:`-Zweig
(Zeile 3744-3747) eine weitere Bedingung als eigenen `elif`-Zweig ergänzen, nach demselben Muster.
`darf_messeverkehr_sehen` wurde oben bereits einmal pro Verbindung ermittelt (Global Constraint:
keine Verbindung offen halten) und wird hier nur noch gelesen, ohne erneuten DB-Zugriff:

```python
            elif data.get("type") == "positions":
                roh = data.get("data", [])
                if any(e.get("_messeverkehr") for e in roh):
                    if darf_messeverkehr_sehen:
                        roh = [{k: v for k, v in e.items() if k != "_messeverkehr"} for e in roh]
                    else:
                        roh = [e for e in roh if not e.get("_messeverkehr")]
                    data = {**data, "data": roh}
```

- [ ] **Step 6: Test laufen lassen, muss bestehen**

Run: `pytest tests/test_messeverkehr_sichtbarkeit.py -v`
Expected: PASS (3 Tests)

- [ ] **Step 7: Bestehende SSE- und Live-Tests laufen lassen (Regression)**

Run: `pytest tests/test_kniebrett_strom_filter.py tests/ -k "live or sse" -v`
Expected: PASS — insbesondere darf sich am Verhalten für `viewer_cid=None`
(nicht angemeldete öffentliche Besucher) nichts ändern.

- [ ] **Step 8: Commit**

```bash
git add app/main.py tests/test_messeverkehr_sichtbarkeit.py
git commit -m "feat: Sichtbarkeitsfilter fuer simulierten Messeverkehr (REST + SSE)"
```

---

## Task 5: Admin-API für Allowlist und Feature-Flag

**Files:**
- Modify: `app/main.py` (neue Routen in der Nähe der übrigen `/api/admin/*`-Endpunkte, z. B. bei
  `admin_get_forum_login` um Zeile 4719)
- Test: `tests/test_messeverkehr_admin_api.py`

**Interfaces:**
- Consumes: `list_messeverkehr_erlaubt`, `add_messeverkehr_erlaubt`, `remove_messeverkehr_erlaubt`,
  `ist_messeverkehr_aktiv`, `set_messeverkehr_aktiv` (Task 1), `require_admin` (bestehend)

- [ ] **Step 1: API-Test schreiben**

Admin-Endpunkt-Tests in dieser Codebasis nutzen den FastAPI-`TestClient` mit gesetztem
Admin-Cookie — siehe `tests/test_admin_*.py` für das genaue Login-Fixture (`_admin_client`
o. ä.); hier exemplarisch mit direktem `ADMIN_PASSWORD`-Login über `/api/admin/login`, dem in
diesem Projekt üblichen Weg:

```python
# tests/test_messeverkehr_admin_api.py
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-pw")
    from app.database import init_db
    init_db(db_path)
    from app.config import get_settings
    get_settings.cache_clear()
    c = TestClient(app)
    r = c.post("/api/admin/login", json={"password": "test-admin-pw"})
    assert r.status_code == 200
    return c


def test_flag_default_aus(client):
    r = client.get("/api/admin/messeverkehr")
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert r.json()["erlaubt"] == []


def test_flag_umschalten(client):
    r = client.put("/api/admin/messeverkehr", json={"enabled": True})
    assert r.status_code == 200
    r = client.get("/api/admin/messeverkehr")
    assert r.json()["enabled"] is True


def test_cid_hinzufuegen_und_entfernen(client):
    r = client.post("/api/admin/messeverkehr/erlaubt", json={"cid": 123456, "von": "Tobias"})
    assert r.status_code == 200
    r = client.get("/api/admin/messeverkehr")
    assert {e["cid"] for e in r.json()["erlaubt"]} == {123456}

    r = client.delete("/api/admin/messeverkehr/erlaubt/123456")
    assert r.status_code == 200
    r = client.get("/api/admin/messeverkehr")
    assert r.json()["erlaubt"] == []


def test_ohne_admin_login_401(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-pw")
    from app.database import init_db
    init_db(db_path)
    from app.config import get_settings
    get_settings.cache_clear()
    c = TestClient(app)
    r = c.get("/api/admin/messeverkehr")
    assert r.status_code == 401
```

Hinweis für den Ausführenden: Das exakte Login-Fixture (Pfad `/api/admin/login`, Cookie-Name,
ob `get_settings` wirklich einen `.cache_clear()` besitzt) VOR dem Schreiben dieses Tests gegen
ein bestehendes `tests/test_admin_*.py` abgleichen und an das dort verwendete Muster angleichen —
dort ist die echte, bereits funktionierende Fassung hinterlegt.

- [ ] **Step 2: Test laufen lassen, muss fehlschlagen**

Run: `pytest tests/test_messeverkehr_admin_api.py -v`
Expected: FAIL — 404 auf `/api/admin/messeverkehr`

- [ ] **Step 3: Endpunkte implementieren**

```python
@app.get("/api/admin/messeverkehr")
async def admin_get_messeverkehr(request: Request):
    """Status des simulierten Messeverkehrs: Feature-Flag + Allowlist."""
    require_admin(request)
    conn = get_connection(get_settings().DB_PATH)
    try:
        return {
            "enabled": ist_messeverkehr_aktiv(conn),
            "erlaubt": list_messeverkehr_erlaubt(conn),
        }
    finally:
        conn.close()


@app.put("/api/admin/messeverkehr")
async def admin_set_messeverkehr(request: Request, body: dict = Body(...)):
    """Schaltet den simulierten Messeverkehr an/aus."""
    require_admin(request)
    aktiv = bool(body.get("enabled"))
    conn = get_connection(get_settings().DB_PATH)
    try:
        set_messeverkehr_aktiv(conn, aktiv)
        conn.commit()
        return {"status": "ok", "enabled": aktiv}
    finally:
        conn.close()


@app.post("/api/admin/messeverkehr/erlaubt")
async def admin_add_messeverkehr_erlaubt(request: Request, body: dict = Body(...)):
    """Fügt eine CID zur Messeverkehr-Allowlist hinzu."""
    require_admin(request)
    try:
        cid = int(body.get("cid"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="cid (Zahl) erforderlich")
    von = str(body.get("von") or "").strip() or None
    conn = get_connection(get_settings().DB_PATH)
    try:
        add_messeverkehr_erlaubt(conn, cid, von)
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()


@app.delete("/api/admin/messeverkehr/erlaubt/{cid}")
async def admin_remove_messeverkehr_erlaubt(cid: int, request: Request):
    """Entfernt eine CID von der Messeverkehr-Allowlist."""
    require_admin(request)
    conn = get_connection(get_settings().DB_PATH)
    try:
        remove_messeverkehr_erlaubt(conn, cid)
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()
```

Import-Zeile oben in `app/main.py` bei den übrigen `from app.database import ...`-Namen ergänzen:
`ist_messeverkehr_aktiv, set_messeverkehr_aktiv, list_messeverkehr_erlaubt,
add_messeverkehr_erlaubt, remove_messeverkehr_erlaubt, cid_hat_messeverkehr_erlaubnis`.

- [ ] **Step 4: Test laufen lassen, muss bestehen**

Run: `pytest tests/test_messeverkehr_admin_api.py -v`
Expected: PASS (4 Tests) — ggf. nach Angleichen des Login-Fixtures an das echte Projektmuster
(siehe Hinweis in Step 1).

- [ ] **Step 5: Ganze Suite laufen lassen**

Run: `pytest tests/ -v`
Expected: PASS, keine Regression. **Vorher CLAUDE.md-Regel beachten: keine Datei anfassen, während
die Suite läuft** — dieser Schritt ist der letzte in diesem Plan, danach nichts mehr editieren, bis
er durchgelaufen ist.

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_messeverkehr_admin_api.py
git commit -m "feat: Admin-API fuer Messeverkehr-Allowlist und Feature-Flag"
```

---

## Nach der Implementierung (nicht Teil der Aufgaben, aber vor dem Deploy nötig)

- **Nicht direkt pushen.** Laut `CLAUDE.md` reißt ein Deploy jede offene Sitzung/jedes Kniebrett
  ab — vorher mit dem Nutzer abstimmen, wann (nicht an einem Flugabend).
- **Vor dem Push:** `git fetch` + Rebase auf `origin/main`, `COORDINATION.md` auf parallele
  Änderungen an `app/main.py`/`app/poller.py`/`app/database.py` prüfen.
- **CID der berechtigten Betrachter** (Messe-Team) muss nach dem Deploy über
  `POST /api/admin/messeverkehr/erlaubt` eingetragen werden — das Tablet am Stand braucht dafür
  eine gültige Forum-Login-Session dieser CID.
- **Feature erst kurz vor der FS Conference (21.11.2026) aktivieren** (`PUT /api/admin/messeverkehr`,
  `enabled: true`) und danach wieder abschalten — Vorgabe ist aus.
