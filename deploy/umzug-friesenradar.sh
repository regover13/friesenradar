#!/usr/bin/env bash
# Umzug FriesenSpy -> FriesenRadar auf dem Server (Plan 2026-10-02, Task 2, Steps 9-15).
#
# Dasselbe Skript fuer die Generalprobe, den echten Abend und den Rueckweg -- erprobt wird
# also der Befehl selbst, nicht nur sein Ergebnis.
#
#   Probe:    PROBE=1 ALT=/opt/friesenspy-probe NEU=/opt/friesenradar \
#             REPO=~/projects/friesenspy-umzug SICHERUNG=/root/umzug-probe-<datum> \
#             sudo -E bash deploy/umzug-friesenradar.sh
#   Echt:     ALT=/opt/friesenspy NEU=/opt/friesenradar REPO=... SICHERUNG=/root/umzug-friesenradar-<datum> \
#             GH_TOKEN=... sudo -E bash deploy/umzug-friesenradar.sh
#   Zurueck:  ZURUECK=1 ALT=... NEU=... SICHERUNG=<dieselbe wie beim Hinweg> sudo -E bash deploy/umzug-friesenradar.sh
#
# Probe-Modus: Der Container startet OHNE Netzwerk (network_mode: none) -- er kann niemandem
# eine Push-Nachricht schicken und keinen Dienst anfragen. Die echte App bleibt unberuehrt.
#
# Reihenfolge mit Absicht (Abschluss-Review 03.10.2026): ALLES, was scheitern kann, ohne dass
# etwas veraendert ist -- Token, config.env, Image-Download --, laeuft VOR dem Stoppen. Bricht
# es danach doch ab, nennt die Ausgabe den Rueckweg fuer genau diesen Stand.
set -euo pipefail

ALT=${ALT:?ALT fehlt}; NEU=${NEU:?NEU fehlt}
SICHERUNG=${SICHERUNG:?SICHERUNG fehlt}; PROBE=${PROBE:-0}; ZURUECK=${ZURUECK:-0}
LIVE=/opt/friesenspy
DB_ALT_NAME=friesenspy.db
DB_NEU_NAME=friesenradar.db
DB_NEU_IM_CONTAINER=/opt/friesenradar/data/$DB_NEU_NAME
IMAGE=ghcr.io/regover13/friesenradar:latest
# Exakt gleich bleiben muss nur, was nach seiner Berechnung eingefroren ist. Alles andere
# darf waehrend der Pruefung wachsen -- der Poller traegt neu online gegangene Piloten ein,
# Nutzer melden Tablets an und aendern Einstellungen (Review W3).
TABELLEN_GLEICH="progress_snapshot"
TABELLEN_WACHSEN="pilots panel_devices panel_prefs push_subscriptions flights position_history bruegge_zuordnung"

STAND=nichts   # fuer den Rueckweg-Hinweis bei einem Abbruch
schritt() { echo; echo "== $*"; }
abbruch() { echo "ABBRUCH: $*" >&2; exit 1; }
als_dienst() { sudo -u containersvc "$@"; }
mv_db() {      # $1 Verzeichnis, $2 von, $3 nach -- immer alle drei Dateien der WAL-Datenbank
  local endung
  for endung in "" -wal -shm; do
    [ ! -e "$1/$2$endung" ] || mv "$1/$2$endung" "$1/$3$endung"
  done
}
zaehlen() {   # $1 = DB-Datei; liest nur
  local db=$1 t
  for t in $TABELLEN_GLEICH $TABELLEN_WACHSEN; do
    printf '%s %s\n' "$t" "$(als_dienst sqlite3 -readonly "$db" "SELECT COUNT(*) FROM $t")"
  done
  printf 'snapshot_stand %s\n' "$(als_dienst sqlite3 -readonly "$db" \
    "SELECT COUNT(*) || '/' || COALESCE(MAX(computed_at),'') FROM progress_snapshot")"
}
vergleichen() {   # $1 vorher, $2 nachher
  local t vorher nachher
  while read -r t vorher; do
    nachher=$(awk -v t="$t" '$1==t{print $2}' "$2")
    case " $TABELLEN_WACHSEN " in
      *" $t "*) [ "$nachher" -ge "$vorher" ] || abbruch "$t: $vorher -> $nachher" ;;
      *)        [ "$nachher" = "$vorher" ] || abbruch "$t: $vorher -> $nachher" ;;
    esac
  done < "$1"
  echo "Zaehlung stimmt."
}
rueckweg_zeigen() {
  [ "$?" = 0 ] && return
  echo >&2
  case "$STAND" in
    nichts)    echo "Es ist nichts veraendert. Die alte App laeuft weiter." >&2 ;;
    gestoppt)  echo "RUECKWEG: Nur gestoppt, nichts verschoben:  docker compose --project-directory $ALT up -d" >&2 ;;
    *)         echo "RUECKWEG: ZURUECK=1 ALT=$ALT NEU=$NEU SICHERUNG=$SICHERUNG sudo -E bash $0" >&2 ;;
  esac
}
trap rueckweg_zeigen EXIT

