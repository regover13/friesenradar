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
- **Technische Heimat** für Paket, Brügge und Widget-Einbettung: `friesenradar.devprops.de`. Für Mitglieder: `radar.friesenflieger.de` — **erst nennen, wenn `curl -sf https://radar.friesenflieger.de/health` gelingt**; bis dahin überall `friesenradar.devprops.de`. Heute zeigt der Name auf den Wildcard-Eintrag des Vereins (217.160.242.47), nicht auf uns.
- **Geschützt, nur mit ausdrücklicher Freigabe:** `/opt/*/config.env`, alles auf friesenflieger.de (Forum-Schreiben, Board-Vorlage, Website).
- **Vor jedem Push:** `git fetch` + Rebase; pytest-Exit-Code selbst prüfen; zu Flugzeiten nicht deployen (nginx-Log: CoherentGT, `/api/sse`).
- **Tests:** `/home/claude/.venv-friesenspy/bin/python -m pytest -n 4 tests/ -q -p no:cacheprovider` (venv wird in Task 7 umbenannt).
- **SQLite nie per `cp`** — `.backup` oder Checkpoint bei gestopptem Container.

## Prüfstand

Vierfach geprüft am 02./03.10.2026: Betrieb (Tasks 1, 2, 7, 8) und Verträglichkeit für Mitglieder
(Tasks 3–6, Spec), jeweils von Fable und Opus. Alle blockierenden Befunde sind unten eingearbeitet;
die Nummern in Klammern (B = Betrieb, V = Verträglichkeit) verweisen auf die Berichte. Der
Ordnername des Kniebrett-Pakets ist entschieden: **Variante B, neuer Ordner** (Nutzer, 03.10.2026, Task 5).

## Stand der Umsetzung (03.10.2026, nachts)

Alles liegt auf Branches, **nichts ist ausgeliefert oder auf dem Server umgestellt**. Die
App-Branches bilden eine Kette, jeder baut auf dem vorigen auf; ausgeliefert wird am Ende
`bruegge-radar` (enthält alle):

| Branch | Inhalt | Task |
|---|---|---|
| `umzug` | Pfade, Image, Compose, nginx, Dockerfile, deploy.yml, Umzugsskript (2× geprobt) | 1, 2 |
| `lichtblick` | 16.0.0: Name, Logo, Symbole, Texte, Download-Name, Teilen-Links | 3 |
| `kniebrett-3` | Paket 3.0.0 im Code (Variante B), Seite erkennt altes Paket | 5 |
| `bruegge-radar` | Brügge 1.19.0 / 1.5.0, Übergabe `docs/uebergabe-friesenradar-pakete.md` | 6 |
| `server-backup` → `friesenradar` | Pfade, Sperre gegen leere DB, README | 2 (Step 1) |
| `devprops.de` → `friesenradar` | fail2ban-Jail/Filter, Serverdoku | 2 (Step 3, 21) |
| `vaultwarden-setup` → `friesenradar` | Watchtower-Liste | 2 (Step 2) |

Suite auf `bruegge-radar`: 3915 grün. Abschluss-Review (Opus) am 03.10.2026: 1 blockierender
Befund (altes Kniebrett-Symbol) und 6 wichtige — alle eingearbeitet.

**Offen beim Nutzer:** Termin Umzug (config.env freigegeben 03.10.), Sim-Prüfung
Paket 3.0.0 nach der Übergabe (Logo in der Vorschau: erledigt 03.10.), Forum (Task 4).

## Review Focus

1. **Leere Datenbank statt Umzug:** Stimmen Mount im Compose, `DB_PATH` in `config.env` und Dateiname nicht überein, legt SQLite still eine leere DB an; Mitglieder sähen eine leere App, und das Backup um 03:00 sicherte die leere Datei. Gegenprobe vor dem Start und Zeilenzahlen direkt danach (Task 2). (B1)
2. **Alte Brüggen und Kniebretter nach dem Umzug** melden weiter über `friesenspy.devprops.de`. Gemessen wird in der **DB** (`bruegge_zuordnung.gesehen_am`, `panel_devices.last_seen_at`), **nicht** im nginx-Log: Erfolgreiche Brügge-Meldungen schreibt `conf.d/bruegge-log.conf` gar nicht ins Log, ein leeres Log hieße dort nichts. (V3)
3. **Forum-Login über alle Adressen** nach dem Umzug, inkl. `FORUM_SSO_CALLBACK`. (Task 2)
4. **Backup läuft in der ersten Nacht mit den neuen Pfaden** und sichert eine nicht leere Datei. (B4)
5. **Push-Benachrichtigungen hängen an der alten Adresse:** 14 Abos von 8 Personen. Wer zusätzlich über die neue Adresse einschaltet, bekommt jede Meldung doppelt. Gehört in die Ankündigung. (V5/V6)

