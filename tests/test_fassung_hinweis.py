# -*- coding: utf-8 -*-
"""„Deine Fassung ist veraltet" — der einzige Weg, der den Piloten erreicht (16.09.2026).

**Die FriesenBrügge kann selbst nichts sagen.** Sie schreibt nach ``stderr`` (MSFS) bzw.
``XPLMDebugString`` (X-Plane); im Flug sieht das niemand — selbst ihre eingebaute
426-Warnung („es hilft nur ein neues Paket") ist damit faktisch stumm. Und alles, was man
*in* sie einbaut, erreicht nur den, der schon aktualisiert hat, also gerade nicht den, um den
es geht. Bleiben Website und Kniebrett.

Beide Brügge senden ihre Fassung seit jeher mit (``bruegge_version``, MSFS wie X-Plane) — der
Server hat sie bis zu diesem Stand **weggeworfen**. Damit ließ sich nicht einmal beantworten,
wer veraltet unterwegs ist.

Der Test bindet beide Enden: den Server (speichern, vergleichen, ausliefern) und den
Hinweiskasten in `index.html`, der die Antwort auswertet.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.database import (get_connection, init_db, touch_panel_device,
                          bind_panel_device, bruegge_zuordnung_setzen,
                          bruegge_version_merken, set_app_setting)
from app.forum_sso import USER_COOKIE, make_user_token
from tests.test_bruegge_endpunkt import (  # noqa: F401  (`klient` ist eine Fixture)
    klient, _meldung, _friese_anlegen,
)

SECRET = "s3cr3t-key"
CID = 1602713
STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
_NODE = shutil.which("node")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    init_db(p)
    settings = SimpleNamespace(
        DB_PATH=p, CALLSIGN_PREFIX="FRS", SECRET_KEY=SECRET, ADMIN_PASSWORD="pw",
        SSO_SECRET="shared-forum-secret", FORUM_SSO_URL="https://board.example/sso",
        FORUM_SSO_CALLBACK="https://friesenspy.example/sso/callback",
        USER_SESSION_MAX_AGE_SEC=1200, OPENAIP_API_KEY="", VAPID_PUBLIC_KEY="",
        BRUEGGE_PACKAGE_PATH="",
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    # Die Fassungen kommen sonst aus den hinterlegten ZIPs -- die gibt es im Test nicht, und
    # ein fehlendes Archiv heißt „keine Aussage" (dann ist NICHTS veraltet). Genau deshalb
    # wird hier gesetzt statt gemockt-weggelassen: Sonst wären alle Prüfungen grün, ohne
    # etwas zu prüfen.
    monkeypatch.setattr(main, "_bruegge_paket_info",
                        lambda sim: {"verfuegbar": True,
                                     "version": "1.12.0" if sim == "msfs" else "1.2.2"})
    monkeypatch.setattr(main, "_efb_package_version", lambda pfad: "2.3.0")
    main._reset_gate_cache()
    # Ohne scharfgeschaltetes Board-Login gibt `_current_cid` grundsaetzlich None zurueck --
    # dann waere jede Pruefung hier gruen, ohne etwas zu pruefen.
    conn = get_connection(p)
    set_app_setting(conn, "forum_login_enabled", "1")
    conn.commit()
    conn.close()
    return SimpleNamespace(client=TestClient(main.app), db=p)


def _cookie(cid: int = CID) -> dict:
    return {USER_COOKIE: make_user_token(SECRET, "Tobias", str(cid), False, time.time() + 3600)}


def _bruegge_anlegen(db, kennung="K1", simulator="msfs2024", version="1.9.0", cid=CID):
    conn = get_connection(db)
    bruegge_zuordnung_setzen(conn, kennung, cid, simulator)
    bruegge_version_merken(conn, kennung, version)
    conn.commit()
    conn.close()


class TestServer:
    def test_ohne_anmeldung_gibt_es_gar_nichts(self, env):
        """Auch nicht die Paketfassungen — dieselbe Auskunft ist bei `/api/efb-package`
        anmeldepflichtig, und zwei Maßstäbe für dieselbe Zahl sind einer zu viel."""
        r = env.client.get("/api/me/fassungen")
        assert r.status_code == 401
        assert "1.12.0" not in r.text

    def test_eine_alte_bruegge_wird_als_veraltet_gemeldet(self, env):
        _bruegge_anlegen(env.db, version="1.9.0")
        d = env.client.get("/api/me/fassungen", cookies=_cookie()).json()
        (b,) = d["bruegge"]["meine"]
        assert b["version"] == "1.9.0" and b["aktuell"] == "1.12.0"
        assert b["veraltet"] is True

    def test_die_neueste_fassung_loest_nichts_aus(self, env):
        _bruegge_anlegen(env.db, version="1.12.0")
        (b,) = env.client.get("/api/me/fassungen", cookies=_cookie()).json()["bruegge"]["meine"]
        assert b["veraltet"] is False

    def test_zeichenkettenvergleich_waere_falschherum(self, env):
        """`"1.9.0" > "1.10.0"` als Text — der Vergleich muss zahlenweise sein."""
        _bruegge_anlegen(env.db, version="1.9.0", kennung="K1")
        d = env.client.get("/api/me/fassungen", cookies=_cookie()).json()
        assert d["bruegge"]["meine"][0]["veraltet"] is True

    def test_eine_bruegge_ohne_gemeldete_fassung_wird_nicht_verdaechtigt(self, env):
        """`None` heißt „hat noch nicht gemeldet", nicht „alt".

        Ein Hinweis auf Verdacht verbrennt das Vertrauen in alle anderen.
        """
        conn = get_connection(env.db)
        bruegge_zuordnung_setzen(conn, "K0", CID, "msfs2024")
        conn.commit()
        conn.close()
        (b,) = env.client.get("/api/me/fassungen", cookies=_cookie()).json()["bruegge"]["meine"]
        assert b["version"] is None and b["veraltet"] is False

    def test_xplane_wird_gegen_das_xplane_paket_gehalten(self, env):
        """Zwei Pakete, zwei Zahlen — eine X-Plane-Brügge 1.2.2 ist aktuell, keine 1.12.0."""
        _bruegge_anlegen(env.db, kennung="X1", simulator="xplane12", version="1.2.2")
        (b,) = env.client.get("/api/me/fassungen", cookies=_cookie()).json()["bruegge"]["meine"]
        assert b["aktuell"] == "1.2.2" and b["veraltet"] is False

    def test_fremde_brueggen_gehen_niemanden_etwas_an(self, env):
        _bruegge_anlegen(env.db, kennung="F1", cid=999999, version="1.0.0")
        d = env.client.get("/api/me/fassungen", cookies=_cookie()).json()
        assert d["bruegge"]["meine"] == []

    def test_auch_das_kniebrett_paket_steht_drin(self, env):
        """Der Zusatz vom 16.09.2026: auf der Website zählt auch das EFB-Paket."""
        conn = get_connection(env.db)
        bind_panel_device(conn, "d" * 40, CID, "Tablet")
        touch_panel_device(conn, "d" * 40, paket_version="2.1.0")
        conn.commit()
        conn.close()
        d = env.client.get("/api/me/fassungen", cookies=_cookie()).json()
        (k,) = d["kniebrett"]["meine"]
        assert k["version"] == "2.1.0" and k["veraltet"] is True
        assert k["geraet"] == "d" * 12, "die Geräte-ID ist ein Zugangsschlüssel — gekürzt"


class TestMeldungSpeichert:
    """Die Version muss beim Melden ankommen — sonst hat der Endpunkt oben nichts zu zeigen.

    Bis zum 16.09.2026 kam sie nicht an: Beide Brügge senden `bruegge_version` seit jeher,
    der Server hat das Feld gelesen und weggeworfen.
    """

    def test_die_gemeldete_fassung_landet_in_der_zuordnung(self, klient, tmp_path):
        db = str(tmp_path / "t.db")
        _friese_anlegen(db)
        klient.post("/api/bruegge/melden", json=_meldung(bruegge_version="1.7.3"))
        conn = get_connection(db)
        row = conn.execute("SELECT bruegge_version FROM bruegge_zuordnung").fetchone()
        conn.close()
        assert row is not None and row[0] == "1.7.3"

    def test_eine_meldung_ohne_feld_loescht_die_bekannte_fassung_nicht(self, klient, tmp_path):
        """Sonst sähe ein Ausfall des Feldes aus wie ein Gerät, das nie gemeldet hat."""
        db = str(tmp_path / "t.db")
        _friese_anlegen(db)
        klient.post("/api/bruegge/melden", json=_meldung(bruegge_version="1.7.3"))
        ohne = _meldung()
        ohne.pop("bruegge_version", None)
        klient.post("/api/bruegge/melden", json=ohne)
        conn = get_connection(db)
        row = conn.execute("SELECT bruegge_version FROM bruegge_zuordnung").fetchone()
        conn.close()
        assert row[0] == "1.7.3"


class TestBannerEndpunkt:
    """Der Banner nach einem Flug mit fehlendem oder altem Paket (12.10.2026). Die Regeln
    selbst prüft `test_paket_mangel.py`; hier geht es um Anmeldung und Wegklicken."""

    def _flug(self, db, logon="2026-10-12T18:00:00Z", logoff="2026-10-12T19:00:00Z"):
        conn = get_connection(db)
        conn.execute("INSERT OR IGNORE INTO pilots (cid, name, added_at, active) "
                     "VALUES (?, 'Test', '2026-01-01T00:00:00Z', 1)", (CID,))
        fid = conn.execute(
            "INSERT INTO flights (cid, callsign, logon_time, logoff_time, duration_min) "
            "VALUES (?, 'FRS49', ?, ?, 60)", (CID, logon, logoff)).lastrowid
        conn.commit()
        conn.close()
        return fid

    def test_ohne_anmeldung_gibt_es_nichts(self, env):
        assert env.client.get("/api/me/paket-hinweis").status_code == 401
        assert env.client.post("/api/me/paket-hinweis/weg", json={"flug_id": 1}).status_code == 401

    def test_flug_ohne_bruegge_zeigt_den_banner(self, env):
        fid = self._flug(env.db)
        d = env.client.get("/api/me/paket-hinweis", cookies=_cookie()).json()
        assert d["flug_id"] == fid and d["zeigen"] is True
        assert [z["art"] for z in d["zeilen"]] == ["bruegge_fehlt"]

    def test_die_hinterlegten_fassungen_kommen_an(self, env):
        self._flug(env.db)
        _bruegge_anlegen(env.db, version="1.9.0", simulator="msfs2020")
        conn = get_connection(env.db)
        conn.execute("UPDATE bruegge_zuordnung SET gesehen_am = '2026-10-12T18:30:00Z'")
        conn.commit()
        conn.close()
        (z,) = env.client.get("/api/me/paket-hinweis", cookies=_cookie()).json()["zeilen"]
        assert z["art"] == "bruegge_alt" and "1.9.0" in z["text"] and "1.12.0" in z["text"]

    def test_wegklicken_gilt_bis_zum_naechsten_flug(self, env):
        fid = self._flug(env.db)
        r = env.client.post("/api/me/paket-hinweis/weg", json={"flug_id": fid}, cookies=_cookie())
        assert r.status_code == 200
        assert env.client.get("/api/me/paket-hinweis", cookies=_cookie()).json()["zeigen"] is False
        self._flug(env.db, logon="2026-10-13T18:00:00Z", logoff="2026-10-13T19:00:00Z")
        assert env.client.get("/api/me/paket-hinweis", cookies=_cookie()).json()["zeigen"] is True

    def test_eine_erfundene_flugnummer_schaltet_den_banner_nicht_fuer_immer_ab(self, env):
        fid = self._flug(env.db)
        r = env.client.post("/api/me/paket-hinweis/weg", json={"flug_id": fid + 10 ** 6},
                            cookies=_cookie())
        assert r.status_code == 400
        assert env.client.get("/api/me/paket-hinweis", cookies=_cookie()).json()["zeigen"] is True


@pytest.mark.skipif(not _NODE, reason="node fehlt")
class TestHinweisImBrowser:
    """Der Kasten selbst — ausgeführt, nicht nur gelesen."""

    def _lauf(self, antwort: dict, im_panel=False) -> dict:
        start = INDEX.index("// PAKET-BANNER-ANFANG")
        ende = INDEX.index("// PAKET-BANNER-ENDE")
        quelle = INDEX[start:ende]
        harness = """
