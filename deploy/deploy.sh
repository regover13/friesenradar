#!/bin/bash
# =========================================================================
#  FriesenRadar — Einspielen auf dem VPS
# =========================================================================
#  Liegt auf dem Server als /opt/friesenradar/deploy.sh und ist der EINZIGE Befehl, den der
#  Deploy-Schluessel 'friesenspy-deploy' ausfuehren darf (restrict,command=... in
#  /root/.ssh/authorized_keys). Vorbild: /opt/tsbot/deploy.sh.
#
#  Warum (04.10.2026): Bis dahin meldeten sich die Workflows mit einem UNBESCHRAENKTEN
#  root-Schluessel an, ueber die fremde Action appleboy/ssh-action. Wer ins Repo pushen, das
#  Secret auslesen oder das Tag der Action umhaengen konnte, hatte eine Root-Shell auf der
#  Maschine, auf der auch Mailserver und Nextcloud liegen. Jetzt kann der Schluessel genau
#  zwei Dinge anstossen, und der Ablauf steht hier statt in der Workflow-Datei.
#
#  Aufruf (der sshd fuehrt NUR dieses Skript aus; was der Aufrufer als Kommando mitgibt,
#  landet in SSH_ORIGINAL_COMMAND und ist hier reine Eingabe):
#
#    SSH_ORIGINAL_COMMAND = "deploy"  -> Produktion: Image :latest holen, neu starten, pruefen
#                           "test"    -> Testinstanz: Image :test bereitlegen
#    stdin                = GITHUB_TOKEN des Workflow-Laufs (nur fuer den Pull)
#
#  Der Token gilt nur fuer die Laufzeit des Workflows und bleibt nicht auf dem Server.
#  Von Hand: `sudo /opt/friesenradar/deploy.sh deploy </dev/null` -- ohne Token greift, was in
#  /root/.docker/config.json steht, oder der Pull scheitert sauber.
#
#  ⚠ Dieses Skript wird NICHT automatisch ausgerollt -- es liegt auf dem Server, nicht im
#  Image. Wer es aendert, kopiert es nach /opt/friesenradar/deploy.sh (root, 755).
# =========================================================================
set -euo pipefail

IMAGE="ghcr.io/regover13/friesenradar"
AUFTRAG="${SSH_ORIGINAL_COMMAND:-${1:-}}"

case "$AUFTRAG" in
    deploy|test) ;;
    *)
        echo "Abbruch: unbekannter Auftrag -- erlaubt sind 'deploy' und 'test'." >&2
        exit 1
        ;;
esac

# ---- GHCR-Zugang: Token von stdin, nur fuer diesen Lauf --------------------------------
ANGEMELDET=0
abmelden() {
    [ "$ANGEMELDET" = 1 ] && docker logout ghcr.io >/dev/null 2>&1
    return 0
}
trap abmelden EXIT

TOKEN=""
if [ ! -t 0 ]; then
    read -r TOKEN || true
fi
if [ -n "$TOKEN" ]; then
    printf '%s' "$TOKEN" | docker login ghcr.io -u regover13 --password-stdin >/dev/null
    ANGEMELDET=1
    echo "== An GHCR angemeldet"
elif [ -n "${SSH_ORIGINAL_COMMAND:-}" ]; then
    # Ueber den Deploy-Schluessel ohne Token: Das ist kein Workflow-Lauf.
    echo "Abbruch: kein Token auf stdin." >&2
    exit 1
fi

if [ "$AUFTRAG" = "test" ]; then
    # Nur bereitlegen, nicht starten. Der lokale Tag macht das Startskript unabhaengig vom
    # Repo-Namen.
    echo "== Test-Image holen"
    docker pull "$IMAGE:test"
    docker tag "$IMAGE:test" test-radar:aktuell
    if [ -x /usr/local/bin/test-radar ]; then
        /usr/local/bin/test-radar aktualisieren
    fi
    # Das vorige Test-Image hat seinen Tag verloren; namenlose Reste wegraeumen.
    # Nur namenlose Images; NIE `prune -a` (siehe Serverdoku).
    docker image prune -f || true
    echo "== Test-Image liegt bereit"
    exit 0
fi

# ---- Produktion --------------------------------------------------------------------------
cd /opt/friesenradar
echo "== Image holen"
docker compose pull
echo "== Dienst starten"
docker compose up -d

# Health-Check: Der Deploy gilt erst als erfolgreich, wenn die App antwortet.
for i in $(seq 1 12); do
    sleep 5
    if curl -sf http://127.0.0.1:8091/health | grep -q '"status":"ok"'; then
        echo "Health OK (Versuch $i)"
        # Das abgeloeste Image hat seinen Tag verloren und bliebe sonst liegen: 191 Stueck in
        # vier Wochen, und Netdatas Docker-Abfrage wurde davon messbar langsamer. Erst NACH
        # dem Health-Check -- scheitert er, liegt der Vorgaenger noch da.
        # Nur namenlose Images; NIE `prune -a` (siehe Serverdoku).
        docker image prune -f || true
        exit 0
    fi
done
echo "Health-Check fehlgeschlagen — letzte Container-Logs:" >&2
docker compose logs --tail 50
exit 1