---

### Task 1: Umzug im Repo vorbereiten (Branch `umzug`) — erledigt bis auf Nachträge

Stand `5aaeb47` auf `origin/umzug`, Suite 3910 grün. Umgesetzt: Compose (Dienst `friesenradar`,
Image `ghcr.io/regover13/friesenradar`, Volume `./data:/opt/friesenradar/data`), `deploy.yml`,
`config.py` (Vorgabe `/opt/friesenradar/data/friesenradar.db`), **Dockerfile** (Benutzer, `WORKDIR`,
`ENV DB_PATH`), nginx-Datei umbenannt, Paketskripte, Paketdatei `efb/friesenradar-efb.zip` mit
Rückfall auf `friesenspy-efb.zip`.

**Der Download-Name folgt dem Paketordner in der abgelegten ZIP** (`_efb_download_name`, Branch
`lichtblick`): bis 2.x `friesenflieger-friesenspy-efb.zip`, ab 3.0.0
`friesenflieger-friesenradar-efb.zip`. Er ist zugleich der Ordnername nach dem Entpacken; so
wechselt er erst mit dem neuen Paket (V1, Variante B).

- [ ] **Nachtrag 1:** `deploy.yml` Skript mit `set -euo pipefail` beginnen, damit ein fehlendes Verzeichnis den Lauf abbricht statt in `$HOME` weiterzumachen.
- [ ] **Nachtrag 2:** Grep aus Step 4 wiederholen, diesmal mit `--include=Dockerfile --include=*.sh` (B3).
- [ ] **Nachtrag 3:** Rebase auf `main`, Suite grün, push nach `origin/umzug`.

---

### Task 2: Server-Umzug (Wartungsfenster, Nutzer gibt Bescheid)

