# -*- coding: utf-8 -*-
"""Mustername aus der ICAO-Kürzelliste (app/icao_typen.py).

Der Fall, der das erzwungen hat (09.10.2026): P28U ist ein gewöhnliches ICAO-Kürzel, die
Zuladungs-Recherche ging trotzdem leer aus, und ohne ihren Namen wurde Wikipedia gar nicht
gefragt. Der Link `#actype=P28U` zeigte „Zu diesem Kürzel ist kein Muster bekannt“.
"""
from __future__ import annotations

import json
import os
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import icao_typen
from app.database import (
    get_aircraft_type, get_connection, get_payload_research, init_db, mark_payload_research,
)

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)

# Ausschnitt der echten Liste, in ihrer Reihenfolge (Abruf 09.10.2026). Die Füllzeilen geben
# Piper, Dornier und Pilatus das Gewicht, das sie in der ganzen Liste haben.
_ROH = [
    {"Designator": "P28U", "ManufacturerCode": "AICSA", "ModelFullName": "PA-28RT-201T Turbo Arrow 4"},
    {"Designator": "P28U", "ManufacturerCode": "CHINCUL", "ModelFullName": "PA-A-28RT-201T Turbo Arrow 4"},
    {"Designator": "P28U", "ManufacturerCode": "EMBRAER", "ModelFullName": "EMB-711ST Corisco 2 Turbo"},
    {"Designator": "P28U", "ManufacturerCode": "PIPER", "ModelFullName": "PA-28RT-201T Turbo Arrow 4"},
    {"Designator": "PC21", "ManufacturerCode": "PILATUS", "ModelFullName": "E-27"},
    {"Designator": "PC21", "ManufacturerCode": "PILATUS", "ModelFullName": "PC-21"},
    {"Designator": "D228", "ManufacturerCode": "DORNIER", "ModelFullName": "228"},
    {"Designator": "D228", "ManufacturerCode": "HINDUSTAN", "ModelFullName": "228"},
    {"Designator": "D228", "ManufacturerCode": "RUAG", "ModelFullName": "Dornier 228"},
    {"Designator": "HA4T", "ManufacturerCode": "HINDUSTAN", "ModelFullName": "HJT-16 Kiran"},
    {"Designator": "HF24", "ManufacturerCode": "HINDUSTAN", "ModelFullName": "HF-24 Marut"},
    {"Designator": "DHC6", "ManufacturerCode": "DE HAVILLAND CANADA", "ModelFullName": "CC-138 Twin Otter"},
    {"Designator": "DHC6", "ManufacturerCode": "DE HAVILLAND CANADA", "ModelFullName": "DHC-6 Twin Otter"},
    {"Designator": "PZ4M", "ManufacturerCode": "PZL-OKECIE", "ModelFullName": "PZL-104M Wilga 2000"},
    {"Designator": "P28A", "ManufacturerCode": "PIPER", "ModelFullName": "PA-28-140 Cherokee"},
    {"Designator": "PA18", "ManufacturerCode": "PIPER", "ModelFullName": "PA-18 Super Cub"},
    {"Designator": "", "ManufacturerCode": "X", "ModelFullName": "ohne Kürzel"},
    {"Designator": "LEER", "ManufacturerCode": "X", "ModelFullName": ""},
    "kaputt",
]


@pytest.fixture
def liste():
    icao_typen.setzen(icao_typen.aus_rohdaten(_ROH))


def test_p28u_ist_die_turbo_arrow_4_von_piper(liste):
    """Fünf Hersteller führen das Kürzel; gemeint ist Piper, nicht der Lizenzbauer AICSA."""
    assert icao_typen.name_fuer("P28U") == "Piper PA-28RT-201T Turbo Arrow 4"
    assert icao_typen.name_fuer(" p28u ") == "Piper PA-28RT-201T Turbo Arrow 4"


def test_der_name_mit_der_zahl_des_kuerzels_gewinnt(liste):
    """PC21 beginnt in der Liste mit „E-27“, DHC6 mit „CC-138“ -- beides führte am 09.10.2026
    zu falschen Artikeln (DHC6 landete bei der Dash 7)."""
    assert icao_typen.name_fuer("PC21") == "Pilatus PC-21"
    assert icao_typen.name_fuer("DHC6") == "De Havilland Canada DHC-6 Twin Otter"


