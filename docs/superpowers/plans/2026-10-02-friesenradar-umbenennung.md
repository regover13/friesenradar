# FriesenRadar (V16 „Lichtblick“) – Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended — der Plan ist überwiegend Betrieb mit Nutzerfreigaben, kein Code am Stück) or superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FriesenSpy heißt überall, wo ein Mensch liest, FriesenRadar — App, Forum, Repo, Image, Server, Pakete, laufende Doku —, ohne dass ein Mitglied Einstellungen, Tablet-Bindung oder Ergebnisse verliert.

**Architecture:** Vier Etappen: (1) Server-Umzug samt Repo- und Image-Umbenennung, unsichtbar für Mitglieder; (2) Release 16.0.0 „Lichtblick“ mit dem sichtbaren Namen, Vorschau-Schalter wird zum Normalfall, Forum am selben Tag; (3) Kniebrett-Paket 3.0.0 und neue FriesenBrügge (Bau auf dem Simulator-Rechner); (4) Aufräumen. Technische Konstanten (`friesenspy_*`-Merker, `friesenspy_device`, `source: 'friesenspy'`, `fs_*`-Cookies, Code-Bezeichner) bleiben — keine Datenmigration.

**Tech Stack:** FastAPI/SQLite (Docker Compose, GHCR, GitHub Actions), nginx, Let's Encrypt, fail2ban, rclone/OneDrive-Backup, Watchtower; Einzeldatei-Frontend; MSFS-EFB-Paket (TypeScript, Bau unter Windows); FriesenBrügge (C++, Bau unter Windows).