> **HALT vor dem Umbau — Nutzer 03.10.2026:** „Frage mich vor dem Umbau nochmal, weil wir doch
> `radar.friesenflieger.de` bei Heinz bestellt haben.“ Vor dem Umzug UND vor dem Ausliefern von
> 16.0.0 den Nutzer fragen, welche Adresse die Texte nennen (Changelog-Punkt „Neue Adresse“,
> README, Forum). Nicht selbst entscheiden, auch wenn DNS schon steht.
> **Ebenfalls Nutzer 03.10.2026:** Kniebrett 3.0.0 und die neue FriesenBrügge gehören ZU
> Lichtblick, nicht „mit dem nächsten Paket“ — beide müssen am Simulator-Rechner gebaut und
> geprüft sein, bevor 16.0.0 hinausgeht.
> **Kniebrett-Ordner (Nutzer 03.10.2026 abends):** Paketordner, Download und abgelegte Datei
> heißen **`friesenkniebrett`** (nicht mehr `friesenflieger-friesenradar-efb` /
> `friesenradar-efb.zip` — wo dieser Plan die alten Namen nennt, gilt der neue; umgesetzt auf
> `bruegge-radar`, 86199bf). Die Brüggen behalten ihre Ordner.
> **Merkposten:** Im Paket steht „Die Anmeldung des Tablets bleibt erhalten“ (Wunsch des
> Nutzers). Scheitert die Prüfung der Gerätebindung am Simulator, muss der Satz aus
> `manifest.json` heraus, und der Changelog-Punkt zum Kniebrett braucht einen Hinweis auf die
> neue Anmeldung — vor dem Verteilen.
> **Paketprüfung am Simulator, 03.10.2026 abends (Sitzung „Lichtblick lokal“ + Server):**
> - Kniebrett 3.0.0 (`friesenkniebrett.zip`, sha256 `26b5e222…e5e4f4`): Gerätebindung bestanden —
>   dieselbe Kennung, `paket=3.0.0`, kein neues Gerät in `panel_devices` (nginx 19:34:28 UTC).
>   App-Name, Symbol, Logo hell/dunkel, Fremdverkehr, Fenster schließen, Anheften: gesehen.
>   Der Merkposten oben ist damit erledigt, der Satz zur Anmeldung bleibt.
> - Brügge MSFS 1.19.0 (`friesenbruegge.zip`, sha256 `8fce0332…d7f41c`): in MSFS 2020 UND 2024
>   Zuordnung, Stellen (rauch_orange) und Abräumen in der Datenbank und im Simulator gesehen.
> - Brügge X-Plane 1.5.0 (CI-Lauf 37112105024, Artefakt `friesenbruegge-xplane`): Log-Zeilen und
>   Zuordnung belegt; Stellen-Test nachgeholt (20:39–20:40 UTC): gesetzt, gesehen, abgeräumt.
> - **Erst nach dem Deploy von 16.0.0 prüfbar:** beide Kniebrett-Pakete nebeneinander
>   (Hinweiskasten, `altesPaketDa()`, Test-Benachrichtigung) — der Kasten gehört zur Seite.
> - Die Pakete liegen auf dem Simulator-Rechner, **nicht** auf dem Server. Hochladen nur auf
>   Wort des Nutzers, nach Umzug und Deploy.
> **TV-Modus (gehört zu 16.0.0):** fertig auf `bruegge-radar`, vom Nutzer am Fire TV Stick
> abgenommen (03.10.2026 abends). Technische Notizen: `docs/tv-modus.md` im Branch. Der
> Changelog-Eintrag 16.0.0 ist erzählend neu geschrieben und nennt TV-Modus, Rundflug, Kniebrett
> 3.0.0 und die neue Brügge.
> **Zweigstand:** `bruegge-radar` ist der vollständige Stand (wird per
> `git push -f origin bruegge-radar:test` auf die Teststufe geschoben); er enthält `umzug`,
> `lichtblick` und `kniebrett-3`.
> **Reihenfolge am Tag X:** (1) Nutzer nach der Adresse fragen, (2) Umzug, (2a) neue
> Forum-Brücke ablegen (s. u.), (3) 16.0.0 ausliefern, (4) am Simulator beide Kniebrett-Pakete
> nebeneinander prüfen, (5) Pakete hochladen — jeder Schritt auf Wort des Nutzers.
>
> **Neu am 04.10.2026 — Forum-Brücke v3 (Abmelden).** 16.0.0 bringt „Abmelden“ im
> Zahnradmenü; es beendet auch die Forum-Sitzung. Dafür muss die neue `deploy/forum/sso.php`
> (Branch `bruegge-radar`, ab `d8de116`) nach `/var/www/bb_friesen/sso.php` auf dem
> FriesenFlieger-Server. Die Brücke legt **Tobias selbst** ab bzw. die Server-Sitzung nur auf
> sein ausdrückliches Wort (Schreibzugriff dort). Echtes Secret und die drei Rücksprung-Adressen
> aus der liegenden Datei übernehmen, Rechte `640 www-data:www-bb_friesen`, danach `php -l`.
> Die neue Brücke ist abwärtsverträglich (Anmeldung unverändert) und kann vor 16.0.0 liegen.
> **Ohne sie fehlt der Abmelden-Knopf** — die Seite zeigt ihn erst, wenn die Brücke `abm: true`
> ins Anmelde-Token schreibt; der Changelog-Eintrag 👤 verspricht ihn. Prüfen nach dem Ablegen:
> neu anmelden, Zahnrad → Abmelden → Ja; danach muss die Anmeldeseite des Forums erscheinen
> und das Forum in diesem Browser abgemeldet sein. Die PHP-Prüffunktion ist lokal gegen
> Aufträge aus `make_logout_token` gegengeprüft, der Lauf **im** phpBB (`session_kill`) noch nicht.
> **Erledigt 04.10.2026, 14:41 MESZ (auf Wort des Nutzers):** Die v3-Brücke liegt auf dem
> Forum (`www-data:www-bb_friesen 660`, Secret aus der liegenden Datei übernommen, `php -l`
> sauber). Die liegende Datei war die alte Vorlage mit Windows-Zeilenenden, sonst zeichengleich.
> Sicherung: `~twaeschle/sso.php.sicherung-2026-10-04` (600). Von außen gemessen, vorher und
> nachher gleich: ohne Sitzung die Anmeldeseite, fremder Rücksprung 400; neu: kaputter
> Abmelde-Auftrag 400. **PHP hält die alte Fassung einige Sekunden im Zwischenspeicher** — die
> erste Probe direkt nach dem Ablegen zeigte noch das alte Verhalten. Schritt 2a entfällt damit.
> Noch offen: eine Anmeldung über die neue Brücke im Log sehen, und das Abmelden im phpBB
> (geht erst mit 16.0.0 oder mit einem von Hand erzeugten Auftrag).
> Ebenfalls am 04.10. dazugekommen (alles auf dem Test-Zweig): Hilfe und Version in der
> Fußleiste, Name ins Zahnradmenü, Zahnrad auf dem Handy neben dem Logo, leerer Prefile-Kasten
> niedrig.