def test_bei_gleichem_modell_gewinnt_der_hersteller_mit_dem_buchstaben_des_kuerzels(liste):
    """D228: Hindustan steht in der Liste öfter als Dornier, gebaut hat sie Dornier."""
    assert icao_typen.name_fuer("D228") == "Dornier 228"


def test_unbekanntes_kuerzel_hat_keinen_namen_und_keinen_hinweis(liste):
    for code in ("P34A", "SR25", "", None):
        assert icao_typen.name_fuer(code) is None
        assert icao_typen.hinweis_fuer(code) == ""
        assert not icao_typen.bekannt(code)


def test_schreibweise_der_hersteller():
    icao_typen.setzen({"MD11": [["MCDONNELL DOUGLAS", "MD-11"]],
                       "PZ4M": [["PZL-OKECIE", "PZL-104M Wilga 2000"]]})
    assert icao_typen.name_fuer("MD11") == "McDonnell Douglas MD-11"
    assert icao_typen.name_fuer("PZ4M") == "PZL-Okecie PZL-104M Wilga 2000"


def test_unbrauchbare_zeilen_fallen_weg(liste):
    assert icao_typen.anzahl() == 9
    assert not icao_typen.bekannt("LEER")


def test_hinweis_nennt_die_varianten_der_gewichtigste_zuerst(liste):
    h = icao_typen.hinweis_fuer("P28U")
    assert h.startswith("laut ICAO Doc 8643: Piper PA-28RT-201T Turbo Arrow 4")
    assert "Embraer EMB-711ST Corisco 2 Turbo" in h


@pytest.mark.parametrize("code,titel,passt", [
    ("P28U", "Piper PA-28", True),
    ("C82R", "Cessna 182 Skylane", True),      # 182 endet auf 82
    ("DR40", "Robin DR 400", True),            # 400 beginnt mit 40
    ("BE60", "Beech Aircraft Corporation", False),   # Artikel über den Hersteller
    ("P208", "Tecnam", False),
    ("UH1", "Bell 212", False),
    ("AEST", "Piper PA-60", True),             # Kürzel ohne Zahl: nicht prüfbar
    ("P28U", None, False),
])
def test_titel_passt(code, titel, passt):
    assert icao_typen.titel_passt(code, titel) is passt


# ---------------------------------------------------------------------------
# Ablage neben der Datenbank
# ---------------------------------------------------------------------------

def _viele(n=600):
    return [{"Designator": f"X{i:03d}", "ManufacturerCode": "TEST", "ModelFullName": f"T-{i}"}
            for i in range(n)]


def test_auffrischen_legt_ab_und_laden_findet_es_wieder(tmp_path):
    assert icao_typen.faellig(tmp_path)
    assert icao_typen.auffrischen(tmp_path, holen=_viele) == 600
    assert not icao_typen.faellig(tmp_path)
    icao_typen.setzen({})
    assert icao_typen.laden(tmp_path) == 600
    assert icao_typen.name_fuer("X007") == "Test T-7"


def test_eine_unbrauchbare_antwort_ueberschreibt_die_gute_liste_nicht(tmp_path):
    icao_typen.auffrischen(tmp_path, holen=_viele)
    vorher = (tmp_path / icao_typen.DATEINAME).read_bytes()
    with pytest.raises(ValueError):
        icao_typen.auffrischen(tmp_path, holen=lambda: [])
    assert (tmp_path / icao_typen.DATEINAME).read_bytes() == vorher
    assert icao_typen.anzahl() == 600


def test_nach_dreissig_tagen_ist_die_liste_faellig(tmp_path):
    icao_typen.auffrischen(tmp_path, holen=_viele)
    assert not icao_typen.faellig(tmp_path, jetzt_s=time.time() + 29 * 86400)
    assert icao_typen.faellig(tmp_path, jetzt_s=time.time() + 31 * 86400)


def test_fehlende_oder_kaputte_datei_ist_keine_liste(tmp_path):
    assert icao_typen.laden(tmp_path) == 0
    (tmp_path / icao_typen.DATEINAME).write_text("{kaputt", encoding="utf-8")
    assert icao_typen.laden(tmp_path) == 0


# ---------------------------------------------------------------------------
# Muster-Recherche: der Name aus der Liste, wenn die Zuladungs-Recherche keinen hat
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    p = str(tmp_path / "t.db")
    init_db(p)
    return p


