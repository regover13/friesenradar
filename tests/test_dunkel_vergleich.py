"""Das Werkzeug, das "dunkles Design unveraendert" belegt (Spec helles Design, Schritt 3)."""
from scripts.dunkel_vergleich import vergleiche


def _seite(css):
    # <style> auf eigener Zeile wie in index.html (Z. 679/4054) -- das Werkzeug liest nur solche.
    return "<html><head>\n  <style>\n" + css + "\n  </style>\n</head><body></body></html>"


ALT = _seite("""
:root { --bg: #04080f; }
.a { color: #2d9cdb; border: 1px solid rgba(45,156,219,0.15); }
.b { background: var(--bg); }
""")


def test_reine_umbenennung_ist_gleich():
    neu = _seite("""
:root { --bg: #04080f; --green: #2d9cdb; --green-rgb: 45,156,219; }
html.hell { --bg: #9FC7F8; --green: #105289; --green-rgb: 16,82,137; }
.a { color: var(--green); border: 1px solid rgba(var(--green-rgb), 0.15); }
.b { background: var(--bg); }
""")
    e = vergleiche(ALT, neu)
    assert e["geaendert"] == [] and e["entfernt"] == []


def test_geaenderte_deckkraft_faellt_auf():
    neu = _seite("""
:root { --bg: #04080f; --green-rgb: 45,156,219; }
.a { color: #2d9cdb; border: 1px solid rgba(var(--green-rgb),0.12); }
.b { background: var(--bg); }
""")
    assert vergleiche(ALT, neu)["geaendert"] == [".a"]


def test_falscher_dunkler_variablenwert_faellt_auf():
    neu = _seite("""
:root { --bg: #04080f; --green: #2e9cdb; }
.a { color: var(--green); border: 1px solid rgba(45,156,219,0.15); }
.b { background: var(--bg); }
""")
    assert vergleiche(ALT, neu)["geaendert"] == [".a"]


def test_neue_regeln_und_hell_bloecke_sind_erlaubt():
    neu = _seite("""
:root { --bg: #04080f; }
.a { color: #2d9cdb; border: 1px solid rgba(45,156,219,0.15); }
.b { background: var(--bg); }
.design-knopf { color: red; }
html.hell .a { color: blue; }
""")
    e = vergleiche(ALT, neu)
    assert e["geaendert"] == [] and e["entfernt"] == []
    assert e["neu"] == [".design-knopf"] and e["neu_unerwartet"] == []


def test_unerwartete_neue_regel_faellt_auf():
    # Ein neuer Selektor auf dieselben Elemente aenderte das Dunkle, ohne unter
    # "geaendert" zu erscheinen -- deshalb gilt Neues nur, wenn es angemeldet ist.
    neu = _seite(ALT[ALT.index(":root"):ALT.index("  </style>")] + "\nheader .a { color: red; }")
    assert vergleiche(ALT, neu)["neu_unerwartet"] == ["header .a"]


def test_style_im_skriptkommentar_wird_nicht_als_css_gelesen():
    # index.html Z. 9: "Muss VOR dem <style>-Block laufen" steht in einem JS-Kommentar.
    html = ("<html><head><script>// VOR dem <style>-Block\nvar o = { t: 1 };</script>\n"
            "  <style>\n.a { color: #2d9cdb; }\n  </style></head></html>")
    e = vergleiche(html, html)
    assert e == {"geaendert": [], "entfernt": [], "neu": [], "neu_unerwartet": []}
    from scripts.dunkel_vergleich import _css
    assert "var o" not in _css(html)


def test_entfernte_regel_faellt_auf():
    neu = _seite(":root { --bg: #04080f; }\n.b { background: var(--bg); }")
    assert vergleiche(ALT, neu)["entfernt"] == [".a"]


def test_undefinierte_variable_bleibt_undefiniert():
    # --text-dim ist heute nirgends definiert. Wer sie definiert, aendert das Dunkle.
    alt = _seite(":root { --bg: #04080f; }\n.x { color: var(--text-dim); }")
    neu = _seite(":root { --bg: #04080f; --text-dim: #6b9ab8; }\n.x { color: var(--text-dim); }")
    assert vergleiche(alt, neu)["geaendert"] == [".x"]


def test_variable_ausserhalb_von_root_faellt_auf():
    neu = _seite(ALT[ALT.index(":root"):ALT.index("  </style>")] + "\nhtml.vr-panel { --bg: #ff0000; }")
    alt = _seite(ALT[ALT.index(":root"):ALT.index("  </style>")] + "\nhtml.vr-panel { --bg: #04080f; }")
    assert vergleiche(alt, neu)["geaendert"] == ["html.vr-panel"]


def test_gemischte_liste_mit_hell_wird_nicht_verschluckt():
    neu = _seite(ALT[ALT.index(":root"):ALT.index("  </style>")] + "\nhtml.hell .x, .a { color: red; }")
    # Der dunkle Teil ".a" haengt sich an die bestehende Regel .a -- also "geaendert".
    assert vergleiche(ALT, neu)["geaendert"] == [".a"]


def test_keyframes_werden_verglichen():
    alt = _seite("@keyframes blink {\n  0% { background: rgba(45,156,219,0.25); }\n}")
    neu = _seite("@keyframes blink {\n  0% { background: rgba(45,156,219,0.26); }\n}")
    assert vergleiche(alt, neu)["geaendert"] == ["@keyframes blink || 0%"]


def test_erlaubtes_muster_deckt_keine_ganze_liste():
    neu = _seite(ALT[ALT.index(":root"):ALT.index("  </style>")] + "\n.design-knopf, .b2 { color: red; }")
    assert vergleiche(ALT, neu)["neu_unerwartet"] == [".design-knopf, .b2"]


def test_hex_schreibweise_und_leerzeichen_sind_egal():
    alt = _seite(".a { color: #2D9CDB; border: 1px solid rgba(45, 156, 219, 0.15); }")
    neu = _seite(":root { --g: #2d9cdb; }\n.a { color: var(--g); border: 1px solid rgba(45,156,219,0.15); }")
    assert vergleiche(alt, neu)["geaendert"] == []
