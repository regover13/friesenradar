"""Teilen- und Badge-Codes nennen die neue Adresse, auch wenn jemand ueber das Alias kommt.

Wer ueber ein altes Lesezeichen auf friesenspy.devprops.de landet, wuerde sonst mit jedem
kopierten Link und jedem Badge-Code die alte Adresse ins Forum tragen (Pruefbefund V7,
02.10.2026). Das Alias bleibt erreichbar, aber niemand soll es mehr lesen."""
import json
import re
import subprocess
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


# Welche Adresse genannt wird, prueft seit #58 tests/test_adress_umleitung.py
# (beide alten Adressen -> radar.friesenflieger.de).


def test_kein_teilen_code_nimmt_location_origin_direkt():
    roh = re.findall(r"\$\{location\.origin\}", INDEX)
    assert roh == [], "Teilen-/Badge-Codes muessen _teilenUrsprung() nehmen"


def test_admin_teilt_ebenfalls_nur_die_neue_adresse():
    admin = (Path(__file__).resolve().parents[1] / "app" / "static" / "admin.html").read_text(encoding="utf-8")
    assert admin.count("location.origin") == 1, \
        "Badge-/Teilen-Codes im Admin muessen _teilenUrsprung() nehmen"
    assert "function _teilenUrsprung()" in admin
