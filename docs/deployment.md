# Deployment

## Automatisch (via GitHub Actions)

Jeder Push auf `main` triggert den CI/CD-Pipeline:

1. `docker build` → Image `ghcr.io/regover13/friesenspy:latest`
2. Push nach GHCR (GitHub Container Registry)
3. SSH auf VPS: Der Workflow ruft dort `deploy` auf — mehr kann er nicht (siehe unten)

### Der Deploy-Schlüssel kann genau zwei Dinge (seit 04.10.2026)

Der Workflow meldet sich mit dem Schlüssel `friesenspy-deploy` an (Secret `DEPLOY_SSH_KEY`).
In `/root/.ssh/authorized_keys` steht er mit `restrict,command="/opt/friesenspy/deploy.sh"`:
keine Shell, kein Forwarding, und egal welches Kommando der Aufrufer mitgibt — der Server führt
nur dieses eine Skript aus. Es kennt zwei Aufträge:

| Auftrag | Workflow | Was geschieht |
|---|---|---|
| `deploy` | `deploy.yml` (Push auf `main`) | `:latest` holen, Container ersetzen, Health-Check, alte Images wegräumen |
| `test` | `test-image.yml` (Push auf `test`) | `:test` holen und als `test-radar:aktuell` bereitlegen, nichts starten |

Der `GITHUB_TOKEN` des Laufs kommt über stdin und dient nur dem Pull; das Skript meldet sich am
Ende wieder von GHCR ab. Den Host-Schlüssel des Servers trägt der Workflow fest bei sich
(`StrictHostKeyChecking=yes`).

**Das Skript liegt im Repo unter `deploy/deploy.sh`, wird aber NICHT automatisch ausgerollt** —
ein Push, der es ändert, ändert auf dem Server nichts. Wer es anfasst, kopiert es von Hand:

```bash
sudo install -m 755 -o root -g root deploy/deploy.sh /opt/friesenspy/deploy.sh
```

Das ist Absicht: Könnte ein Push das Skript ersetzen, wäre die Einschränkung des Schlüssels
wertlos. Vorher lief der Deploy über die fremde Action `appleboy/ssh-action` mit einem
unbeschränkten root-Schlüssel — wer pushen oder das Secret lesen konnte, hatte eine Root-Shell.

Fremde Actions sind in allen Workflows auf einen Commit festgenagelt (`uses: …@<sha> # vX.Y.Z`),
und jeder Workflow trägt `permissions: contents: read`; nur der Bau-Job bekommt zusätzlich
`packages: write`.

Der Container läuft als non-root User `friesenspy` (UID 1001).

## Was ein Deploy kostet — und warum das HTTP 502 erzeugt

Ein Deploy ersetzt den Container. In dem Fenster dazwischen antwortet niemand, und nginx
meldet dem Aufrufer **HTTP 502**. Das ist kein Fehler, sondern der Neustart selbst — wer
502er auswertet, muss sie abziehen.

Gemessen am 15.09.2026 über zwei Tage: **Alle 839 Upstream-Fehler lagen im Fenster eines
Deploys, kein einziger daneben** (41 Deploys, davon 25 mit laufenden Clients). Die Größe
des Fensters ist jedes Mal dieselbe:

| Abschnitt | vor dem 15.09.2026 | seither |
|---|---|---|
| alter Container beendet sich | ~10 s, endete mit **SIGKILL** | **4,7 s**, Exit 0 |
| neuer Container startet die App | ~7 s | ~7 s |
| **Summe** | **16–20 s** | **~12 s** |

Die 4,7 s sind gemessen, nicht gerechnet: Mit dem echten Image und einer offenen
SSE-Verbindung braucht der Stopp **30,9 s und endet mit Exit 137**, wenn man das Argument
aus dem `CMD` nimmt, und **4,7 s mit Exit 0**, wenn es drinsteht (Gnadenfrist im Test auf
30 s gesetzt, damit der Unterschied sichtbar wird; in Produktion sind es 10 s). Der Rest von
4,7 s ist **nicht** das Zeitlimit, sondern der Lifespan-Shutdown — ohne jede SSE-Verbindung
dauert der Stopp genauso lange. Das Zeitlimit kostet also nichts, es verhindert nur das
Hängenbleiben.

