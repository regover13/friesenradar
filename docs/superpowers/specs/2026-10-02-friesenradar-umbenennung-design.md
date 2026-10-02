# Umbenennung FriesenSpy → FriesenRadar (V16 „Lichtblick“) – Design

Stand: 02.10.2026. Grundlage: Issues #51–#56 und das Gespräch vom 01./02.10.2026.

## Ziel

FriesenSpy heißt künftig **FriesenRadar**. Vorgabe des Nutzers: **„Ich will nirgends mehr
FriesenSpy lesen!“** — nicht in der App, nicht im Forum, nicht in Ordnern, Repos, Docker oder
Doku. Release **16.0.0 „Lichtblick“**.

## Entscheidungen (aus den Issues)

1. **Name:** FriesenRadar. „Friesen“ bleibt, „Spy“ ist negativ belastet. Mit Micha besprochen.
2. **Logo:** abgeleitet aus den Original-SVGs des Repaint-Kits, „Flieger“ durch „Radar“ ersetzt.
   **Logofarben werden nie verändert**, nur offizielle Fassungen verwendet: im Dunklen
   „white and red“, im Hellen farbig, in Kopfzeile und Kniebrett ohne Inseln. Kopfzeile
   zentriert, 90 px (Handy 56 px, eigene Zeile). Kniebrett: Logo im Streifen, 42 px.
3. **App-Symbol:** das rote Flugzeug aus dem Logo, unverändert, auf **Weiß**.
4. **Adressen:** `radar.friesenflieger.de` (für Mitglieder, wartet auf Heinz),
   `friesenradar.devprops.de` (läuft), `friesenspy.devprops.de` (wird stilles Alias, s. u.).
5. **Versionsverlauf:** alte CHANGELOG-Einträge bleiben als Geschichte.
6. **Andere Repos:** Kommentare und Erwähnungen bleiben als Geschichte. Ausnahme: Technik, die
   den Containernamen nennt (Watchtower-Liste in `vaultwarden-setup`) und die Serverdoku, soweit
   sie Pfade und Befehle nennt.
7. **Forum-Beiträge** bleiben, wie sie sind. Unterforum und Thementitel werden umbenannt.
8. **Grenze:** Umbenannt wird, was ein Mensch beim Benutzen oder Verwalten liest. Was nur der Code
   liest, bleibt als technische Konstante: Merker-Schlüssel `friesenspy_*`, Gerätekennung
   `friesenspy_device`, Schnittstellenwert `source: 'friesenspy'`, Cookie-Namen `fs_*`, Bezeichner
   im Code (Nutzer 02.10.2026: weniger Risiko). Damit entfallen alle Datenmigrationen.
9. **Datierte Dokumente** (`docs/superpowers/`, Analysen mit Datum) bleiben als Geschichte. Damit
   spätere Sitzungen nicht auf den alten Namen zurückfallen, steht in `CLAUDE.md` ausdrücklich:
   Der Name ist FriesenRadar; „friesenspy“ in Code und alter Doku ist Konstante bzw. Geschichte.

## Was „nirgends lesen“ technisch bedeutet

| Bereich | Ergebnis | Weg |
|---|---|---|
| App (Website, Kniebrett, Admin, Download-, Rechtstext- und Anmeldeseiten, Widget, Push, Telegram, Manifest, Symbole, Favicon) | neuer Name | Code, 16.0.0 |
| Forum | Unterforum „FriesenRadar“, Thema „FriesenRadar – Entwicklungsstand“, Widget-Einbettung auf neue Adresse | Board-Admin (Nutzer/Heinz) bzw. ich mit Freigabe |
| Vereinswebsite | Widget-Einbettung auf neue Adresse | Micha |
| GitHub | Repo `regover13/friesenradar`, Image `ghcr.io/regover13/friesenradar` | Umbenennen; GitHub leitet alte Links weiter |
| Server | `/opt/friesenradar`, Container `friesenradar-friesenradar-1`, `friesenradar.db`, nginx-, Zertifikat-, fail2ban-, Backup-Namen | Umzug in einem ruhigen Fenster |
| Kniebrett-Paket | Ordner `friesenflieger-friesenradar-efb`, Titel, Symbol, Adresse | neue Paketversion 3.0.0 |
| FriesenBrügge | Texte und Adresse | neue Fassung |
| Code-Interna | **bleiben** als technische Konstante (Entscheidung 8) | — |
| Doku im Repo | README, CLAUDE.md, COORDINATION.md, laufende Doku | Text |
| Claude | Arbeitsordner, venv, Gedächtnis, Freigaben | lokal |

