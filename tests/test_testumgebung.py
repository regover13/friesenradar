# -*- coding: utf-8 -*-
"""Die Testumgebung selbst (25.09.2026).

**Temporäre Dateien liegen im Arbeitsspeicher, wo es ihn gibt.** Gemessen am 24.09.2026:
``init_db`` wird in der Suite 1409-mal gerufen und braucht auf der Platte 368 ms, in
``/dev/shm`` 35 ms -- die Zeit ging fast ganz ins Synchronisieren auf die Platte. Die ganze
Suite lief damit in 2:59 statt 8:46, mit denselben 3409 bestandenen Tests.
"""
from __future__ import annotations

import os

import pytest

_RAM = "/dev/shm"


@pytest.mark.skipif(not (os.path.isdir(_RAM) and os.access(_RAM, os.W_OK)),
                    reason="kein /dev/shm auf dieser Maschine")
@pytest.mark.skipif("TMPDIR" in os.environ, reason="TMPDIR ist ausdruecklich gesetzt")
def test_temporaere_dateien_liegen_im_ram(tmp_path):
    assert str(tmp_path).startswith(_RAM), tmp_path


def test_alte_laeufe_bleiben_nicht_im_arbeitsspeicher_liegen(pytestconfig):
    # 02.11.2026: drei aufbewahrte Läufe zu je ~950 MB in /dev/shm drückten den Server in den Swap.
    assert pytestconfig.getini("tmp_path_retention_count") == "1"
    assert pytestconfig.getini("tmp_path_retention_policy") == "failed"