**Nur, wenn der Nutzer das Fenster freigibt.** Ausfall ~1 min. Die CI liegt **nicht** auf dem
kritischen Pfad: Das neue Image wird gebaut, während der alte Container noch läuft. (B2)

**Vorbedingungen (Tage vorher, ohne Ausfall):**
- [ ] **Step 1:** `server-backup`: Änderung auf einem Branch vorbereiten (`FS_DIR=/opt/backup/friesenradar`, Archiv `friesenradar-${DATE}.tar.gz`, Quelle `/opt/friesenradar/data/friesenradar.db`, Ziel `onedrive:/Server-Backup/friesenradar/`), dazu eine Prüfung `[ -s "$DB" ]` vor dem `.backup`, damit nie eine leere Datei gesichert wird. `rclone`-Pfade als Literal. (B4)
- [ ] **Step 2:** `vaultwarden-setup`: Watchtower-Liste auf `friesenradar-friesenradar-1` auf einem Branch vorbereiten. Einspielen vor dem nächsten Sonntag 04:00.
- [ ] **Step 3:** `fail2ban` im Repo `devprops.de`: Jail und Filter `friesenradar` vorbereiten (Filter kennt alle drei Hosts schon, `efa4b5e`).
- [x] **Step 4:** **Freigegeben vom Nutzer am 03.10.2026 („ja“)**, gilt für den Umzug. Ursprünglich: `config.env`-Änderung dem Nutzer zeigen und **Freigabe holen**: `DB_PATH=/opt/friesenradar/data/friesenradar.db`, `FORUM_SSO_CALLBACK=https://friesenradar.devprops.de/auth/forum/callback`. Ohne Freigabe kein Umzug.
- [ ] **Step 4b:** Der Sitzung auf dem Simulator-Rechner Bescheid geben: `paket.ps1` lädt ab dem Umzug nach `/opt/friesenradar/...`; ein Upload mit altem Stand scheitert laut. (K6)
- [ ] **Step 5:** `COORDINATION.md`-Eintrag mit Termin; Vorbedingung für Task 7: **keine andere Sitzung arbeitet in `~/projects/friesenspy*`**.

**Am Abend, vor dem Ausfall (alter Container läuft weiter):**
- [ ] **Step 6:** Flugbetrieb prüfen (nginx-Log der letzten 10 min, `CoherentGT`, `/api/sse`).
- [ ] **Step 7:** `gh repo rename friesenradar -R regover13/friesenspy --yes`, Remote auf `regover13/friesenradar`. Discord vorwarnen: Der folgende Deploy meldet rot.
- [ ] **Step 8:** `umzug` nach `main` (Rebase, Suite grün, Push). Der Workflow testet und baut `ghcr.io/regover13/friesenradar:latest`; sein Deploy-Schritt scheitert an `cd /opt/friesenradar` (gibt es noch nicht), der alte Container bleibt unberührt. Gegenprobe: `gh api user/packages/container/friesenradar` zeigt das Paket, `visibility: private`. **Ist der Bau rot, hier aufhören** — nichts ist bis dahin verändert außer dem Repo-Namen.

