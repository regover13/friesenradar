"""Teilen- und Badge-Codes nennen die neue Adresse, auch wenn jemand ueber das Alias kommt.

Wer ueber ein altes Lesezeichen auf friesenspy.devprops.de landet, wuerde sonst mit jedem
kopierten Link und jedem Badge-Code die alte Adresse ins Forum tragen (Pruefbefund V7,
02.10.2026). Das Alias bleibt erreichbar, aber niemand soll es mehr lesen."""
import json
import re
import subprocess
from pathlib import Path

INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")


def _funktion(name):
    start = INDEX.index(f"function {name}(")
    ende = INDEX.index("\n}\n", start) + 2
    return INDEX[start:ende]


def _ursprung(origin):
    js = "var location = {origin: %s};\n%s\nprocess.stdout.write(_teilenUrsprung());" % (
        json.dumps(origin), _funktion("_teilenUrsprung"))
    return subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout


def test_alias_wird_beim_teilen_zur_neuen_adresse():
    assert _ursprung("https://friesenspy.devprops.de") == "https://friesenradar.devprops.de"


def test_andere_adressen_bleiben_wie_sie_sind():
    for o in ["https://friesenradar.devprops.de", "https://radar.friesenflieger.de", "http://localhost:8091"]:
        assert _ursprung(o) == o


def test_kein_teilen_code_nimmt_location_origin_direkt():
    roh = re.findall(r"\$\{location\.origin\}", INDEX)
    assert roh == [], "Teilen-/Badge-Codes muessen _teilenUrsprung() nehmen"


def test_admin_teilt_ebenfalls_nur_die_neue_adresse():
    admin = (Path(__file__).resolve().parents[1] / "app" / "static" / "admin.html").read_text(encoding="utf-8")
    assert "location.origin" not in admin.replace("location.origin === 'https://friesenspy.devprops.de'", "") \
        .replace("? 'https://friesenradar.devprops.de' : location.origin", ""), \
        "Badge-/Teilen-Codes im Admin muessen _teilenUrsprung() nehmen"
    assert "function _teilenUrsprung()" in admin