def _poller(db_path, tmp_path):
    from app.poller import VatsimPoller
    p = VatsimPoller(db_path=db_path, callsign_prefix="FRS")
    p._photo_dir = Path(tmp_path) / "fotos"
    return p


def _zuladung_leer_ausgegangen(db_path, code):
    c = get_connection(db_path)
    mark_payload_research(c, code, "nichts_gefunden", T0)
    c.commit()
    c.close()


def _wiki(titel):
    def _fake(name, fetch):
        _fake.gefragt = name
        return {"wiki_lang": "de", "wiki_title": titel, "extract": "Text …"}
    _fake.gefragt = None
    return _fake


@pytest.mark.asyncio
async def test_leere_zuladungs_recherche_sperrt_ein_icao_kuerzel_nicht_mehr(
        db, tmp_path, monkeypatch, liste):
    """Der P28U-Fall: früher `nichts_gefunden`, ohne Wikipedia je gefragt zu haben."""
    from app import aircraft_info
    _zuladung_leer_ausgegangen(db, "P28U")
    p = _poller(db, tmp_path)
    monkeypatch.setattr(p, "_now", lambda: T0)
    wiki = _wiki("Piper PA-28")
    monkeypatch.setattr(aircraft_info, "resolve_type", wiki)

    await p._resolve_aircraft_type("P28U")

    assert wiki.gefragt == "Piper PA-28RT-201T Turbo Arrow 4"
    row = get_aircraft_type(get_connection(db), "P28U")
    assert row["fetch_state"] == "ok"
    assert row["wiki_title"] == "Piper PA-28"
    assert row["name"] == "Piper PA-28RT-201T Turbo Arrow 4"
    quelle = get_connection(db).execute(
        "SELECT name_source FROM aircraft_types WHERE type_code = 'P28U'").fetchone()[0]
    assert quelle == "icao"


@pytest.mark.asyncio
async def test_solange_die_zuladungs_recherche_laeuft_wartet_die_liste(
        db, tmp_path, monkeypatch, liste):
    """Der recherchierte Name trifft die geflogene Variante genauer und soll gewinnen."""
    from app import aircraft_info
    p = _poller(db, tmp_path)
    monkeypatch.setattr(p, "_now", lambda: T0)
    monkeypatch.setattr(aircraft_info, "resolve_type",
                        lambda name, fetch: pytest.fail("zu früh gefragt"))

    await p._resolve_aircraft_type("P28U")

    row = get_aircraft_type(get_connection(db), "P28U")
    assert row is None or row["fetch_state"] in (None, "neu")


@pytest.mark.asyncio
async def test_solange_die_liste_geholt_wird_faellt_kein_urteil(db, tmp_path, monkeypatch):
    """Erster Start nach dem Deploy: Die Liste wird noch geholt, die Nachlese läuft schon.
    Dieser Augenblick darf ein bekanntes Kürzel nicht für 30 Tage sperren. Ist der Abruf
    durch -- auch gescheitert --, fällt das Urteil wieder, sonst bliebe es Dauerkandidat."""
    _zuladung_leer_ausgegangen(db, "P28U")
    p = _poller(db, tmp_path)
    monkeypatch.setattr(p, "_now", lambda: T0)
    p._icao_ausstehend = True

    await p._resolve_aircraft_type("P28U")
    row = get_aircraft_type(get_connection(db), "P28U")
    assert row is None or row["fetch_state"] in (None, "neu")

    await p._icao_typen_pflegen()          # scheitert: Tests rufen die ICAO nicht an
    assert p._icao_ausstehend is False
    await p._resolve_aircraft_type("P28U")
    assert get_aircraft_type(get_connection(db), "P28U")["fetch_state"] == "nichts_gefunden"


@pytest.mark.asyncio
async def test_ein_artikel_ueber_den_hersteller_wird_verworfen(db, tmp_path, monkeypatch, liste):
    from app import aircraft_info
    _zuladung_leer_ausgegangen(db, "PC21")
    p = _poller(db, tmp_path)
    monkeypatch.setattr(p, "_now", lambda: T0)
    wiki = _wiki("Pilatus Aircraft")
    monkeypatch.setattr(aircraft_info, "resolve_type", wiki)

    await p._resolve_aircraft_type("PC21")

    assert wiki.gefragt == "Pilatus PC-21", "Wikipedia wurde gar nicht gefragt"

    row = get_aircraft_type(get_connection(db), "PC21")
    assert row["fetch_state"] == "nichts_gefunden"
    assert not row["wiki_title"]


