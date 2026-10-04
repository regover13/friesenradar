"""Belegt, dass das dunkle Design nach dem Variablen-Umbau unveraendert ist.

Nimmt den <style>-Block von index.html im Ausgangsstand (git) und im Arbeitsstand, setzt in
BEIDEN jedes var(--x) mit dem Wert aus :root ein (html.hell-Bloecke werden verworfen) und
vergleicht Selektor fuer Selektor die Deklarationen. Erlaubt ist nur Hinzukommendes.

Aufruf:  python -m scripts.dunkel_vergleich [--basis HEAD]
         Vorgabe HEAD: belegt den Arbeitsstand gegen den letzten Commit (je Schritt).
         Sieht NUR den <style>-Block -- Inline-style= und JavaScript nicht.
Spec:    docs/superpowers/specs/2026-10-01-helles-design-design.md, Schritt 3
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DATEI = "app/static/index.html"

# Selektoren, die der Umbau gewollt NEU einfuehrt. Alles andere Neue ist verdaechtig: Ein neuer
# Selektor auf bereits gestylte Elemente aendert das Dunkle, ohne unter "geaendert" zu stehen.
NEU_ERLAUBT = [
    r"^(html\.vr-panel )?\.design-knopf(\.an)?$", r"#einst-design", r"#notif-web-titel",
    r"^\.notif-panel:not\(\.mit-push\) #[\w-]+$",
    r"^\.notif-zahnrad-panel$", r"^#panel-anzeige \.panel-einst-name:first-of-type$",
    # Vorschau FriesenRadar (Issue #56): greift nur mit html.radar; .logo-radar versteckt die
    # neuen Logos im Normalbetrieb.
    r"^html\.radar[.\s]", r"^\.logo-radar$",
]

_KOMMENTAR = re.compile(r"/\*.*?\*/", re.S)
_VAR = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*(?:\([^()]*\)[^()]*)*))?\)")


def _css(html: str) -> str:
    # Nur echte <style>-Zeilen: In index.html Z. 9 steht "<style>-Block" in einem
    # JS-Kommentar -- eine lose Suche laese das ganze Kopfskript als CSS.
    teile = re.findall(r"^\s*<style[^>]*>\s*$(.*?)^\s*</style>", html, re.S | re.M)
    return _KOMMENTAR.sub("", "\n".join(teile))


def _bloecke(css: str):
    """Flache Liste (kontext, selektor, rumpf); @media-Klammern werden als Kontext mitgefuehrt."""
    aus, kontext, i = [], [], 0
    while i < len(css):
        auf = css.find("{", i)
        zu = css.find("}", i)
        if zu == -1:
            break
        if auf != -1 and auf < zu:
            kopf = " ".join(css[i:auf].split())
            ende = css.find("}", auf)
            naechstes_auf = css.find("{", auf + 1)
            if kopf.startswith("@") and naechstes_auf != -1 and naechstes_auf < ende:
                kontext.append(kopf)
                i = auf + 1
                continue
            aus.append((" | ".join(kontext), kopf, css[auf + 1:ende]))
            i = ende + 1
        else:
            if kontext:
                kontext.pop()
            i = zu + 1
    return aus


def _deklarationen(rumpf: str) -> list[tuple[str, str]]:
    out = []
    for teil in rumpf.split(";"):
        if ":" not in teil:
            continue
        name, wert = teil.split(":", 1)
        out.append((name.strip().lower(), " ".join(wert.split())))
    return out


def _glieder(selektor: str) -> list[str]:
    return [g.strip() for g in selektor.split(",") if g.strip()]


def _ist_hell(glied: str) -> bool:
    return glied.startswith("html.hell")


def _variablen(bloecke) -> dict[str, str]:
    v: dict[str, str] = {}
    for kontext, sel, rumpf in bloecke:
        if sel.strip() == ":root" and not kontext:
            for n, w in _deklarationen(rumpf):
                if n.startswith("--"):
                    v[n] = w
    return v


def _einsetzen(wert: str, var: dict[str, str], tiefe: int = 0) -> str:
    if tiefe > 10:
        return wert

    def ersatz(m):
        name, rueckfall = m.group(1), m.group(2)
        if name in var:
            return _einsetzen(var[name], var, tiefe + 1)
        if rueckfall is not None:
            return _einsetzen(rueckfall.strip(), var, tiefe + 1)
        return "<UNDEFINIERT>"

    return _VAR.sub(ersatz, wert)


def _norm(wert: str) -> str:
    wert = re.sub(r"\s*,\s*", ",", wert)
    wert = re.sub(r"\(\s*", "(", wert)
    wert = re.sub(r"\s*\)", ")", wert)
    return re.sub(r"#[0-9a-fA-F]{3,8}\b", lambda m: m.group(0).lower(), wert)


def _aufgeloest(html: str) -> dict[str, list[tuple[str, str]]]:
    bloecke = _bloecke(_css(html))
    var = _variablen(bloecke)
    regeln: dict[str, list[tuple[str, str]]] = {}
    for kontext, sel, rumpf in bloecke:
        if sel.startswith("@"):
            continue
        # Nur Glieder, die SELBST mit html.hell beginnen, gehoeren dem Hellen. Eine gemischte
        # Liste ("html.hell .x, .y") behaelt ihren dunklen Teil -- als anderer Schluessel
        # erscheint sie dann unter neu_unerwartet statt still zu verschwinden.
        dunkel = [g for g in _glieder(sel) if not _ist_hell(g)]
        if not dunkel:
            continue
        sel = ", ".join(dunkel)
        # Variablen-Definitionen zaehlen nur in :root als Werte (sie werden eingesetzt);
        # anderswo (z. B. html.vr-panel { --green: … }) sind sie eine Aenderung wie jede andere.
        ist_root = sel == ":root" and not kontext
        dekl = [(n, _norm(_einsetzen(w, var))) for n, w in _deklarationen(rumpf)
                if not (ist_root and n.startswith("--"))]
        schluessel = (kontext + " || " if kontext else "") + sel
        regeln.setdefault(schluessel, []).extend(dekl)
    return regeln


def vergleiche(alt_html: str, neu_html: str) -> dict:
    alt, neu = _aufgeloest(alt_html), _aufgeloest(neu_html)
    frisch = [s for s in neu if s not in alt]
    return {
        "geaendert": [s for s in alt if s in neu and alt[s] != neu[s]],
        "entfernt": [s for s in alt if s not in neu],
        "neu": frisch,
        # Jedes Glied einer Liste muss angemeldet sein: ".design-knopf, .aircraft-marker-fremd"
        # ist nicht deshalb erlaubt, weil sein erstes Glied es waere.
        "neu_unerwartet": [s for s in frisch
                           if not all(any(re.search(m, g) for m in NEU_ERLAUBT)
                                      for g in _glieder(s.split(" || ")[-1]))],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--basis", default="HEAD")
    a = ap.parse_args()
    alt = subprocess.run(["git", "show", f"{a.basis}:{DATEI}"], capture_output=True,
                         text=True, check=True).stdout
    neu = Path(DATEI).read_text(encoding="utf-8")
    e = vergleiche(alt, neu)
    for art in ("geaendert", "entfernt", "neu", "neu_unerwartet"):
        print(f"{art}: {len(e[art])}")
        for s in e[art]:
            print("   ", s)
    return 1 if (e["geaendert"] or e["entfernt"] or e["neu_unerwartet"]) else 0


if __name__ == "__main__":
    sys.exit(main())
