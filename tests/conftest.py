# -*- coding: utf-8 -*-
"""Gemeinsame Einstellungen der Testsuite.

**Temporäre Dateien in den Arbeitsspeicher** (25.09.2026). Fast jeder Test legt über
``tmp_path`` eine eigene SQLite-Datenbank an (``init_db``, 1409-mal je Lauf). Auf der Platte
kostet das 368 ms je Aufruf, fast alles Warten aufs Synchronisieren; in ``/dev/shm`` 35 ms.
Die Suite lief damit in 2:59 statt 8:46 -- mit denselben 3409 bestandenen Tests, also ohne
dass ein Test weniger beweist (``tests/test_testumgebung.py``).

``tempfile.tempdir`` ist die Stelle, aus der ``tmp_path`` und ``tempfile.mkdtemp`` ihren
Ursprung nehmen. Ein ausdrücklich gesetztes ``TMPDIR`` hat Vorrang, und wo es kein
``/dev/shm`` gibt (Windows, macOS), bleibt alles, wie es war.
"""
from __future__ import annotations

import os
import tempfile

_RAM = "/dev/shm"

if "TMPDIR" not in os.environ and os.path.isdir(_RAM) and os.access(_RAM, os.W_OK):
    tempfile.tempdir = _RAM


import pytest


@pytest.fixture(autouse=True)
def _icao_liste_leer_und_ohne_netz(monkeypatch):
    """Die ICAO-Kürzelliste lebt im Modul (`app.icao_typen`) und käme sonst aus dem Netz.

    Jeder Test beginnt ohne Liste -- dann verhält sich die Muster-Recherche wie vor 16.4.1 --
    und kein Test ruft die ICAO an, auch nicht über einen gestarteten Poller. Wer die Liste
    braucht, setzt sie selbst (tests/test_icao_typen.py)."""
    from app import icao_typen

    def _kein_netz():
        raise RuntimeError("Tests rufen die ICAO nicht an")

    icao_typen.setzen({})
    monkeypatch.setattr(icao_typen, "_holen", _kein_netz)
    yield
    icao_typen.setzen({})
