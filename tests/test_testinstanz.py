"""Testinstanz (test-radar.devprops.de) aus dem Admin starten und stoppen.

Die App kann und soll Docker nicht steuern (kein Socket im Container). Sie legt nur eine
Anforderung als Datei neben die Datenbank; auf dem Server liest ein systemd-Pfadwächter sie und
ruft `test-radar start|stop`. Der Stand kommt auf demselben Weg zurück (status.json)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.auth import make_admin_token, make_confirm_token
from app.database import init_db

SECRET = "s3cr3t-key"
PW = "test-admin-pw"
WURZEL = Path(__file__).resolve().parents[1]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    p = str(tmp_path / "t.db")
    init_db(p)
    settings = SimpleNamespace(
        DB_PATH=p, CALLSIGN_PREFIX="FRS", SECRET_KEY=SECRET, ADMIN_PASSWORD=PW,
        SSO_SECRET="", FORUM_SSO_URL="", FORUM_SSO_CALLBACK="",
        USER_SESSION_MAX_AGE_SEC=3600, OPENAIP_API_KEY="", VAPID_PUBLIC_KEY="",
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    main._reset_gate_cache()
    ordner = tmp_path / "testinstanz"
    return SimpleNamespace(client=TestClient(main.app), ordner=ordner)


def _admin():
    return {"fs_admin": make_admin_token(SECRET, PW),
            "fs_confirm": make_confirm_token(SECRET, PW, 9_999_999_999)}


def test_ohne_admin_kein_zugriff(env):
    assert env.client.get("/api/admin/testinstanz").status_code in (401, 403)
    assert env.client.post("/api/admin/testinstanz", json={"aktion": "start"}).status_code in (401, 403)
    assert not env.ordner.exists()


def test_stand_ohne_statusdatei_heisst_aus(env):
    d = env.client.get("/api/admin/testinstanz", cookies=_admin()).json()
    assert d["laeuft"] is False and d["angefordert"] is None
    assert d["adresse"] == "https://test-radar.devprops.de"


@pytest.mark.parametrize("aktion", ["start", "stop"])
def test_anforderung_wird_als_datei_abgelegt(env, aktion):
    r = env.client.post("/api/admin/testinstanz", json={"aktion": aktion}, cookies=_admin())
    assert r.status_code == 200
    assert (env.ordner / "anforderung").read_text() == aktion
    assert env.client.get("/api/admin/testinstanz", cookies=_admin()).json()["angefordert"] == aktion


@pytest.mark.parametrize("aktion", ["", "restart", "start; rm -rf /", None, 7])
def test_nur_start_und_stop_sind_erlaubt(env, aktion):
    r = env.client.post("/api/admin/testinstanz", json={"aktion": aktion}, cookies=_admin())
    assert r.status_code == 400
    assert not (env.ordner / "anforderung").exists()


def test_stand_kommt_aus_der_statusdatei(env):
    env.ordner.mkdir()
    (env.ordner / "status.json").write_text(json.dumps(
        {"laeuft": True, "seit": "2026-10-03T08:00:00Z", "bis": "2026-10-03T10:00:00Z",
         "version": "16.0.0", "geheim": "x"}))
    d = env.client.get("/api/admin/testinstanz", cookies=_admin()).json()
    assert d["laeuft"] is True and d["bis"] == "2026-10-03T10:00:00Z" and d["version"] == "16.0.0"
    assert "geheim" not in d, "nur bekannte Felder durchreichen"


def test_kaputte_statusdatei_heisst_aus(env):
    env.ordner.mkdir()
    (env.ordner / "status.json").write_text("{kaputt")
    assert env.client.get("/api/admin/testinstanz", cookies=_admin()).json()["laeuft"] is False


def test_admin_seite_hat_schalter_und_link():
    admin = (WURZEL / "app" / "static" / "admin.html").read_text(encoding="utf-8")
    assert 'id="testinstanzLink" href="https://test-radar.devprops.de"' in admin
    assert "/api/admin/testinstanz" in admin
    assert 'id="testinstanzStart"' in admin and 'id="testinstanzStop"' in admin


def test_host_skript_nimmt_nur_start_und_stop_aus_der_datei():
    """Die Datei kommt aus dem Container -- ihr Inhalt darf nie als Befehl ausgewertet werden."""
    sk = (WURZEL / "deploy" / "test-radar" / "test-radar").read_text(encoding="utf-8")
    rumpf = sk[sk.index("anforderung)"):]
    assert 'case "$wunsch" in' in rumpf and "start|stop)" in rumpf
    assert "eval" not in sk
    for k in ["VAPID_PRIVATE_KEY", "TELEGRAM_BOT_TOKEN", "ANTHROPIC_API_KEY"]:
        assert k in sk, f"{k} muss in der Kopie geleert werden"
    assert "DELETE FROM push_subscriptions" in sk
    assert "--on-active=2h" in sk


def test_anfordern_verlangt_die_passwort_bestaetigung(env):
    nur_admin = {"fs_admin": make_admin_token(SECRET, PW)}
    r = env.client.post("/api/admin/testinstanz", json={"aktion": "start"}, cookies=nur_admin)
    assert r.status_code == 403 and r.json()["detail"] == "confirm_required"
    assert not (env.ordner / "anforderung").exists()


def test_datenkopie_liegt_nie_in_tmp():
    sk = (WURZEL / "deploy" / "test-radar" / "test-radar").read_text(encoding="utf-8")
    assert "/tmp" not in sk.replace("Nie ueber /tmp", "")
    assert 'chmod 700 "$ORT/data"' in sk


def test_im_uebergabeordner_arbeitet_nie_root():
    """Der Ordner gehoert dem Container -- ein Symlink darin darf root nichts ueberschreiben lassen."""
    sk = (WURZEL / "deploy" / "test-radar" / "test-radar").read_text(encoding="utf-8")
    for zeile in sk.splitlines():
        if "$UEBERGABE" in zeile or '"$datei"' in zeile:
            z = zeile.strip()
            if z.startswith(("#", "UEBERGABE=", "datei=", "status)")):
                continue
            # datei_schreiben schreibt selbst als containersvc (und ohne Symlink-Folgen).
            assert "sudo -u containersvc" in z or "datei_schreiben " in z, zeile


def test_sitzung_der_testinstanz_wird_geprueft_und_beim_stoppen_geleert():
    """Die Marke landet in einer nginx-Datei -- nur ein Wert aus erlaubten Zeichen darf hinein,
    und nach dem Stoppen darf keine gueltige Sitzung liegen bleiben. Name und CID stehen nicht
    im (oeffentlichen) Repo."""
    sk = (WURZEL / "deploy" / "test-radar" / "test-radar").read_text(encoding="utf-8")
    assert "*[!A-Za-z0-9._=-]*" in sk
    stop = sk[sk.index("stoppen() {"):]
    assert stop.index("sitzung_zu") < stop.index("down")
    assert "htpasswd" not in sk and "auth_basic" not in (WURZEL / "deploy" / "test-radar" / "test-radar.devprops.de.conf").read_text()
    assert "TEST_NAME=" not in sk and "TEST_CID=" not in sk


def test_kopie_bekommt_eigene_schluessel_und_das_ende_steht_vor_dem_start():
    """Sicherheitspruefung 03.10.2026: Eine in der Kopie ausgestellte Sitzung darf in der
    echten App nichts gelten (eigener SECRET_KEY je Lauf). Und das automatische Ende wird
    vorgemerkt, BEVOR etwas scheitern kann -- sonst liefe eine halb gestartete Kopie weiter."""
    sk = (WURZEL / "deploy" / "test-radar" / "test-radar").read_text(encoding="utf-8")
    start = sk[sk.index("starten() {"):sk.index("sitzung_ausstellen() {")]
    assert "for k in SECRET_KEY SSO_SECRET; do" in start and "secrets.token_hex" in start
    assert start.index("--on-active=2h") < start.index('"${compose[@]}" up -d')
    assert "sitzung_ausstellen ||" in start


def test_admin_der_kopie_sagt_dass_man_in_ihr_ist(env):
    """Nutzerfund 03.10.2026: Im Admin der Testinstanz stand „Aus.“, waehrend sie lief."""
    env.ordner.mkdir()
    (env.ordner / "status.json").write_text(json.dumps({"laeuft": True, "hier": True, "bis": "2026-10-03T10:00:00Z"}))
    d = env.client.get("/api/admin/testinstanz", cookies=_admin()).json()
    assert d["hier"] is True
    admin = (WURZEL / "app" / "static" / "admin.html").read_text(encoding="utf-8")
    assert "if (d.hier) {" in admin and "Du bist gerade in der Testinstanz" in admin
    sk = (WURZEL / "deploy" / "test-radar" / "test-radar").read_text(encoding="utf-8")
    assert 'hier' in sk and '$ORT/data/testinstanz/status.json' in sk


def test_ohne_marke_ist_man_nicht_in_der_kopie(env):
    assert env.client.get("/api/admin/testinstanz", cookies=_admin()).json()["hier"] is False


def test_zugangslink_nur_wenn_er_auf_die_testadresse_zeigt(env):
    env.ordner.mkdir()
    gut = "https://test-radar.devprops.de/_zugang/" + "ab12" * 12
    for wert, erwartet in [(gut, gut), ("https://boese.example/_zugang/" + "ab12" * 12, None),
                           ("javascript:alert(1)", None), (7, None)]:
        (env.ordner / "status.json").write_text(json.dumps({"laeuft": True, "zugang": wert}))
        assert env.client.get("/api/admin/testinstanz", cookies=_admin()).json()["zugang"] == erwartet


def test_ohne_zugangscookie_kein_zutritt():
    conf = (WURZEL / "deploy" / "test-radar" / "test-radar.devprops.de.conf").read_text(encoding="utf-8")
    assert "if ($tr_ok = 0) { return 403; }" in conf
    sk = (WURZEL / "deploy" / "test-radar" / "test-radar").read_text(encoding="utf-8")
    assert "set $tr_ok 0;" in sk[sk.index("sitzung_zu() {"):sk.index("sitzung_ausstellen() {")]


def test_dateien_in_container_ordnern_folgen_keinem_symlink():
    """Sicherheitspruefung 03.10.2026: Die Kopie laeuft mit ungeprueftem Code als derselbe
    Benutzer wie die echte App. Ein von ihr gelegter Symlink duerfte sonst beim naechsten
    Start eine Datei der echten App ueberschreiben."""
    sk = (WURZEL / "deploy" / "test-radar" / "test-radar").read_text(encoding="utf-8")
    assert "O_NOFOLLOW" in sk and "O_EXCL" in sk
    assert 'rm -rf "$ORT/data/testinstanz"' in sk
    assert 'open(ziel, "w")' not in sk and 'open(sys.argv[1], "w")' not in sk


def test_geheimes_steht_nie_in_einer_befehlszeile():
    """Sicherheitspruefung 03.10.2026: Zugangslink und Schluessel standen als Argument in der
    Prozessliste. Jetzt laufen sie ueber die Standardeingabe bzw. entstehen im Prozess selbst."""
    sk = (WURZEL / "deploy" / "test-radar" / "test-radar").read_text(encoding="utf-8")
    assert "json.load(sys.stdin)" in sk
    assert "sed -i \"s|^$k=.*|$k=$(" not in sk
    for zeile in sk.splitlines():
        if "datei_schreiben " in zeile and not zeile.startswith("datei_schreiben()"):
            assert zeile.strip().startswith("| datei_schreiben"), zeile


def test_version_aus_der_kopie_wird_auf_ziffern_beschraenkt():
    sk = (WURZEL / "deploy" / "test-radar" / "test-radar").read_text(encoding="utf-8")
    stelle = sk.index("from app.version import VERSION")
    assert "tr -cd '0-9.'" in sk[stelle:stelle + 200] and "head -n 1" in sk[stelle:stelle + 200]
