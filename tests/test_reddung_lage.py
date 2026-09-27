# -*- coding: utf-8 -*-
"""Die Lage einer FriesenReddung: was gesucht wird (Nutzerwunsch 27.09.2026).

Ein Freitext (`lagetext` -- bewusst nicht `lage`: „Lage des Havaristen" heisst in dieser
Codebasis sein ORT, und der ist geheim), den der Veranstalter im Admin schreibt -- die Geschichte des Abends. Er steht
oben in der Reddung-Ansicht (schon vor dem Start), im Live-Block und im Forumstext. Wie viel
er verraet, entscheidet der Veranstalter; der Ort des Havaristen bleibt davon unberuehrt.

Zweiter Teil, gleich wichtig: Wer nach dem Abend einen Tippfehler in der Lage korrigiert,
darf die Bilanz nicht verlieren. Das Formular schickt beim Speichern IMMER alle Felder, und
bis 15.24.0 verwarf jedes Speichern den fortgeschriebenen Stand. Nach dem Aufraeumen der
Bruegge-Spuren (12 h) haette die Neuberechnung die abgesuchte Flaeche auf null gesetzt
(s. CLAUDE.md, „Vor dem Erhoehen von _REDDUNG_STAND_FASSUNG …").
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException

import app.main as main
from app.database import get_connection, get_progress_snapshot, get_reddung_event, write_progress_snapshot

from tests.test_reddung_api import FakeReq, SEKTOR, _laufend, db  # noqa: F401  (Fixture)

_INDEX = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text(encoding="utf-8")
_ADMIN = (Path(__file__).resolve().parents[1] / "app" / "static" / "admin.html").read_text(encoding="utf-8")
_NODE = shutil.which("node")

LAGE = ("Eine Cessna 172 ist auf dem Weg von Mendig nach Bitburg verschollen.\n"
        "Letzter Funkkontakt über der Hohen Acht.")


def _anlegen(**extra) -> int:
    body = {"name": "Verschollen in der Eifel", "dtstart": "2026-09-25T17:00:00Z", **SEKTOR, **extra}
    return asyncio.run(main.admin_create_reddung_event(FakeReq(body=body)))["id"]


def _aendern(eid, body):
    return asyncio.run(main.admin_update_reddung_event(FakeReq(body=body), eid))


def _event(db, eid) -> dict:
    c = get_connection(db)
    try:
        return dict(get_reddung_event(c, eid))
    finally:
        c.close()


# --- Speichern und Ausliefern -------------------------------------------------------------

def test_die_lage_wird_angelegt_und_oeffentlich_ausgeliefert(db):
    eid = _anlegen(lagetext=LAGE, **_laufend())
    assert _event(db, eid)["lagetext"] == LAGE
    daten = main.reddung_events()
    assert daten[0]["lagetext"] == LAGE


def test_die_lage_wird_beim_aendern_geputzt(db):
    eid = _anlegen()
    _aendern(eid, {"lagetext": "  " + LAGE + "\n\n "})
    assert _event(db, eid)["lagetext"] == LAGE
    _aendern(eid, {"lagetext": "   "})
    assert _event(db, eid)["lagetext"] is None, "leer heisst: keine Lage"


def test_ohne_lage_steht_null_in_der_liste(db):
    _anlegen(**_laufend())
    assert main.reddung_events()[0]["lagetext"] is None


@pytest.mark.parametrize("falsch", [42, ["a"], "x" * 2001], ids=["zahl", "liste", "zu_lang"])
def test_eine_unbrauchbare_lage_wird_abgewiesen(db, falsch):
    with pytest.raises(HTTPException) as e:
        _anlegen(lagetext=falsch)
    assert e.value.status_code == 400
    eid = _anlegen()
    with pytest.raises(HTTPException) as e:
        _aendern(eid, {"lagetext": falsch})
    assert e.value.status_code == 400


# --- Der Stand ueberlebt das Speichern der Lage -------------------------------------------

def _mit_stand(db, eid):
    c = get_connection(db)
    try:
        write_progress_snapshot(c, "reddung", eid,
                                {"v": 1, "bis": "2026-09-25T17:30:00Z",
                                 "treffer": {"z0_0": [111, "2026-09-25T17:10:00Z"]},
                                 "je_pilot": {"111": 1}, "fund": None},
                                "2026-09-25T17:30:00Z")
        c.commit()
    finally:
        c.close()


def _stand_da(db, eid) -> bool:
    c = get_connection(db)
    try:
        return get_progress_snapshot(c, "reddung", eid) is not None
    finally:
        c.close()


def _wie_das_formular(ev: dict, **aenderung) -> dict:
    """Was rdSpeichern schickt: alle Felder, mit den gespeicherten Werten."""
    felder = ("name", "dtstart", "dtend", "sued", "nord", "west", "ost", "kante_km", "korridor_km",
              "hoehe_max_ft", "gs_max_kt", "gs_min_kt", "fund_radius_m", "fund_hoehe_ft",
              "aufnehmen_noetig", "landung_noetig", "aufnahme_verfaellt", "lagetext")
    return {**{k: ev[k] for k in felder}, **aenderung}


def test_die_lage_zu_speichern_behaelt_den_stand(db):
    eid = _anlegen(lagetext="Tippfeler")
    _mit_stand(db, eid)
    _aendern(eid, _wie_das_formular(_event(db, eid), lagetext=LAGE))
    assert _event(db, eid)["lagetext"] == LAGE
    assert _stand_da(db, eid), "nur die Lage ist neu -- die Bilanz muss bleiben"


def test_den_namen_zu_aendern_behaelt_den_stand(db):
    eid = _anlegen()
    _mit_stand(db, eid)
    _aendern(eid, _wie_das_formular(_event(db, eid), name="Verschollen im Hunsrück"))
    assert _stand_da(db, eid)


def test_ein_geaenderter_rechenwert_verwirft_den_stand_weiterhin(db):
    """Die Gegenprobe: Mit dem ganzen Formular und EINER geaenderten Hoehenschranke muss der
    Stand weg -- sonst zaehlten Zellen, die unter der neuen Schranke nie abgesucht waren."""
    eid = _anlegen()
    _mit_stand(db, eid)
    _aendern(eid, _wie_das_formular(_event(db, eid), hoehe_max_ft=1500))
    assert not _stand_da(db, eid)


def test_ein_zahlenwert_als_ganzzahl_gilt_als_unveraendert(db):
    """Das Formular schickt 2000, gespeichert ist 2000.0 -- das ist dieselbe Schranke."""
    eid = _anlegen()
    _mit_stand(db, eid)
    ev = _event(db, eid)
    _aendern(eid, _wie_das_formular(ev, hoehe_max_ft=int(ev["hoehe_max_ft"]), lagetext=LAGE))
    assert _stand_da(db, eid)


# --- Anzeige ------------------------------------------------------------------------------

def _funktion(name: str) -> str:
    m = re.search(rf"^(async )?function {re.escape(name)}\(", _INDEX, flags=re.M)
    assert m, f"function {name} fehlt"
    return _INDEX[m.start():_INDEX.index("\n}\n", m.start()) + 3]


@pytest.mark.skipif(not _NODE, reason="node fehlt")
def test_die_lage_wird_escaped_und_behaelt_ihre_zeilen():
    js = _funktion("escHtml") + _funktion("_reddungLageHtml") + """
      console.log(JSON.stringify([_reddungLageHtml({lagetext: 'A <b>\\nB'}), _reddungLageHtml({lagetext: null}),
                                  _reddungLageHtml({})]));
    """
    erg = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
    assert erg.returncode == 0, erg.stderr
    mit, ohne, leer = json.loads(erg.stdout.strip().splitlines()[-1])
    assert "A &lt;b&gt;\nB" in mit and 'class="reddung-lage"' in mit and "<b>" not in mit
    assert ohne == "" and leer == ""


def test_die_zeilenumbrueche_bleiben_sichtbar():
    m = re.search(r"\.reddung-lage\s*\{([^}]*)\}", _INDEX)
    assert m and "white-space: pre-line" in m.group(1)


def test_die_lage_steht_oben_in_der_reddung_ansicht():
    bilanz = _funktion("_reddungBilanzHtml")
    assert "_reddungLageHtml(r)" in bilanz
    # vor dem Balken, also vor allem anderen ausser dem Zeitfenster
    assert bilanz.index("_reddungLageHtml(r)") < bilanz.index("_reddungBalken(")


def test_die_lage_steht_im_live_block_solange_gesucht_wird():
    block = _funktion("_reddungBannerBlock")
    assert re.search(r"if \(!fertig\) html \+= _reddungLageHtml\(r\)", block)


def test_die_lage_steht_im_forumstext():
    text = _funktion("_reddungForumText")
    assert re.search(r"if \(r\.lagetext\) z\.push\(`Lage: \$\{r\.lagetext\}`\)", text)


def test_der_admin_hat_ein_feld_fuer_die_lage():
    assert re.search(r'<textarea id="rd-lagetext"', _ADMIN)
    speichern = _ADMIN[_ADMIN.index("async function rdSpeichern"):_ADMIN.index("function _rdFormSchliessen")]
    assert "lagetext: document.getElementById('rd-lagetext').value.trim()" in speichern
    bearbeiten = _ADMIN[_ADMIN.index("function rdEdit("):_ADMIN.index("async function rdCopyLink")]
    assert "setz('rd-lagetext', ev.lagetext)" in bearbeiten