'use strict';
const zustand = { text: '', versteckt: true, dataset: {}, aufrufe: [] };
const kasten = { dataset: zustand.dataset };
Object.defineProperty(kasten, 'hidden', {
  get: () => zustand.versteckt, set: (v) => { zustand.versteckt = v; },
});
const textFeld = { set textContent(v) { zustand.text = v; }, get textContent() { return zustand.text; } };
global.document = {
  documentElement: { classList: { contains: (k) => k === 'vr-panel' && IM_PANEL } },
  getElementById: (id) => id === 'fassung-hinweis' ? kasten
                        : id === 'fassung-hinweis-text' ? textFeld : null,
};
global.fetch = (url, opt) => {
  zustand.aufrufe.push([url, opt && opt.method || 'GET', opt && opt.body || null]);
  return Promise.resolve({ ok: true, json: () => Promise.resolve(ANTWORT) });
};
QUELLE
_fassungenPruefen();
setTimeout(() => {
  // ERST ablesen, DANN wegklicken -- sonst misst der Test seinen eigenen Klick.
  const gesehen = { text: zustand.text, versteckt: zustand.versteckt };
  _fassungHinweisWeg();
  console.log(JSON.stringify(Object.assign(gesehen, {
    danach_versteckt: zustand.versteckt, aufrufe: zustand.aufrufe })));
}, 30);
"""
        js = (harness
              .replace("IM_PANEL", "true" if im_panel else "false")
              .replace("ANTWORT", json.dumps(antwort))
              .replace("QUELLE", quelle))
        p = subprocess.run([_NODE, "-e", js], capture_output=True, text=True, timeout=20)
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout.strip().splitlines()[-1])

    def _antwort(self, *arten, zeigen=True):
        return {"flug_id": 77, "zeigen": zeigen,
                "zeilen": [{"art": a, "text": "Text zu " + a} for a in arten]}

    def test_ein_mangel_zeigt_den_kasten(self):
        z = self._lauf(self._antwort("bruegge_alt"))
        assert z["versteckt"] is False and z["text"] == "Text zu bruegge_alt"
        assert z["aufrufe"][0][0] == "/api/me/paket-hinweis"

    def test_mehrere_maengel_stehen_untereinander(self):
        z = self._lauf(self._antwort("bruegge_alt", "kniebrett_alt"))
        assert z["text"] == "Text zu bruegge_alt\nText zu kniebrett_alt"

    def test_ohne_mangel_bleibt_es_still(self):
        assert self._lauf(self._antwort())["versteckt"] is True

    def test_weggeklickt_auf_einem_anderen_geraet_bleibt_weg(self):
        assert self._lauf(self._antwort("bruegge_fehlt", zeigen=False))["versteckt"] is True

    def test_im_kniebrett_bleibt_das_paket_seinem_eigenen_hinweis_ueberlassen(self):
        """Dort meldet die Hülle die wirklich laufende Fassung — zwei Kästen wären dieselbe
        Nachricht zweimal."""
        assert self._lauf(self._antwort("kniebrett_alt"), im_panel=True)["versteckt"] is True
        z = self._lauf(self._antwort("bruegge_alt", "kniebrett_alt"), im_panel=True)
        assert z["versteckt"] is False and z["text"] == "Text zu bruegge_alt"

    def test_wegklicken_meldet_den_flug_an_den_server(self):
        z = self._lauf(self._antwort("bruegge_fehlt"))
        assert z["danach_versteckt"] is True
        url, methode, koerper = z["aufrufe"][-1]
        assert (url, methode) == ("/api/me/paket-hinweis/weg", "POST")
        assert json.loads(koerper) == {"flug_id": 77}


class TestBeideEnden:
    """Server und Seite müssen denselben Endpunkt meinen."""

    def test_die_seite_fragt_den_endpunkt_den_es_gibt(self):
        assert "/api/me/paket-hinweis" in INDEX and "/api/me/paket-hinweis/weg" in INDEX
        quelle = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(
            encoding="utf-8")
        assert '@app.get("/api/me/paket-hinweis")' in quelle
        assert '@app.post("/api/me/paket-hinweis/weg")' in quelle

    def test_der_banner_wird_auch_ohne_neuladen_wieder_geprueft(self):
        """Sonst sieht ihn nach dem Flug nur, wer die Seite neu lädt."""
        assert re.search(r"setInterval\(_fassungenPruefen,\s*10 \* 60 \* 1000\)", INDEX)

    def test_der_endpunkt_liegt_nicht_hinter_dem_gate(self):
        """`/api/me` steht in der Allowlist — sonst käme die Antwort nie an."""
        assert any(p in ("/api/me",) for p in main._GATE_ALLOW_PREFIXES)