@pytest.mark.asyncio
async def test_kuerzel_ausserhalb_der_liste_bleibt_nichts_gefunden(
        db, tmp_path, monkeypatch, liste):
    from app import aircraft_info
    _zuladung_leer_ausgegangen(db, "P34A")
    p = _poller(db, tmp_path)
    monkeypatch.setattr(p, "_now", lambda: T0)
    monkeypatch.setattr(aircraft_info, "resolve_type",
                        lambda name, fetch: pytest.fail("ohne Namen gibt es nichts zu fragen"))

    await p._resolve_aircraft_type("P34A")

    assert get_aircraft_type(get_connection(db), "P34A")["fetch_state"] == "nichts_gefunden"


# ---------------------------------------------------------------------------
# Zuladungs-Recherche: Hinweis aus der Liste, Grund des Fehlschlags in der Datenbank
# ---------------------------------------------------------------------------

class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Resp:
    stop_reason = "end_turn"

    def __init__(self, text):
        self.content = [_Block(text)]


def _fake_anthropic(antwort: str, gesehen: dict):
    mod = types.ModuleType("anthropic")

    class _Stream:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            return _Resp(antwort)

    class Anthropic:
        def __init__(self, **kwargs):
            self.messages = self

        def stream(self, **kwargs):
            gesehen["prompt"] = kwargs["messages"][0]["content"]
            return _Stream()

    mod.Anthropic = Anthropic
    return mod


@pytest.fixture
def _key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_der_prompt_nennt_das_muster_aus_der_liste(monkeypatch, liste, _key):
    from app import llm
    gesehen = {}
    gut = json.dumps({"make_model": "Piper PA-28RT-201T Turbo Arrow IV", "mtow_kg": 1315,
                      "empty_kg": 767, "fuel_full_kg": 196})
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(gut, gesehen))

    assert llm.suggest_aircraft_payload("P28U")["mtow_kg"] == 1315.0
    assert "laut ICAO Doc 8643: Piper PA-28RT-201T Turbo Arrow 4" in gesehen["prompt"]


def test_kuratierter_hinweis_bleibt_vorn(monkeypatch, _key):
    from app import llm
    icao_typen.setzen({"C172": [["REIMS", "FR172 Reims Rocket"]]})
    gesehen = {}
    gut = json.dumps({"make_model": "Cessna 172", "mtow_kg": 1157, "empty_kg": 767,
                      "fuel_full_kg": 144})
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(gut, gesehen))

    llm.suggest_aircraft_payload("C172")
    assert "(Cessna 172)" in gesehen["prompt"]
    assert "Reims" not in gesehen["prompt"]


def test_nullen_als_antwort_nennen_den_grund(monkeypatch, _key):
    """So sah der Fehlschlag am 09.10.2026 aus: Das Schema zwingt zu einer Antwort, das Modell
    schreibt Nullen und seine Begründung in make_model."""
    from app import llm
    nullen = json.dumps({"make_model": "Designator D226 not found in ICAO registry",
                         "mtow_kg": 0, "empty_kg": 0, "fuel_full_kg": 0})
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(nullen, {}))

    grund: list[str] = []
    assert llm.suggest_aircraft_payload("D226", grund) is None
    assert "unplausible Werte" in grund[0]
    assert "not found in ICAO registry" in grund[0]


@pytest.mark.asyncio
async def test_der_grund_steht_in_der_datenbank(db, tmp_path, monkeypatch):
    """Eine Logzeile überlebt keinen Deploy -- genau daran scheiterte die Suche bei P28U."""
    from app import llm

    def _leer(code, grund=None):
        grund.append("unplausible Werte (mtow=0 empty=0 fuel=0); Antwort: nicht gefunden")
        return None

    monkeypatch.setattr(llm, "suggest_aircraft_payload", _leer)
    p = _poller(db, tmp_path)
    monkeypatch.setattr(p, "_now", lambda: T0)

    await p._auto_research_payload("D226")

    row = get_payload_research(get_connection(db), "D226")
    assert row["state"] == "nichts_gefunden"
    assert row["last_error"].startswith("unplausible Werte")