**Bleibt, weil Geschichte oder unveränderlich:** CHANGELOG-Einträge vor 16.0.0, Commit-Historie,
alte Gesprächsprotokolle, alte Forumsbeiträge, Erwähnungen in anderen Repos.

## Was nicht sofort weg kann: `friesenspy.devprops.de`

Installierte Brüggen und Kniebrett-Pakete haben die Adresse fest eingebaut, und alte
Forumsbeiträge betten Badges und Widget von dort ein. Lösung:

- Neue Paket- und Brügge-Fassungen sprechen die neue Adresse an.
- Die alte Adresse bleibt **stilles Alias** im selben Vhost: liefert dieselbe App, aber niemand
  liest sie mehr (keine Links, keine Texte nennen sie).
- Abgeschaltet wird sie erst, wenn in der Datenbank keine alte Brügge (`bruegge_zuordnung`,
  Version und `gesehen_am`) und kein altes Paket (`panel_devices`) mehr meldet — das nginx-Log
  enthält erfolgreiche Brügge-Meldungen gar nicht. Badges in alten Beiträgen würden dann brechen — deshalb
  vermutlich **nie**, sondern dauerhaft als stilles Alias (Entscheidung beim Aufräumen).

**Technische Heimat für Paket und Brügge:** `friesenradar.devprops.de` (unter eigener Kontrolle).
`radar.friesenflieger.de` ist die Adresse, die Mitglieder lesen (Forum, Ankündigung), hängt
aber am DNS des Vereins.

## Daten und Merker

Entfällt durch Entscheidung 8: Merker, Gerätekennung, Schnittstellenwerte und gespeicherte Daten
behalten ihre Schlüssel. Keine Migration, kein Risiko für die 19 eingefrorenen Ergebnisse
(`progress_snapshot`) und keine erneute Anmeldung von Tablets. Das Kniebrett-Paket 3.0.0 liest
und schreibt weiter `friesenspy_device`.

## Reihenfolge

1. **Server-Umzug (kurze Unterbrechung, ruhiges Fenster):** Repo und Image umbenennen,
   `/opt/friesenradar`, DB-Datei, Container, nginx/Zertifikat/fail2ban/Backup/Watchtower,
   `config.env` (DB_PATH, FORUM_SSO_CALLBACK — **geschützte Datei, nur mit Freigabe**),
   Deploy-Workflow. Gegenprobe: App, Login, Brügge-Meldungen, Backup-Probelauf.
2. **16.0.0 „Lichtblick“ (sichtbar):** neuer Name überall, Vorschau-Schalter entfällt,
   Widget-Text, Manifest/Symbole, README. Ankündigung im Forum „V16 - Lichtblick“.
   Forum-Umbenennungen und Widget-Einbettung am selben Tag.
3. **Kniebrett-Paket 3.0.0 und neue Brügge:** neue Adresse und Namen; Kennung bleibt. Das
   Paket weist im Tablet selbst auf ein veraltetes Paket hin (vorhandener Mechanismus).
4. **Aufräumen:** altes GHCR-Paket, altes Zertifikat, Claude-Arbeitsumgebung, Gedächtnis,
   Serverdoku. Entscheidung über das Alias erst nach Messung.

## Risiken und Gegenmittel

- **Datenverlust beim DB-Umzug:** vorher `.backup` (nie `cp` bei WAL), Container gestoppt, danach
  Zeilenzahlen vergleichen.
- **Backup läuft ins Leere:** Probelauf des Backup-Skripts direkt nach dem Umzug.
- **fail2ban/Watchtower greifen still nicht mehr:** jeweils Gegenprobe (fail2ban-regex,
  Watchtower-Liste gegen `docker ps`).
- **Eingefrorene Ergebnisse:** werden nicht angefasst (keine Migration).
- **Mitglieder mit alter App/altem Paket:** stilles Alias. Android zieht Name und Symbol der
  installierten App selbst nach; auf iPhone/iPad bleibt der alte Name bis zur Neuinstallation.
  Push-Abos hängen an der Adresse, über die sie eingeschaltet wurden — gehört in die Ankündigung.
- **Parallele Sitzungen:** COORDINATION.md-Eintrag vor dem Umzug, Pfade ändern sich für alle.

## Zeitpunkt

Server-Umzug, wenn der Nutzer Zeit hat — er gibt Bescheid. Alles davor (Vorbereitung im Code,
Plan, Tests) läuft unabhängig davon.