**Spec:** `docs/superpowers/specs/2026-10-02-friesenradar-umbenennung-design.md` (Issues #51–#56)

## Global Constraints

- **Der Name ist FriesenRadar.** Neue Texte, Commits, Changelog, Forum: nur FriesenRadar. „friesenspy“ im Code ist technische Konstante, kein Name (Gedächtnis `project_friesenradar-name`).
- **Bleiben als Konstante (nicht anfassen):** Merker-Schlüssel `friesenspy_*`, Gerätekennung `friesenspy_device`, Schnittstellenwert `source: 'friesenspy'`, Cookie-Namen `fs_*`, Bezeichner und Docstrings im Code.
- **Bleiben als Geschichte:** CHANGELOG-Einträge vor 16.0.0, datierte Doku (`docs/superpowers/`, Dateien mit Datum im Namen), Commit-Historie, Forumsbeiträge, Erwähnungen in anderen Repos.
- **Logofarben nie ändern;** nur offizielle Fassungen. App-Symbol: rotes Flugzeug auf Weiß.
- **`friesenspy.devprops.de` bleibt stilles Alias** im selben Vhost; nirgends mehr genannt.
- **Technische Heimat** für Paket und Brügge: `friesenradar.devprops.de`. Für Mitglieder: `radar.friesenflieger.de` (sobald DNS steht, sonst `friesenradar.devprops.de`).
- **Geschützt, nur mit ausdrücklicher Freigabe:** `/opt/*/config.env`, alles auf friesenflieger.de (Forum-Schreiben, Board-Vorlage, Website).
- **Vor jedem Push:** `git fetch` + Rebase; pytest-Exit-Code selbst prüfen; zu Flugzeiten nicht deployen (nginx-Log: CoherentGT, `/api/sse`).
- **Tests:** `/home/claude/.venv-friesenspy/bin/python -m pytest -n 4 tests/ -q -p no:cacheprovider` (venv wird in Task 7 umbenannt).
- **SQLite nie per `cp`** — `.backup` oder Checkpoint bei gestopptem Container.

## Review Focus

1. **Backup nach dem Umzug:** Läuft `backup_onedrive.sh` mit den neuen Pfaden durch und landet das Archiv in `Server-Backup/friesenradar/`? (Task 2, Probelauf)
2. **Alte Brüggen und Kniebretter nach dem Umzug:** Melden sie weiter über `friesenspy.devprops.de` (nginx-Log 200 auf `/api/bruegge/melden`)? (Task 2, Gegenprobe)
3. **Forum-Login über alle drei Adressen** nach dem Umzug, inkl. `FORUM_SSO_CALLBACK` in `config.env`. (Task 2)
4. **Watchtower** prüft den neuen Container nicht (Liste) und meldet keinen 401. (Task 2)
5. **Installierte PWAs** behalten Namen und Symbol bis zur Neuinstallation — steht in der Ankündigung. (Task 4)

---

### Task 1: Umzug im Repo vorbereiten (Branch `umzug`, noch nicht ausliefern)

Alles, was Pfade und Namen von Repo, Image und Server betrifft. Wird erst im Umzugsfenster (Task 2) nach `main` gebracht, weil es `/opt/friesenradar` voraussetzt.

**Files:**
- Modify: `docker-compose.yml` (Dienst `friesenradar`, Image `ghcr.io/regover13/friesenradar:latest`, Volume `./data:/opt/friesenradar/data`)
- Modify: `.github/workflows/deploy.yml` (`IMAGE`, `cd /opt/friesenradar`, Meldetexte „FriesenRadar …“, Health-Check-Text auf `friesenradar.devprops.de`)
- Modify: `app/config.py` (Vorgabe `DB_PATH = "/opt/friesenradar/data/friesenradar.db"`, Kommentar zur Paketdatei)
- Modify: `app/main.py:708,811` (Paketdatei `efb/friesenradar-efb.zip`, Download-Name `friesenflieger-friesenradar-efb.zip`) — **mit Rückfall:** existiert die neue Datei nicht, alte `efb/friesenspy-efb.zip` ausliefern (bis Task 5 gebaut ist)
- Rename: `nginx/friesenspy.devprops.de.conf` → `nginx/friesenradar.devprops.de.conf` (`server_name friesenradar.devprops.de friesenspy.devprops.de;` — neuer Name zuerst; Zertifikatspfad `live/friesenradar.devprops.de/`)
- Modify: `friesenbruegge/msfs/paket.ps1`, `friesenbruegge/xplane/paket.ps1` (Ziel `server:/opt/friesenradar/data/efb/…`)
- Test: `tests/test_paket_download.py` (neu oder bestehende Download-Tests erweitern)

- [ ] **Step 1:** Branch `umzug` von `main`.
- [ ] **Step 2: Test zuerst** für den Paket-Download: liefert `friesenradar-efb.zip`, wenn vorhanden; sonst `friesenspy-efb.zip`; Download-Dateiname `friesenflieger-friesenradar-efb.zip`. Rot laufen lassen.
- [ ] **Step 3:** `main.py` anpassen, Test grün.
- [ ] **Step 4:** Übrige Dateien oben ändern. `grep -rn "/opt/friesenspy\|regover13/friesenspy" --include=*.py --include=*.yml --include=*.ps1 --include=*.conf .` muss leer sein (außer datierter Doku).
- [ ] **Step 5:** Suite grün. Commit auf `umzug`, push nach `origin/umzug` (kein Deploy, Workflow läuft nur auf `main`).

---

### Task 2: Server-Umzug (Wartungsfenster, Nutzer gibt Bescheid)

**Nur, wenn der Nutzer das Fenster freigibt.** Dauer ~15 min, davon ~5 min Ausfall (Bau des Images).

**Vorab (ohne Ausfall):**
- [ ] **Step 1:** `COORDINATION.md`-Eintrag: „Umzug FriesenRadar am …, Pfade ändern sich: /opt/friesenradar, Repo regover13/friesenradar, ~/projects/friesenradar“. Push (nur .md, kein Deploy).
- [ ] **Step 2:** Neues Zertifikat (läuft parallel zum alten): `sudo certbot certonly --webroot -w /var/www/html --cert-name friesenradar.devprops.de -d friesenradar.devprops.de -d friesenspy.devprops.de [-d radar.friesenflieger.de, falls DNS steht]`.
- [ ] **Step 3:** `config.env`-Änderung dem Nutzer zeigen und **Freigabe holen**: `DB_PATH=/opt/friesenradar/data/friesenradar.db`, `FORUM_SSO_CALLBACK=https://friesenradar.devprops.de/auth/forum/callback` (Rückfall-Adresse; die Liste in `_SSO_RUECKSPRUNG_HOSTS` deckt alle drei ab). Sicherung `config.env.bak-umzug`.
- [ ] **Step 4:** Flugbetrieb prüfen (nginx-Log der letzten 10 min, ohne Nutzer-IP).

**Umzug:**
- [ ] **Step 5:** `cd /opt/friesenspy && docker compose down`. Gegenprobe: `docker ps | grep friesenspy` leer.
- [ ] **Step 6:** DB sichern und Zeilen zählen: `sqlite3 data/friesenspy.db "PRAGMA wal_checkpoint(TRUNCATE)"`, `.backup /opt/backup/friesenspy-vor-umzug.db`, Zeilenzahlen von `flights`, `position_history`, `panel_prefs`, `progress_snapshot` notieren.
- [ ] **Step 7:** `sudo mv /opt/friesenspy /opt/friesenradar`; `mv data/friesenspy.db data/friesenradar.db` (WAL/SHM sind nach dem Checkpoint leer; vorhandene `-wal`/`-shm` mitbenennen). `config.env` anpassen (Step 3).
- [ ] **Step 8: GitHub:** `gh repo rename friesenradar -R regover13/friesenspy --yes`. Lokales Remote: `git remote set-url origin https://github.com/regover13/friesenradar.git`. Beschreibung: „VATSIM Live-Tracker für die FriesenFlieger“ (unverändert, enthält keinen Namen).
- [ ] **Step 9:** Branch `umzug` nach `main` (Rebase, Suite grün, push). Der Workflow baut `ghcr.io/regover13/friesenradar` und deployt nach `/opt/friesenradar` → Container `friesenradar-friesenradar-1`.
- [ ] **Step 10: nginx:** `nginx/friesenradar.devprops.de.conf` nach `/etc/nginx/sites-available/`, Symlink in `sites-enabled`, alten Symlink und alte Datei entfernen (vorher nach `/root/friesenspy-nginx-vor-umzug.conf` sichern), `nginx -t`, `reload`. Die drei `.bak`-Dateien in `sites-available` nach `/root/` verschieben.
- [ ] **Step 11: Gegenproben** (alle müssen stimmen, sonst zurück auf den alten Stand):
  - `curl -s -o /dev/null -w "%{http_code}"` auf alle drei Adressen → 401/200 wie vorher
  - Zeilenzahlen aus Step 6 im laufenden Container identisch
  - Forum-Login im Browser über `friesenradar.devprops.de` (Nutzer) bzw. `curl` auf `/auth/forum/login` → 302 mit passender Rücksprungadresse
  - nginx-Log: `/api/bruegge/melden` und `/panel` über `friesenspy.devprops.de` weiter 200 (Review Focus 2)

**Nachziehen (ohne Ausfall):**
- [ ] **Step 12: fail2ban:** Repo `devprops.de`: `fail2ban/jail.d/friesenspy.conf` → `friesenradar.conf` (`[friesenradar]`, `filter = friesenradar`), `filter.d/friesenspy.conf` → `friesenradar.conf`. Auf dem Server installieren, alte Dateien entfernen, `fail2ban-client reload`. Gegenprobe: `fail2ban-regex` mit drei Probezeilen (wie am 02.10.2026), `fail2ban-client status friesenradar`.
- [ ] **Step 13: Backup** (Repo `server-backup`): `FS_DIR=/opt/backup/friesenradar`, Archivname `friesenradar-${DATE}.tar.gz`, Quelle `/opt/friesenradar/data/friesenradar.db`, Ziel `onedrive:/Server-Backup/friesenradar/`, Funktionsnamen und Labels. `/opt/backup/friesenspy` → `/opt/backup/friesenradar` (alte Archive rotieren von selbst heraus). **Probelauf** nur dieses Teils (Review Focus 1), Archiv im OneDrive prüfen. Commit, Push, auf dem Server einspielen wie im Repo beschrieben.
- [ ] **Step 14: Watchtower** (Repo `vaultwarden-setup`): in `WATCHTOWER_DISABLE_CONTAINERS` `friesenspy-friesenspy-1` → `friesenradar-friesenradar-1`. Auf dem Server einspielen, `docker compose up -d --no-deps watchtower` in `/opt/vaultwarden`. Gegenprobe: `docker inspect watchtower` zeigt die neue Liste.
- [ ] **Step 15:** Zertifikat `friesenspy.devprops.de` löschen (`certbot delete --cert-name friesenspy.devprops.de`), nachdem nginx auf das neue zeigt.
- [ ] **Step 16:** `/etc/passwd`: `sudo usermod -c "… Container hermes, mailsync und friesenradar …" containersvc`.
- [ ] **Step 17: Serverdoku** (Repo `devprops.de`, `claude-leitstand/projects-CLAUDE.md`): Dienste-Tabelle, Repos-Tabelle, Deploy-Tabelle, Pfade; veraltete Kopie `nginx/sites-available/friesenspy.devprops.de.conf` dort löschen (maßgeblich ist das App-Repo). Push.
- [ ] **Step 18:** Altes Image lokal: `docker rmi ghcr.io/regover13/friesenspy:latest` (nachdem kein Container es nutzt), Gegenprobe `docker images | grep friesenspy` leer.

---

### Task 3: Release 16.0.0 „Lichtblick“ (sichtbar)

**Files:**
- Modify: `app/static/index.html` — Vorschau wird Normalfall:
  - Kopfskript-Block `radarHosts` entfernen; `html.radar`-Präfix aus allen Regeln streichen (Regeln gelten immer); `.logo-alt` samt altem Schriftzug und Raute entfernen; `.logo-radar { display: none }` entfernen.
  - `_appName()` → `return 'FriesenRadar';`, `_radarAnwenden()` und der Aufruf in `fsRefreshSession` entfernen; `_appNameEinsetzen` setzt nur noch `.app-name`/Titel (Manifest-Umschaltung entfällt, s. u.).
  - `<title>`, `application-name`, `apple-mobile-web-app-title` fest „FriesenRadar“; `.app-name`-Spans durch festen Text ersetzen.
  - Kniebrett-Leiste: Regeln aus der Vorschau gelten fest (Streifen 42 px, Logo).
  - Download-Hinweise `friesenspy.devprops.de/download` → `radar.friesenflieger.de/download` (bzw. `friesenradar.devprops.de`).
- Modify: `app/static/manifest.webmanifest` (Inhalt von `radar/manifest.webmanifest`, Symbolpfade auf die Wurzel); Symbole `icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, `apple-touch-icon.png` durch die aus `static/radar/` ersetzen; `favicon.ico` aus `radar/favicon-32.png` erzeugen (Pillow, 16/32/48); `static/radar/` danach löschen.
- Modify: `app/static/sw.js` (Rückfalltitel „FriesenRadar“), `admin.html` (3), `efb.html` (5), `impressum.html` (4), `datenschutz.html` (8).
- Modify: `app/main.py` — FastAPI-Titel; Tablet-Anmeldeseite (Z. ~5236–5408); Test-Push-Titel (Z. ~5744, 5780); AIP-User-Agent (Z. 8058); Widget-Vorschau (Z. ~8939–8986: Titel, Einbettungscode auf `https://radar.friesenflieger.de/widget`); Widget selbst (Z. ~9103–9112: Link, „✈ FriesenRadar“, Fußzeile ohne alten Domainnamen); `_radar_vorschau_fuer` und `radar_vorschau` in `/api/me` entfernen.
- Modify: `README.md` (alle Nennungen, Links auf neue Adresse und neues Repo), `CLAUDE.md` (Titel, Projektstruktur, Deployment-Pfade, **neuer Abschnitt „Name“**: Der Name ist FriesenRadar; „friesenspy“ in Code, Merkern, Gerätekennung und Schnittstellen ist technische Konstante; datierte Doku ist Geschichte und kein Vorbild für Namen), `COORDINATION.md` (Kopf), undatierte Doku: `docs/api.md`, `architecture.md`, `bruegge-arten-ausbau.md`, `deployment.md`, `efb-panel-debugging.md`, `fable-analyse-auftrag.md`, `flugplatzkarten-passen.md`, `fse-daten-weltweit.md`, `gps-flugerkennung.md`, `impressum-recherche.md`, `kutter-zuladung-invalidierung.md`, `offene-aufgaben.md`, `uebergabe-an-die-server-sitzung.md`, `uebergabe-msfs-build.md` (nicht `release-14.0.0-…`, das ist Geschichte).
- Modify: `app/CHANGELOG.json` (16.0.0 „Lichtblick“, `highlight: false`).
- Modify: `scripts/dunkel_vergleich.py` (`NEU_ERLAUBT`-Muster für `html.radar` entfernen) — oder das Werkzeug, falls nicht mehr gebraucht, behalten wie es ist.
- Test: `tests/test_radar_vorschau.py` → umbauen zu `tests/test_name_friesenradar.py`

- [ ] **Step 1: Test zuerst** `tests/test_name_friesenradar.py`:

```python
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
    return "\n".join(l for l in text.split("\n") if not l.strip().startswith(("//", "#")))


def test_kein_alter_name_wo_menschen_lesen():
    for rel in SICHTBAR:
        t = _ohne_kommentare((ROOT / rel).read_text(encoding="utf-8"))
        # Technische Konstanten (Merker-Schluessel, source-Wert, Geraetekennung) sind erlaubt.
        t = re.sub(r"friesenspy_[a-z_]+|'friesenspy[-a-z_]*'|\"friesenspy[-a-z_]*\"", "", t)
        assert not re.search(r"friesen ?spy", t, re.I), rel


def test_widget_und_anmeldeseite_heissen_friesenradar():
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "✈ FriesenRadar" in main and "✈ FriesenSpy" not in main
    assert "<title>FriesenRadar – Anmeldung</title>" in main


def test_vorschau_schalter_ist_weg():
    idx = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
    assert "html.radar" not in idx and "_radarAnwenden" not in idx and "radarHosts" not in idx
```

- [ ] **Step 2:** Rot laufen lassen (README und Seiten nennen den alten Namen).
- [ ] **Step 3:** Änderungen oben umsetzen. Erlaubte Fundstellen von `friesen ?spy` danach nur noch: Konstanten, Kommentare, datierte Doku, CHANGELOG vor 16.0.0, `deploy/forum/sso.php`-Liste (enthält die Alias-Adresse als erlaubten Rücksprung — technisch).
- [ ] **Step 4:** Browser-Gegenprobe (lokal, leere DB): Website hell/dunkel, Handy, Kniebrett (`?vr=1`), Widget `/widget`, Anmeldeseite `/auth/device`; Titel, Logo, Manifest. `scripts/dunkel_vergleich.py` gegen `HEAD` zeigt nur die erwarteten Änderungen der Kopfzeile.
- [ ] **Step 5:** Suite grün, Commit. **Auslieferung erst am Tag der Forum-Umstellung (Task 4), Flugbetrieb prüfen.**

---

### Task 4: Forum und Ankündigung (am Tag von 16.0.0)

Alles auf friesenflieger.de nur mit Freigabe; Schreiben einzeln erfragen.

- [ ] **Step 1:** Unterforum „FriesenSpy“ (f=116, Tools und AddOns → Mapping-Tools) in „FriesenRadar“ umbenennen — **Nutzer oder Heinz** über ACP → Foren.
- [ ] **Step 2:** Thema 1785 „FriesenSpy – Entwicklungsstand“ → „FriesenRadar – Entwicklungsstand“: ersten Beitrag mit `forum_read_topic` finden (Autor, Inhalt prüfen), Betreff per `forum_edit_post` ändern, Text unverändert mitgeben (`previous_text` sichern). **Erst nach Freigabe.**
- [ ] **Step 3:** Widget-Einbettung umstellen: Board-Vorlage (Heinz) und www.friesenflieger.de (Micha) auf `https://radar.friesenflieger.de/widget`. Text für Heinz/Micha im Chat vorbereiten.
- [ ] **Step 4:** Ankündigung „V16 - Lichtblick“ im Thema 1785: Entwurf im Chat (Ton: `tone-of-voice`, kurz, wenig Formatierung), nach Freigabe posten, Betreff nachziehen. Inhalt: neuer Name, neue Adresse, Logo/Symbol, **installierte App einmal neu installieren**, Kniebrett-Paket und Brügge folgen (Task 5/6).
- [ ] **Step 5:** Gegenprobe: `forum_list_forums` (seit Hermes `5bdcc1c` mit allen Ebenen) nennt kein „FriesenSpy“ mehr; Board-Startseite und Website zeigen das Widget mit „FriesenRadar“.

---

### Task 5: Kniebrett-Paket 3.0.0 (Code hier, Bau auf dem Simulator-Rechner)

**Files:**
- Rename: `msfs-panel/PackageSources/FriesenSpy/` → `msfs-panel/PackageSources/FriesenRadar/` (inkl. `FriesenSpy.tsx`/`.scss` → `FriesenRadar.*`)
- Modify: `manifest.json` (`title` „FriesenRadar“, `package_version` 3.0.0, Release-Notiz), `package.json` (`@efb/friesenradar`), `build.js`, `build-package.ps1` (Pfade, Paketordner `friesenflieger-friesenradar-efb`, `efb_apps/FriesenRadar`)
- Modify: `FriesenRadar.tsx` — URL `https://friesenradar.devprops.de/panel` und `/auth/device`; App-Name; **`DEVICE_KEY` bleibt `"friesenspy_device"`** (Kommentar: technische Konstante, Bindung bleibt); `PAKET_VERSION` 3.0.0
- Modify: `src/Assets/app-icon.svg` (rotes Flugzeug auf Weiß, aus `static/radar/icon.svg`)
- Modify: Server: Hinweis auf veraltetes Paket (vorhandener `paket_version`-Mechanismus) nennt „Bitte den alten Ordner `friesenflieger-friesenspy-efb` aus dem Community-Ordner löschen“.

- [ ] **Step 1:** Änderungen im Repo, Tests für den Paket-Hinweis (Text, Mindestversion 3.0.0).
- [ ] **Step 2:** Übergabe an die Sitzung auf dem Simulator-Rechner (`docs/uebergabe-msfs-build.md` nachziehen): bauen, testen im Sim (Bindung bleibt, Logo, Name), Zip nach `/opt/friesenradar/data/efb/friesenradar-efb.zip`.
- [ ] **Step 3:** Nach Ablage: Download liefert das neue Paket (Task 1 Rückfall greift nicht mehr). Alte Datei `friesenspy-efb.zip` löschen.

---

### Task 6: FriesenBrügge (Code hier, Bau auf dem Simulator-Rechner)

**Files:** `friesenbruegge/msfs/bruegge.cpp:129` (`BRUEGGE_URL`), `friesenbruegge/xplane/netz.h:98,102,133`, `friesenbruegge/xplane/bruegge.cpp:424,1007` (Texte), `LIESMICH.txt`, Paketskripte (Task 1).

- [ ] **Step 1:** URL auf `https://friesenradar.devprops.de/api/bruegge/melden`, Texte „FriesenRadar“, Versionsnummer erhöhen.
- [ ] **Step 2:** Übergabe an die Sitzung auf dem Simulator-Rechner: bauen, im Sim prüfen (Meldungen kommen über die neue Adresse an: nginx-Log), Pakete hochladen.
- [ ] **Step 3:** Alte Brüggen melden weiter über das Alias (kein Zwang zum Update).

---

### Task 7: Claude-Arbeitsumgebung (direkt nach Task 2)

- [ ] **Step 1:** `~/projects/friesenspy` → `~/projects/friesenradar` (`mv`, Remote ist seit Task 2 umgestellt). Alter Worktree `~/projects/friesenspy-posix`: `git worktree remove` (Branch längst in main). `~/projects/friesenspy-aip-arbeitsstand.md` → `friesenradar-aip-arbeitsstand.md`.
- [ ] **Step 2:** venv neu anlegen: `python3 -m venv ~/.venv-friesenradar`, `pip install -r requirements.txt -r requirements-test.txt playwright`, `playwright install chromium`; altes `~/.venv-friesenspy` löschen. Gedächtnisnotiz `reference_friesenspy-tests-eigenes-venv` umschreiben.
- [ ] **Step 3:** `~/projects/.claude/settings.local.json`: Pfade `friesenspy` → `friesenradar` (nur Pfade).
- [ ] **Step 4:** Gedächtnis: Notizen mit Pfaden/Repo/Adressen auf den neuen Stand; Dateinamen `*friesenspy*` → `*friesenradar*`, `MEMORY.md`-Zeilen nachziehen. Inhaltliche Geschichte („am 05.09. in FriesenSpy …“) darf bleiben, aber jede Notiz, die einen Namen für künftige Arbeit vorgibt, sagt FriesenRadar.

---

### Task 8: Aufräumen und Entscheidung zum Alias (später)

- [ ] **Step 1:** Altes GHCR-Paket `friesenspy` löschen (Nutzer, falls der Token kein `delete:packages` hat).
- [ ] **Step 2:** OneDrive `Server-Backup/friesenspy/`: leert sich durch die Rotation; danach den leeren Ordner löschen.
- [ ] **Step 3:** Nach einigen Wochen nginx-Log auswerten: melden noch alte Brüggen/Pakete über `friesenspy.devprops.de`? Ergebnis in #52; Alias bleibt mindestens wegen der Badges in alten Beiträgen.
- [ ] **Step 4:** Issues #51–#56 schließen.