**Ausfall (~1 min):** Steps 9–15 führt `deploy/umzug-friesenradar.sh` (Branch `umzug`) in einem
Zug aus. Seit dem Abschluss-Review laufen alle Prüfungen (Token, `config.env`-Schlüssel) und
der **Image-Download vor dem Stoppen**; bricht es danach ab, nennt die Ausgabe den Rückweg für
genau diesen Stand. Der Rückweg ist ein eigener Modus (`ZURUECK=1`: alle drei DB-Dateien
zurückbenennen, `.alt`-Dateien zurück, Leer-Prüfung vor dem Start, Zählung). Exakt gleich
bleiben muss nur `progress_snapshot`; alle anderen Tabellen dürfen wachsen. **Zweite
Generalprobe** am selben Tag mit dieser Fassung: Hin- und Rückweg bestanden (Reste unter
`/root/umzug-probe2-2026-10-03/`). **Generalprobe am
03.10.2026 bestanden:** dasselbe Skript gegen eine Kopie im alten Aufbau (`PROBE=1`, Container
ohne Netzwerk, echte App unberührt) — Health nach 10 s, DB im Container 128 MB unter dem neuen
Pfad, alle Zählungen gleich (19 Snapshots unverändert), Website/Admin/Kniebrett/Widget/Download/
Kartenblatt/Badge mit 200, ohne Login 401. Backup-Teil (Branch `friesenradar` im Repo
`server-backup`) gegen die Probe-DB: Archiv vollständig; fehlende Datei → Abbruch ohne leere
Sicherung. Reste unter `/root/umzug-probe-2026-10-03/` (0700), Probe-Image
`ghcr.io/regover13/friesenradar:probe` — beides nach dem Umzug löschen (Step 23).
- [ ] **Step 9:** `PRAGMA integrity_check` auf der laufenden DB, Ergebnis `ok`. Zeilenzahlen und `MAX(id)` notieren: `flights`, `position_history`, `panel_prefs`, `panel_devices`, `push_subscriptions`, `progress_snapshot` (dazu `COUNT(*)` und `MAX(computed_at)`, die 19 Snapshots dürfen sich nie ändern).
- [ ] **Step 10:** `cd /opt/friesenspy && docker compose down`. Gegenprobe: `docker ps | grep friesenspy` leer.
- [ ] **Step 11:** Checkpoint und Sicherung als `containersvc` mit absoluten Pfaden: `PRAGMA wal_checkpoint(TRUNCATE)`, `.backup /root/umzug-friesenradar-<datum>/friesenspy.db` (nicht unter `/opt/backup`, sonst hält `backup_status.sh` die Handkopie für die jüngste Sicherung). Alte Compose nach `/root/umzug-friesenradar-<datum>/`, ebenso `config.env`.
- [ ] **Step 12:** `sudo mv /opt/friesenspy /opt/friesenradar`, `mv data/friesenspy.db data/friesenradar.db`. `ls -la data/friesenradar.db*` → genau eine Datei, Besitzer `containersvc`.
- [ ] **Step 13:** **Neue `docker-compose.yml` aus dem Repo nach `/opt/friesenradar/` kopieren** — der Deploy kopiert keine Compose-Datei, sonst startet die alte mit altem Image und altem Mount (B1). `config.env` wie in Step 4 freigegeben. Gegenprobe: `docker compose config | grep -E 'image|/opt/'` zeigt nur `friesenradar`, und die DB-Datei aus `DB_PATH` liegt im gemounteten Verzeichnis.
- [ ] **Step 14:** (im Skript: Login und `docker pull` laufen schon VOR Step 10) `docker compose up -d`. Container heißt `friesenradar-friesenradar-1`. **Rückfall, falls der Pull scheitert:** `docker tag ghcr.io/regover13/friesenspy:latest ghcr.io/regover13/friesenradar:latest` und `up -d` (das alte Image läuft mit den neuen Pfaden, weil `config.env` gewinnt).
- [ ] **Step 15: Gegenproben sofort** — scheitert eine, Rückweg (Step 16):
  - `curl -sf http://127.0.0.1:8091/health`
  - Zeilenzahlen aus Step 9: jede `>=` dem notierten Wert, `progress_snapshot` exakt gleich
  - alle drei Adressen antworten wie vorher; Forum-Login über `/auth/forum/login` springt je Host richtig zurück
  - nach 5 min: `bruegge_zuordnung.gesehen_am` und `panel_devices.last_seen_at` nach dem Umzug, falls jemand fliegt (Review Focus 2)
- [ ] **Step 16 (nur im Fehlerfall): Rückweg** — `down`, `mv` zurück, DB-Name zurück, alte Compose und `config.env` aus `/root/umzug-…`, `up -d` in `/opt/friesenspy`. Das alte Image liegt lokal, bis Step 23.

**Nachziehen (ohne Ausfall, am selben Abend):**
- [ ] **Step 17: nginx:** `nginx/friesenradar.devprops.de.conf` installieren, alten Symlink **vor** `nginx -t` entfernen (sonst doppelte `limit_req_zone`-Namen), alte Datei und die drei `.bak` nach `/root/umzug-…`, `reload`. Bis Step 22 zeigt der neue Vhost noch auf das bestehende Zertifikat (`live/friesenspy.devprops.de`, deckt beide Namen).
- [ ] **Step 18: fail2ban** aus Step 3 einspielen (Repo `devprops.de`, Branch `friesenradar`) und **die alten `/etc/fail2ban/jail.d/friesenspy.conf` und `filter.d/friesenspy.conf` entfernen** — sonst laufen zwei gleiche Jails auf `goaccess.log`; `fail2ban-regex` mit drei Probezeilen, `fail2ban-client status friesenradar`.
- [ ] **Step 19: Backup** aus Step 1 einspielen — **vor 03:00** — ausdrücklich per `cp backup_onedrive.sh /opt/backup/scripts/` mit `diff`-Gegenprobe (die README beschreibt nur die Erstinstallation, K9). Alte Archive `/opt/backup/friesenspy/*.tar.gz` nach `/opt/backup/manual/friesenspy-alt/` (die Rotation sieht Unterordner nicht und würde sie sonst nie löschen). Probelauf dieses Teils, Archiv im OneDrive prüfen. Am Morgen `systemctl --failed`.
- [ ] **Step 20: Watchtower** aus Step 2 einspielen, `docker compose up -d --no-deps watchtower`; Gegenprobe `docker inspect watchtower`.
- [ ] **Step 21:** `containersvc`-Kommentar in `/etc/passwd`; Serverdoku (Repo `devprops.de`) mit Pfaden, Containernamen und Tabellen.