Die 10 Sekunden waren Dockers Gnadenfrist: uvicorn wartet beim Beenden auf das Ende aller
laufenden Antworten, und `/api/sse` liefert einen Stream, der nie endet. Eine einzige offene
SSE-Verbindung hielt den Container deshalb fest, bis `SIGKILL` kam — die App wurde also bei
**jedem** Deploy mitten im Schreiben nach SQLite abgeschossen. Behoben mit
`--timeout-graceful-shutdown 3` im `CMD` des Dockerfiles; die Begründung steht dort
ausführlich, bewacht wird es von `tests/test_deploy_shutdown.py`.

⚠ **`stop_grace_period` in `docker-compose.yml` zu erhöhen wäre der falsche Griff** — das
verlängert nur das Warten, statt es zu beenden.

**Die verbleibenden ~7 Sekunden sind der App-Start** (FSE-Bestand mit 23.780 Plätzen,
6.121 Meldepunkte, Platzrunden). Sie sind noch offen; ein Deploy ohne Ausfall bräuchte einen
zweiten Container, und dem steht die gemeinsame SQLite-Datei im Weg.

**Wer im Sekundentakt meldet, merkt das als Erster.** Für die FriesenBrügge ist jede dieser
Sekunden eine verlorene Meldung — ihr Punkt auf der Karte friert so lange ein. Deshalb gilt:
**nicht in den laufenden Betrieb deployen**, wenn jemand fliegt.

## Manuell auf dem VPS

```bash
ssh root@167.86.127.129
cd /opt/friesenspy
docker compose pull
docker compose up -d
```

## Logs einsehen

```bash
docker logs friesenspy-friesenspy-1 -f
```

## Container neu starten (config.env-Änderungen)

```bash
cd /opt/friesenspy
docker compose up -d --force-recreate
```

**Wichtig:** `docker restart` liest `env_file` nicht neu ein. Immer `docker compose up -d` benutzen wenn `config.env` geändert wurde.

## config.env

Die Datei liegt auf dem VPS unter `/opt/friesenspy/config.env` und wird **niemals** in Git eingecheckt.

```bash
SECRET_KEY=<random-hex-32>
CALLSIGN_PREFIX=FRS
VATSIM_POLL_INTERVAL=15
DB_PATH=/opt/friesenspy/data/friesenspy.db
TELEGRAM_BOT_TOKEN=        # leer = kein Alert
TELEGRAM_CHAT_ID=          # leer = kein Alert
```

`SECRET_KEY` generieren:
```bash
openssl rand -hex 32
```

## Datenbank

SQLite-Datei liegt im gemounteten Volume: `/opt/friesenspy/data/friesenspy.db`

Backup:
```bash
sqlite3 /opt/friesenspy/data/friesenspy.db ".backup /tmp/friesenspy_backup.db"
```

## nginx

Konfiguration in `nginx/friesenspy.devprops.de.conf`:

- `/api/sse`: Kein Rate-Limit, `proxy_read_timeout 3600s`, `X-Accel-Buffering: no`
- Alle anderen Endpoints: Rate-Limit 30req/min, `proxy_pass http://127.0.0.1:8091`

## Telegram-Alerts einrichten (optional)

1. Bot erstellen via [@BotFather](https://t.me/BotFather) → Token kopieren
2. Bot in gewünschte Gruppe einladen
3. Chat-ID ermitteln: `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. In `config.env` eintragen und Container neu erstellen

## GitHub Secrets

| Secret | Beschreibung |
|--------|--------------|
| `DEPLOY_SSH_KEY` | Privater Teil des Deploy-Schlüssels `friesenspy-deploy` — auf dem Server auf `/opt/friesenspy/deploy.sh` eingeschränkt |
| `DISCORD_WEBHOOK` | Kanal-Webhook für die Deploy-Meldung (optional) |

Ein GHCR-Token braucht es nicht: Bau und Pull laufen mit dem `GITHUB_TOKEN` des Laufs.

Neuen Deploy-Schlüssel ausstellen (auf dem Server): `ssh-keygen -t ed25519 -N '' -C friesenspy-deploy`,
den privaten Teil per `gh secret set DEPLOY_SSH_KEY -R regover13/friesenspy < datei` hinterlegen und
danach leeren, den öffentlichen mit `restrict,command="/opt/friesenspy/deploy.sh"` davor in
`/root/.ssh/authorized_keys` eintragen (alte Zeile entfernen).

## Rollback

```bash
# Vorheriges Image taggen und deployen
docker pull ghcr.io/regover13/friesenspy:<sha>
docker tag ghcr.io/regover13/friesenspy:<sha> ghcr.io/regover13/friesenspy:latest
cd /opt/friesenspy && docker compose up -d
```