[ "$(id -u)" = 0 ] || abbruch "als root ausfuehren"

# ------------------------------------------------------------------------------------------
# Rueckweg
# ------------------------------------------------------------------------------------------
if [ "$ZURUECK" = 1 ]; then
  STAND=rueckweg
  [ -d "$NEU" ] || abbruch "$NEU gibt es nicht -- nichts zurueckzuholen"
  [ ! -e "$ALT" ] || abbruch "$ALT existiert schon"
  [ -f "$SICHERUNG/docker-compose.yml.alt" ] && [ -f "$SICHERUNG/config.env.alt" ] \
    || abbruch "Sicherung unvollstaendig: $SICHERUNG"
  schritt "Neue App stoppen"
  docker compose --project-directory "$NEU" down || true
  schritt "Zurueck verschieben: $NEU -> $ALT"
  mv "$NEU" "$ALT"
  mv_db "$ALT/data" "$DB_NEU_NAME" "$DB_ALT_NAME"
  cp -p "$SICHERUNG/docker-compose.yml.alt" "$ALT/docker-compose.yml"
  cp -p "$SICHERUNG/config.env.alt" "$ALT/config.env"
  rm -f "$ALT/probe.override.yml"
  [ -s "$ALT/data/$DB_ALT_NAME" ] || abbruch "$ALT/data/$DB_ALT_NAME fehlt oder ist leer -- NICHT starten"
  if [ "$PROBE" = 1 ]; then
    # Die Kopie traegt die ALTE Compose-Datei: Port 8091 und volles Netz. Gestartet waere sie
    # eine zweite App neben der echten, die Push-Nachrichten verschicken kann. Also nie.
    echo "ZURUECK (Probe): verschoben und zurueckbenannt, NICHT gestartet."
    exit 0
  fi
  schritt "Alte App starten"
  docker compose --project-directory "$ALT" up -d
  if [ -f "$SICHERUNG/zaehlung-vorher.txt" ]; then
    zaehlen "$ALT/data/$DB_ALT_NAME" > "$SICHERUNG/zaehlung-zurueck.txt"
    vergleichen "$SICHERUNG/zaehlung-vorher.txt" "$SICHERUNG/zaehlung-zurueck.txt"
  fi
  echo "ZURUECK: alte App laeuft wieder aus $ALT."
  exit 0
fi

# ------------------------------------------------------------------------------------------
# Hinweg -- erst alles pruefen, was ohne Aenderung scheitern kann
# ------------------------------------------------------------------------------------------
REPO=${REPO:?REPO fehlt}
schritt "Vorbedingungen"
if [ "$PROBE" = 1 ]; then
  # Die Probe darf die echte App nie beruehren -- auch nicht ueber den Compose-Projektnamen,
  # der aus dem Ordnernamen kommt (ein Ordner .../friesenspy wuerde den echten Container treffen).
  [ "$(realpath -m "$ALT")" != "$LIVE" ] || abbruch "Probe zeigt auf die echte App"
  [ "$(basename "$ALT")" != friesenspy ] || abbruch "Probe-Ordner darf nicht friesenspy heissen"
else
  [ -n "${GH_TOKEN:-}" ] || abbruch "GH_TOKEN fehlt"
fi
[ -f "$ALT/data/$DB_ALT_NAME" ] || abbruch "$ALT/data/$DB_ALT_NAME fehlt"
[ ! -e "$NEU" ] || abbruch "$NEU existiert schon"
[ -f "$REPO/docker-compose.yml" ] || abbruch "$REPO/docker-compose.yml fehlt"
grep -q "image: ghcr.io/regover13/friesenradar" "$REPO/docker-compose.yml" || abbruch "Repo-Compose ist nicht die neue"
[ "$(grep -c '^DB_PATH=' "$ALT/config.env")" = 1 ] || abbruch "DB_PATH nicht genau einmal in config.env"
[ "$(grep -c '^FORUM_SSO_CALLBACK=' "$ALT/config.env")" = 1 ] || abbruch "FORUM_SSO_CALLBACK nicht genau einmal"
mkdir -p "$SICHERUNG"; chmod 700 "$SICHERUNG"
echo "ok"

if [ "$PROBE" != 1 ]; then
  schritt "Neues Image holen (die alte App laeuft dabei weiter)"
  echo "$GH_TOKEN" | docker login ghcr.io -u regover13 --password-stdin
  docker pull "$IMAGE" || { docker logout ghcr.io; abbruch "Pull gescheitert -- ist der Bau gruen? (gh api user/packages/container/friesenradar)"; }
  docker logout ghcr.io

  schritt "Container der alten App stoppen"
  STAND=gestoppt
  docker compose --project-directory "$ALT" down
  ! docker ps --format '{{.Names}}' | grep -qx friesenspy-friesenspy-1 || abbruch "Container laeuft noch"