**Eine Woche später:**
- [ ] **Step 22: Zertifikat:** `sudo certbot certonly -n --webroot -w /var/www/html --cert-name friesenradar.devprops.de -d friesenradar.devprops.de -d friesenspy.devprops.de --deploy-hook "systemctl reload nginx"`, Vhost auf `live/friesenradar.devprops.de` umstellen (im Repo steht bis dahin bewusst noch `live/friesenspy.devprops.de`, sonst scheitert Step 17 an `nginx -t`), `nginx -t`, `reload`, mit `curl -v` prüfen. Erst wenn `nginx -T | grep live/friesenspy` leer ist (K3): `certbot delete --cert-name friesenspy.devprops.de` — **nicht umkehrbar** außer durch Neuausstellung (Rate-Limit). (B5)
- [ ] **Step 23:** Altes Image `docker rmi ghcr.io/regover13/friesenspy:latest` und das Probe-Image `ghcr.io/regover13/friesenradar:probe`, Gegenprobe `docker images`. Probe-Reste `/root/umzug-probe-2026-10-03/` und `/root/umzug-probe2-2026-10-03/` (zusammen ~1,8 GB, enthalten DB-Kopien) löschen — mit Freigabe.

**Später, wenn Heinz den DNS-Eintrag gesetzt hat** (CNAME `radar` → **`friesenradar.devprops.de`**):
- [ ] **Step 24:** `dig +short radar.friesenflieger.de` zeigt auf 167.86.127.129. Zertifikat erweitern (`--expand -d radar.friesenflieger.de`), `server_name` ergänzen, `curl -sf https://radar.friesenflieger.de/health`, Forum-Login über diese Adresse. Erst danach Texte für Mitglieder auf diese Adresse umstellen (Task 3 Nachtrag). (V4)

---

### Task 3: Release 16.0.0 „Lichtblick“ (sichtbar) — gebaut auf Branch `lichtblick`

Stand `f395b0d` auf `origin/lichtblick` (Basis `umzug`): Vorschau-Schalter entfernt, Logo fest,
Name in allen Seiten, Server-Texten, Widget, Anmeldeseite, Test-Push, User-Agents, Manifest,
Symbolen, `favicon.ico`, README, CLAUDE.md (Abschnitt „Name“), COORDINATION.md, undatierter Doku;
`radar_vorschau` aus `/api/me` entfernt; `generate_icons.py` gelöscht (hätte die neuen Symbole still
mit den alten überschrieben); Changelog 16.0.0 „Lichtblick“ (`highlight: false`). Die Download-
Adresse nennt das Kniebrett als Text: `friesenradar.devprops.de/download`. Widget-Einbettung:
`https://friesenradar.devprops.de/widget` (technische Heimat, liest kein Mitglied). Wächtertest
`tests/test_name_friesenradar.py` prüft Seiten, README (inkl. Überschriften) und Server-Code.
Suite grün (3901).

- [x] **Step 1:** `efb.html` und README nennen keinen Ordnernamen mehr; der Download-Name folgt dem Paketinhalt (Variante B).
- [x] **Step 2:** **Erledigt 03.10.2026, 07:55:** Nutzer im Simulator „sieht soweit alles gut aus“; im Log beide Logo-Dateien mit `CoherentGT` abgerufen (200). Ursprünglicher Auftrag: **Sim-Prüfung des Logos im Kniebrett, vor dem Ausliefern:** Bisher ist das Radar-Kniebrett nie in Coherent GT gelaufen (0 Abrufe der Logo-Dateien mit `CoherentGT` im Log). Prüfung über die Vorschau, die heute auf `main` für die CID des Nutzers aktiv ist: hell und dunkel, mit Statusleiste und geöffneten Fenstern. (V9)
- [ ] **Step 3:** Teilen- und Badge-Codes bauen ihre Adresse aus `location.origin`; wer über das Alias kommt, verbreitet die alte Adresse weiter. Abbilden: aus `friesenspy.devprops.de` wird beim Kopieren `friesenradar.devprops.de`, mit Test. (V7)
- [ ] **Step 4:** Vor dem Ausliefern: Rebase auf `main` (nach Task 2), Datum im Changelog auf den Releasetag, Suite grün, Flugbetrieb prüfen. Nach dem Ausliefern im Admin **16.0.0 als Banner wählen** — sonst zeigt der Neuigkeiten-Kasten weiter den Text von Luftschloss, und darin steht der alte Name.

