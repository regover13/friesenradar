#!/usr/bin/env bash
# Umzug FriesenSpy -> FriesenRadar auf dem Server (Plan 2026-10-02, Task 2, Steps 9-15).
#
# Dasselbe Skript fuer die Generalprobe und den echten Abend -- erprobt wird also der Befehl
# selbst, nicht nur sein Ergebnis.
#
#   Probe:  PROBE=1 ALT=/opt/friesenspy-probe NEU=/opt/friesenradar \
#           REPO=~/projects/friesenspy-umzug SICHERUNG=/root/umzug-probe-<datum> \
#           sudo -E bash deploy/umzug-friesenradar.sh
#   Echt:   ALT=/opt/friesenspy NEU=/opt/friesenradar REPO=... SICHERUNG=/root/umzug-friesenradar-<datum> \
#           GH_TOKEN=... sudo -E bash deploy/umzug-friesenradar.sh
#
# Probe-Modus: Der Container startet OHNE Netzwerk (network_mode: none) -- er kann niemandem
# eine Push-Nachricht schicken und keinen Dienst anfragen. Die echte App bleibt unberuehrt.
#
# Bricht bei jedem Fehler ab. Der Rueckweg steht am Ende der Ausgabe.
set -euo pipefail

ALT=${ALT:?ALT fehlt}; NEU=${NEU:?NEU fehlt}; REPO=${REPO:?REPO fehlt}
SICHERUNG=${SICHERUNG:?SICHERUNG fehlt}; PROBE=${PROBE:-0}
LIVE=/opt/friesenspy
DB_ALT_NAME=friesenspy.db
DB_NEU_NAME=friesenradar.db
DB_NEU_IM_CONTAINER=/opt/friesenradar/data/$DB_NEU_NAME
TABELLEN_GLEICH="panel_devices panel_prefs push_subscriptions pilots progress_snapshot"
TABELLEN_WACHSEN="flights position_history bruegge_zuordnung"

schritt() { echo; echo "== $*"; }
abbruch() { echo "ABBRUCH: $*" >&2; exit 1; }
als_dienst() { sudo -u containersvc "$@"; }

[ "$(id -u)" = 0 ] || abbruch "als root ausfuehren"
if [ "$PROBE" = 1 ]; then
  # Die Probe darf die echte App nie beruehren -- auch nicht ueber den Compose-Projektnamen,
  # der aus dem Ordnernamen kommt (ein Ordner .../friesenspy wuerde den echten Container treffen).
  [ "$(realpath -m "$ALT")" != "$LIVE" ] || abbruch "Probe zeigt auf die echte App"
  [ "$(basename "$ALT")" != friesenspy ] || abbruch "Probe-Ordner darf nicht friesenspy heissen"
fi
[ -f "$ALT/data/$DB_ALT_NAME" ] || abbruch "$ALT/data/$DB_ALT_NAME fehlt"
[ ! -e "$NEU" ] || abbruch "$NEU existiert schon"
[ -f "$REPO/docker-compose.yml" ] || abbruch "$REPO/docker-compose.yml fehlt"
grep -q "image: ghcr.io/regover13/friesenradar" "$REPO/docker-compose.yml" || abbruch "Repo-Compose ist nicht die neue"
mkdir -p "$SICHERUNG"; chmod 700 "$SICHERUNG"

zaehlen() {   # $1 = DB-Datei; liest nur
  local db=$1 t
  for t in $TABELLEN_GLEICH $TABELLEN_WACHSEN; do
    printf '%s %s\n' "$t" "$(als_dienst sqlite3 -readonly "$db" "SELECT COUNT(*) FROM $t")"
  done
  printf 'snapshot_stand %s\n' "$(als_dienst sqlite3 -readonly "$db" \
    "SELECT COUNT(*) || '/' || COALESCE(MAX(computed_at),'') FROM progress_snapshot")"
}