fi

schritt "Pruefen, Zaehlen, Sichern ($ALT)"
ergebnis=$(als_dienst sqlite3 "$ALT/data/$DB_ALT_NAME" "PRAGMA integrity_check")
[ "$ergebnis" = ok ] || abbruch "integrity_check: $ergebnis"
als_dienst sqlite3 "$ALT/data/$DB_ALT_NAME" "PRAGMA wal_checkpoint(TRUNCATE)" >/dev/null
zaehlen "$ALT/data/$DB_ALT_NAME" | tee "$SICHERUNG/zaehlung-vorher.txt"
# Zwischenablage im Datenordner selbst, nicht in /tmp: Dort waere die Kopie der
# Mitgliederdaten fuer jeden Benutzer der Maschine lesbar.
tmp="$ALT/data/.umzug-sicherung.db"
rm -f "$tmp"
( umask 077; als_dienst sqlite3 "$ALT/data/$DB_ALT_NAME" ".backup '$tmp'" )
mv "$tmp" "$SICHERUNG/$DB_ALT_NAME"
cp -p "$ALT/docker-compose.yml" "$SICHERUNG/docker-compose.yml.alt"
cp -p "$ALT/config.env" "$SICHERUNG/config.env.alt"
[ -s "$SICHERUNG/$DB_ALT_NAME" ] || abbruch "Sicherung leer"

schritt "Verschieben: $ALT -> $NEU"
STAND=verschoben
mv "$ALT" "$NEU"
mv_db "$NEU/data" "$DB_ALT_NAME" "$DB_NEU_NAME"
fremde=$(find "$NEU/data" -maxdepth 1 -name "$DB_NEU_NAME*" ! -user containersvc)
[ -z "$fremde" ] || abbruch "DB-Dateien mit falschem Besitzer: $fremde"

schritt "Compose und config.env einsetzen"
install -m 644 -o root -g root "$REPO/docker-compose.yml" "$NEU/docker-compose.yml"
sed -i "s|^DB_PATH=.*|DB_PATH=$DB_NEU_IM_CONTAINER|" "$NEU/config.env"
sed -i "s|^FORUM_SSO_CALLBACK=.*|FORUM_SSO_CALLBACK=https://friesenradar.devprops.de/auth/forum/callback|" "$NEU/config.env"

compose=(docker compose --project-directory "$NEU" -f "$NEU/docker-compose.yml")
if [ "$PROBE" = 1 ]; then
  cat > "$NEU/probe.override.yml" <<'YML'
services:
  friesenradar:
    image: ghcr.io/regover13/friesenradar:probe
    network_mode: none
    ports: !reset []
    restart: "no"
YML
  compose+=(-f "$NEU/probe.override.yml")
fi

schritt "Gegenprobe der Konfiguration"
konfig=$("${compose[@]}" config)
echo "$konfig" | grep -E 'image:|target:|source:|DB_PATH'
echo "$konfig" | grep -q 'image: ghcr.io/regover13/friesenradar' || abbruch "falsches Image"
echo "$konfig" | grep -q 'target: /opt/friesenradar/data' || abbruch "falscher Mount"
echo "$konfig" | grep -q "DB_PATH: $DB_NEU_IM_CONTAINER" || abbruch "DB_PATH passt nicht"
[ -s "$NEU/data/$DB_NEU_NAME" ] || abbruch "DB-Datei am Ziel fehlt oder ist leer"

schritt "Starten"
STAND=gestartet
"${compose[@]}" up -d
c=friesenradar-friesenradar-1

schritt "Gesundheit"
for i in $(seq 1 24); do
  sleep 5
  if docker exec "$c" python -c "import urllib.request,sys; sys.exit(0 if b'\"ok\"' in urllib.request.urlopen('http://127.0.0.1:8091/health',timeout=3).read() else 1)" 2>/dev/null; then
    echo "Health OK (nach $((i*5)) s)"; break
  fi
  [ "$i" -lt 24 ] || { docker logs --tail 40 "$c"; abbruch "Health-Check rot"; }
done

schritt "DB im Container"
docker exec "$c" python -c "
import os; from app.config import get_settings as g; p=g().DB_PATH
print(p, os.path.getsize(p)); assert p == '$DB_NEU_IM_CONTAINER', p; assert os.path.getsize(p) > 0"

schritt "Zaehlung nachher"
zaehlen "$NEU/data/$DB_NEU_NAME" | tee "$SICHERUNG/zaehlung-nachher.txt"
vergleichen "$SICHERUNG/zaehlung-vorher.txt" "$SICHERUNG/zaehlung-nachher.txt"

echo
echo "FERTIG. Rueckweg, falls noetig:"
echo "  ZURUECK=1 ALT=$ALT NEU=$NEU SICHERUNG=$SICHERUNG sudo -E bash $0"