---

### Task 4: Forum und Ankündigung (am Tag von 16.0.0)

Alles auf friesenflieger.de nur mit Freigabe; Schreiben einzeln erfragen.

- [ ] **Step 1:** Unterforum „FriesenSpy“ (f=116) in „FriesenRadar“ umbenennen — Nutzer im ACP (hat selbst Zugriff).
- [ ] **Step 2:** Thema 1785 in „FriesenRadar – Entwicklungsstand“ umbenennen — **Nutzer im ACP bzw. über die Moderation**, nicht durch Bearbeiten des ersten Beitrags: Trägt er eine Umfrage, löscht jedes Bearbeiten sie samt Ergebnissen. (V10)
- [ ] **Step 3:** Widget-Einbettung in Board-Vorlage und Website auf `https://friesenradar.devprops.de/widget` — **der Nutzer hat selbst Zugriff auf beides** (03.10.2026); nur DNS liegt bei Heinz. Ändert der Nutzer, oder ich mit ausdrücklicher Schreibfreigabe.
- [ ] **Step 4:** Discord-Webhook-Name und Telegram-Bot-Anzeigename umbenennen (Nutzer).
- [ ] **Step 5:** Ankündigung „V16 - Lichtblick“: Entwurf im Chat, nach Freigabe posten, Betreff nachziehen. Inhalt: neuer Name, neue Adresse, Logo und Symbol; **iPhone/iPad:** alte App vom Home-Bildschirm löschen, über die neue Adresse neu hinzufügen, Benachrichtigungen neu einschalten; **Android:** nichts tun, Name und Symbol ziehen von selbst nach; einmal neu anmelden; Kniebrett-Paket und Brügge folgen. (V5/V6)
- [ ] **Step 6:** Gegenprobe `forum_list_forums`; nach einigen Tagen `SELECT owner_cid, COUNT(*) FROM push_subscriptions GROUP BY 1 HAVING COUNT(*) > 1`.

---

### Task 5: Kniebrett-Paket 3.0.0 — Variante B (Nutzer 03.10.2026, nach erst A)

**Neuer Ordner:** Paketordner `friesenflieger-friesenradar-efb`, Quellordner
`msfs-panel/PackageSources/FriesenRadar/`, Klasse `FriesenRadar`, `efb_apps/FriesenRadar` —
alle drei gleich, weil das CSS-Präfix aus dem Ordnernamen kommt und die EFB Apps über den
Klassennamen führt. URL `https://friesenradar.devprops.de/panel`, `manifest.title`
„FriesenRadar“, Symbol aus `app/static/logo/friesenradar-symbol.svg`, `PAKET_VERSION` 3.0.0.
**`DEVICE_KEY` bleibt `"friesenspy_device"`.**

Bekannte Folgen (V2), die diese Fassung auffangen muss:
- Liegt der alte Ordner noch im Community-Ordner, zeigt das Tablet **zwei Apps**.
- Die **Anheftung** der App im Tablet geht einmal verloren (neuer Klassenname).
- Ob die **Gerätebindung** hält, ist nicht belegt (`SetStoredData` paketübergreifend?).

Schon erledigt (Branch `lichtblick`): Der Download-Name folgt dem Ordner in der ZIP
(`_efb_download_name`), wechselt also erst, wenn 3.0.0 abgelegt ist; `efb.html` und README nennen
keinen Ordnernamen mehr.