if [ "$PROBE" != 1 ]; then
  schritt "Container der alten App stoppen"
  docker compose --project-directory "$ALT" down
  ! docker ps --format '{{.Names}}' | grep -qx friesenspy-friesenspy-1 || abbruch "Container laeuft noch"
fi

schritt "Pruefen, Zaehlen, Sichern ($ALT)"
ergebnis=$(als_dienst sqlite3 "$ALT/data/$DB_ALT_NAME" "PRAGMA integrity_check")
[ "$ergebnis" = ok ] || abbruch "integrity_check: $ergebnis"
als_dienst sqlite3 "$ALT/data/$DB_ALT_NAME" "PRAGMA wal_checkpoint(TRUNCATE)" >/dev/null
zaehlen "$ALT/data/$DB_ALT_NAME" | tee "$SICHERUNG/zaehlung-vorher.txt"
tmp=$(mktemp -u /tmp/umzug-sicherung-XXXXXX.db)
als_dienst sqlite3 "$ALT/data/$DB_ALT_NAME" ".backup '$tmp'"
mv "$tmp" "$SICHERUNG/$DB_ALT_NAME"
cp -p "$ALT/docker-compose.yml" "$SICHERUNG/docker-compose.yml.alt"
cp -p "$ALT/config.env" "$SICHERUNG/config.env.alt"
[ -s "$SICHERUNG/$DB_ALT_NAME" ] || abbruch "Sicherung leer"

schritt "Verschieben: $ALT -> $NEU"
mv "$ALT" "$NEU"
for endung in "" -wal -shm; do
  [ ! -e "$NEU/data/$DB_ALT_NAME$endung" ] || mv "$NEU/data/$DB_ALT_NAME$endung" "$NEU/data/$DB_NEU_NAME$endung"
done
fremde=$(find "$NEU/data" -maxdepth 1 -name "$DB_NEU_NAME*" ! -user containersvc)
[ -z "$fremde" ] || abbruch "DB-Dateien mit falschem Besitzer: $fremde"

schritt "Compose und config.env einsetzen"
install -m 644 -o root -g root "$REPO/docker-compose.yml" "$NEU/docker-compose.yml"
[ "$(grep -c '^DB_PATH=' "$NEU/config.env")" = 1 ] || abbruch "DB_PATH nicht genau einmal in config.env"
[ "$(grep -c '^FORUM_SSO_CALLBACK=' "$NEU/config.env")" = 1 ] || abbruch "FORUM_SSO_CALLBACK nicht genau einmal"
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
if [ "$PROBE" != 1 ]; then
  echo "${GH_TOKEN:?GH_TOKEN fehlt}" | docker login ghcr.io -u regover13 --password-stdin
  "${compose[@]}" pull || { docker logout ghcr.io; abbruch "Pull gescheitert -- Rueckfall: docker tag ghcr.io/regover13/friesenspy:latest ghcr.io/regover13/friesenradar:latest, dann up -d"; }
  docker logout ghcr.io
fi
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
while read -r t vorher; do
  nachher=$(awk -v t="$t" '$1==t{print $2}' "$SICHERUNG/zaehlung-nachher.txt")
  case " $TABELLEN_WACHSEN " in
    *" $t "*) [ "$nachher" -ge "$vorher" ] || abbruch "$t: $vorher -> $nachher" ;;
    *)        [ "$nachher" = "$vorher" ] || abbruch "$t: $vorher -> $nachher" ;;
  esac
done < "$SICHERUNG/zaehlung-vorher.txt"
echo "Zaehlung stimmt."

echo
echo "FERTIG. Rueckweg, falls noetig:"
echo "  ${compose[*]} down; mv $NEU $ALT; mv $ALT/data/$DB_NEU_NAME $ALT/data/$DB_ALT_NAME"
echo "  cp -p $SICHERUNG/docker-compose.yml.alt $ALT/docker-compose.yml; cp -p $SICHERUNG/config.env.alt $ALT/config.env"
echo "  docker compose --project-directory $ALT up -d"
