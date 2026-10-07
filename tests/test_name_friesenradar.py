"""Der Name ist FriesenRadar (16.0.0). Waechter gegen den alten Namen in allem, was ein Mensch liest."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SICHTBAR = ["app/static/index.html", "app/static/admin.html", "app/static/efb.html",
            "app/static/impressum.html", "app/static/datenschutz.html", "app/static/sw.js",
            "app/static/manifest.webmanifest", "README.md"]


def _ohne_kommentare(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    # Nur JS-Zeilenkommentare: "#" am Zeilenanfang ist im README eine Ueberschrift -- die liest
    # jeder (Prueffund 02.10.2026), und in CSS ein Selektor.
    return "\n".join(l for l in text.split("\n") if not l.strip().startswith("//"))


def test_kein_alter_name_wo_menschen_lesen():
    for rel in SICHTBAR:
        t = _ohne_kommentare((ROOT / rel).read_text(encoding="utf-8"))
        # Technische Konstanten (Merker-Schluessel, source-Wert, Geraetekennung) sind erlaubt.
        t = re.sub(r"friesenspy_[a-z_]+|'friesenspy[-a-z_]*'|\"friesenspy[-a-z_]*\"", "", t)
        # Das stille Alias darf genau dort stehen, wo es auf die neue Adresse umgeleitet wird.
        t = t.replace("var UMZUG_ALT = ['friesenspy.devprops.de', 'friesenradar.devprops.de'];", "")
        # Kniebrett-Paket 3.0.0 (Variante B): Die Bitte, den alten Ordner zu loeschen, muss ihn
        # beim Namen nennen -- die einzige erlaubte Nennung, an genau diese Formulierung gebunden.
        t = re.sub(r"(?:alten )?Ordner\s+(?:<code>)?friesenflieger-friesenspy-efb", "", t)
        assert not re.search(r"friesen ?spy", t, re.I), rel


def test_widget_und_anmeldeseite_heissen_friesenradar():
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "✈ FriesenRadar" in main and "✈ FriesenSpy" not in main
    assert "<title>FriesenRadar – Anmeldung</title>" in main


def test_vorschau_schalter_ist_weg():
    idx = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    assert "html.radar" not in idx and "_radarAnwenden" not in idx and "radarHosts" not in idx


def test_server_code_nennt_den_alten_namen_nicht():
    """main.py baut Anmeldeseite, Widget, Widget-Vorschau und Test-Push selbst zusammen; der
    User-Agent geht an fremde Dienste, deren Betreiber ihn lesen. Die alte Adresse darf nur
    noch als erlaubter Login-Ruecksprung stehen (stilles Alias) und in Kommentaren."""
    for rel in ["app/main.py", "app/aircraft_info.py"]:
        t = (ROOT / rel).read_text(encoding="utf-8")
        assert "FriesenSpy" not in t, rel
        code = [l for l in t.split("\n") if "friesenspy.devprops.de" in l
                and not l.strip().startswith("#")]
        assert code == ['    "friesenspy.devprops.de",'] if rel == "app/main.py" else code == [], rel