- [ ] **Step 1: Erkennung des alten Pakets** in 3.0.0: `Efb.apps().getArray()` auf `internalName === "FriesenSpy"` prüfen und im `pong` als `altesPaket: true` melden. Die Seite zeigt dann einen **nicht wegklickbaren** Hinweis: „Bitte den alten Ordner `friesenflieger-friesenspy-efb` aus dem Community-Ordner löschen und den Simulator neu starten.“ Der Ordnername ist dort die einzige erlaubte Nennung (Ausnahme im Wächtertest, an genau diese Stelle gebunden). Test zuerst.
- [ ] **Step 2:** Auch die **alte** App soll es erfahren: Meldet 2.x sich, obwohl `panel_devices` für dieselbe Kennung schon 3.0.0 gesehen hat, zeigt der vorhandene Paket-Hinweis den Lösch-Satz. Test zuerst.
- [ ] **Step 3:** Die Sperre `_paketSperrePruefen` bleibt unverändert (nur Pakete ohne Version); 2.3.2 wird nicht gesperrt, nur per Hinweis gebeten — mit Test.
- [ ] **Step 4:** `efb.html` ab 3.0.0: Satz zum Löschen des alten Ordners bei einem Update von 2.x.
- [ ] **Step 5: Sim-Prüfung, harte Schranke vor der Ablage** (Übergabe an die Sitzung auf dem Simulator-Rechner, `docs/uebergabe-msfs-build.md` nachziehen):
  - **nur neues Paket** (alter Ordner gelöscht): `/auth/device` im nginx-Log mit **derselben** `device=`-Kennung wie vorher und `paket=3.0.0`. Kommt eine neue Kennung, ist die Bindung paketgebunden — dann nicht ablegen, sondern neu entscheiden.
  - **beide installiert:** der Hinweis aus Step 1 erscheint in der neuen App, der aus Step 2 in der alten.
- [ ] **Step 6:** Ablage als `/opt/friesenradar/data/efb/friesenradar-efb.zip`; Download heißt danach `friesenflieger-friesenradar-efb.zip` (Gegenprobe mit `curl -sI`). Alte `friesenspy-efb.zip` nach Bewährung löschen. Die Release-Notizen älterer Fassungen im Paket bleiben als Geschichte.

---

### Task 6: FriesenBrügge

**Files:** `friesenbruegge/msfs/bruegge.cpp` (`BRUEGGE_URL`), `friesenbruegge/xplane/netz.h`, `bruegge.cpp` (Texte), `LIESMICH.txt`.

- [ ] **Step 1:** URL auf `https://friesenradar.devprops.de/api/bruegge/melden`, Texte, **neue Versionsnummer** — an ihr erkennt der Server später, wer noch die alte Adresse nutzt.
- [ ] **Step 2:** **Möglichst vor dem 24.10.2026** ausliefern (`_BRUEGGE_P2_MSFS_BIS`): Dann aktualisieren die MSFS-Piloten einmal statt zweimal.
- [ ] **Step 3:** Erfolg in der DB prüfen (`bruegge_zuordnung.bruegge_version`, `gesehen_am`), nicht im nginx-Log.

---

### Task 7: Claude-Arbeitsumgebung (direkt nach Task 2)

- [ ] **Step 1:** Vorbedingung: keine andere Sitzung in `~/projects/friesenspy*` (offene Shells verlieren ihr Verzeichnis). Worktrees `friesenspy-umzug` und `friesenspy-lichtblick` erst nach dem Merge entfernen; `friesenspy-posix` (`karten-legende-politur`) vorher auf ungemergte Commits prüfen (`git log main..karten-legende-politur`). Danach `mv ~/projects/friesenspy ~/projects/friesenradar`, `git worktree repair` für verbleibende.
- [ ] **Step 2:** venv `~/.venv-friesenradar` neu, altes löschen, Gedächtnisnotiz nachziehen.
- [ ] **Step 3:** `~/projects/.claude/settings.local.json`: nur Pfade.
- [ ] **Step 4:** Gedächtnis: Pfade, Repo, Adressen. Die Sitzungsablagen unter `~/.claude/projects/-home-claude-projects-friesenspy*` hängen am alten Pfad; `claude --resume` aus dem neuen Ordner findet sie nicht — hinnehmbar, die Server-Sitzungen laufen in `~/projects`.

---

### Task 8: Aufräumen (später)

- [ ] **Step 1:** Altes GHCR-Paket `friesenspy` löschen (Token hat `delete:packages`). Nicht umkehrbar — nach Bewährung.
- [ ] **Step 2:** `/opt/backup/manual/friesenspy-alt/` nach 7 Tagen, OneDrive `Server-Backup/friesenspy/` nach 30 Tagen von Hand löschen (`rclone purge`, Freigabe). Die Rotation erledigt das **nicht**.
- [ ] **Step 3:** Nach einigen Wochen in der DB auswerten: Welche Brügge- und Paketversionen melden noch? Das Alias bleibt mindestens wegen der Badges in alten Beiträgen und der Push-Abos an der alten Adresse.
- [ ] **Step 4:** Issues #51–#56 schließen.
