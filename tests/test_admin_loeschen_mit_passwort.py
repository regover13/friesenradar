"""Löschen im Admin geht nur mit Passwort -- ausnahmslos (Nutzer, 28.09.2026).

„Löschen unter Admin immer nur mit Passwort! Das scheint bei unseren neuen Funktionen zur
Reddung, Brücke und Messe nicht berücksichtigt worden zu sein!" Stimmte: Elf destruktive
Endpunkte liefen ohne Step-up (`require_confirm`), einer davon -- Objekt aus dem Simulator
nehmen -- sogar ohne jede Nachfrage auf einen Klick.

Der erste Test bewacht die REGEL: Jede DELETE-Route unter /api/admin verlangt das Passwort,
auch jede künftige. Der zweite nennt die destruktiven Aktionen, die als POST daherkommen.
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


def test_jede_admin_loeschroute_verlangt_das_passwort():
    ohne = [pfad for m, pfad, fn in _routen() if m == "DELETE" and not _verlangt_passwort(fn)]
    assert ohne == [], ohne


@pytest.mark.parametrize("pfad", [
    "/api/admin/bruegge/vergessen",
    "/api/admin/reddung/events/{event_id}/aufnahme-freigeben",
    "/api/admin/bummel/races/{race_id}/hide",
    "/api/admin/bummel/races/{race_id}/kalenderstand/{feld}",
    "/api/admin/transport/events/{event_id}/kalenderstand/{feld}",
])
def test_destruktive_post_aktionen_verlangen_das_passwort(pfad):
    treffer = [fn for m, p, fn in _routen() if m == "POST" and p == pfad]
    assert treffer, pfad
    assert _verlangt_passwort(treffer[0]), pfad


def test_die_bruegge_knoepfe_holen_die_passwortabfrage_nach():
    """Ein nacktes fetch bekäme bei 403 keine Passwortabfrage, nur einen Fehler -- `api()`
    fragt nach und wiederholt die Aktion."""
    assert not re.search(r"fetch\('/api/admin/bruegge/(soll/|vergessen)", _ADMIN)
    assert "api('DELETE', '/api/admin/bruegge/soll/'" in _ADMIN
    assert "api('POST', '/api/admin/bruegge/vergessen'" in _ADMIN
