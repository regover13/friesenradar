"""Dauerhaftes Löschen im Admin geht nur mit Passwort (Nutzer, 28.09.2026).

„Löschen unter Admin immer nur mit Passwort!" -- und genauer: „Ich will nur Dinge, die dauerhaft
sind und dauerhaft gelöscht werden." Destruktiv heißt hier: gespeicherte Daten verschwinden
endgültig. NICHT darunter fällt, was nur einen Betriebszustand zurücknimmt -- ein angefordertes
Objekt aus dem Simulator nehmen, eine Aufnahme im laufenden Abend freigeben, ein Feld dem
Kalender zurückgeben. Das bleibt ein Klick.

Der erste Test bewacht die REGEL für jede DELETE-Route, auch jede künftige; Ausnahmen stehen
mit Begründung in `_KEIN_DAUERHAFTES_LOESCHEN`. Der zweite nennt die dauerhaften Löschungen,
die als POST daherkommen.
"""
from __future__ import annotations

import ast
import inspect
import re
import textwrap
from pathlib import Path

import pytest

from app import main

_ADMIN = (Path(__file__).resolve().parents[1] / "app" / "static" / "admin.html").read_text(encoding="utf-8")

#: DELETE-Routen, die KEINE gespeicherten Daten löschen -- mit Begründung, damit niemand sie
#: aus Gewohnheit „repariert".
_KEIN_DAUERHAFTES_LOESCHEN = {
    "/api/admin/bruegge/soll/{soll_id}":
        "nimmt nur ein angefordertes Objekt aus dem Simulator zurück (Nutzer, 28.09.2026)",
}


def _verlangt_passwort(fn) -> bool:
    baum = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return any(isinstance(k, ast.Call) and getattr(k.func, "id", None) == "require_confirm"
               for k in ast.walk(baum))


def _routen():
    for r in main.app.routes:
        pfad = getattr(r, "path", "")
        if pfad.startswith("/api/admin/") and getattr(r, "endpoint", None):
            for methode in getattr(r, "methods", set()):
                yield methode, pfad, r.endpoint


def _fn(methode, pfad):
    treffer = [fn for m, p, fn in _routen() if m == methode and p == pfad]
    assert treffer, (methode, pfad)
    return treffer[0]


def test_jede_admin_loeschroute_verlangt_das_passwort():
    ohne = [pfad for m, pfad, fn in _routen()
            if m == "DELETE" and pfad not in _KEIN_DAUERHAFTES_LOESCHEN and not _verlangt_passwort(fn)]
    assert ohne == [], ohne


@pytest.mark.parametrize("pfad", [
    "/api/admin/bruegge/vergessen",                 # Bindung samt Bewährung weg
    "/api/admin/bummel/races/{race_id}/hide",       # eingefrorenes Ergebnis weg
])
def test_dauerhaftes_loeschen_per_post_verlangt_das_passwort(pfad):
    assert _verlangt_passwort(_fn("POST", pfad)), pfad


@pytest.mark.parametrize("methode,pfad", [
    ("DELETE", "/api/admin/bruegge/soll/{soll_id}"),
    ("POST", "/api/admin/reddung/events/{event_id}/aufnahme-freigeben"),
    ("POST", "/api/admin/bummel/races/{race_id}/kalenderstand/{feld}"),
    ("POST", "/api/admin/transport/events/{event_id}/kalenderstand/{feld}"),
])
def test_zuruecknehmen_bleibt_ein_klick(methode, pfad):
    """Nutzer, 28.09.2026: „Das ist ok so!! Das löscht kein Objekt aus der DB." """
    assert not _verlangt_passwort(_fn(methode, pfad)), pfad


def test_die_bruegge_knoepfe_gehen_ueber_api():
    """Ein nacktes fetch bekäme bei 403 keine Passwortabfrage, nur einen Fehler -- `api()`
    fragt nach und wiederholt die Aktion (wichtig fürs Vergessen)."""
    assert not re.search(r"fetch\('/api/admin/bruegge/(soll/|vergessen)", _ADMIN)
    assert "api('POST', '/api/admin/bruegge/vergessen'" in _ADMIN
