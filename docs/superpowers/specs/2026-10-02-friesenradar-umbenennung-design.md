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
| Code-Interna | Bezeichner, Merker-Schlüssel, API-Werte | mit Migration, s. u. |
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
- Abgeschaltet wird sie erst, wenn im nginx-Log keine alte Brügge (`/api/bruegge/melden`) und
  kein altes Paket mehr meldet. Badges in alten Beiträgen würden dann brechen — deshalb
  vermutlich **nie**, sondern dauerhaft als stilles Alias (Entscheidung beim Aufräumen).

**Technische Heimat für Paket und Brügge:** `friesenradar.devprops.de` (unter eigener Kontrolle).
`radar.friesenflieger.de` ist die Adresse, die Mitglieder lesen (Forum, Ankündigung), hängt
aber am DNS des Vereins.

## Daten und Merker

Gemessen am 02.10.2026 (Produktions-DB, nur lesend):

| Fundstelle | Anzahl | Umgang |
|---|---|---|
| `flight_cache.source = 'friesenspy'` | 1140 | API-Wert wird `radar`; Lesen akzeptiert beide Werte, Cache füllt sich neu |
| `progress_snapshot.payload_json` | 2 | **eingefrorene, enthüllte Ergebnisse — nie neu berechnen, nie umschreiben**; Code muss den alten Wert beim Lesen verstehen |
| `panel_diag.payload_json` | 500 | Diagnose-Protokoll, bleibt (räumt sich selbst ab) |
| `panel_prefs.prefs_json` | 46 | Merker-Schlüssel `friesenspy_*` → `radar_*`: einmalige Migration in der DB beim Start, im Browser Rückfall auf den alten Schlüssel (Cookie `fs_karte`, localStorage) mit Umschreiben |

Kniebrett-Gerätekennung `friesenspy_device` (MSFS-Ablage): Die neue Paketversion liest den
alten Schlüssel, wenn der neue fehlt, und schreibt ihn unter dem neuen Namen. Damit bleibt jedes
Tablet gebunden.

Cookie-Namen `fs_*` bleiben (lesen sich nicht als FriesenSpy, ein Umbenennen meldete alle ab).

## Reihenfolge

1. **Vorbereitung (unsichtbar):** Code auf neue Interna mit Rückwärtsverstehen (Merker,
   API-Wert), alles noch unter altem Namen ausgeliefert. Tests.
2. **Server-Umzug (kurze Unterbrechung, ruhiges Fenster):** Repo und Image umbenennen,
   `/opt/friesenradar`, DB-Datei, Container, nginx/Zertifikat/fail2ban/Backup/Watchtower,
   `config.env` (DB_PATH, FORUM_SSO_CALLBACK — **geschützte Datei, nur mit Freigabe**),
   Deploy-Workflow. Gegenprobe: App, Login, Brügge-Meldungen, Backup-Probelauf.
3. **16.0.0 „Lichtblick“ (sichtbar):** neuer Name überall, Vorschau-Schalter entfällt,
   Widget-Text, Manifest/Symbole, README. Ankündigung im Forum „V16 - Lichtblick“.
   Forum-Umbenennungen und Widget-Einbettung am selben Tag.
4. **Kniebrett-Paket 3.0.0 und neue Brügge:** neue Adresse, Namen, Migration der Kennung. Das
   Paket weist im Tablet selbst auf ein veraltetes Paket hin (vorhandener Mechanismus).
5. **Aufräumen:** altes GHCR-Paket, altes Zertifikat, Claude-Arbeitsumgebung, Gedächtnis,
   Serverdoku. Entscheidung über das Alias erst nach Messung.

## Risiken und Gegenmittel

- **Datenverlust beim DB-Umzug:** vorher `.backup` (nie `cp` bei WAL), Container gestoppt, danach
  Zeilenzahlen vergleichen.
- **Backup läuft ins Leere:** Probelauf des Backup-Skripts direkt nach dem Umzug.
- **fail2ban/Watchtower greifen still nicht mehr:** jeweils Gegenprobe (fail2ban-regex,
  Watchtower-Liste gegen `docker ps`).
- **Eingefrorene Ergebnisse:** Snapshot-Version nicht erhöhen; Test, der den alten Wert liest.
- **Mitglieder mit alter App/altem Paket:** stilles Alias; installierte PWAs behalten ihren Namen
  bis zur Neuinstallation — gehört in die Ankündigung.
- **Parallele Sitzungen:** COORDINATION.md-Eintrag vor dem Umzug, Pfade ändern sich für alle.

## Offene Fragen an den Nutzer

1. **Laufende Doku vs. Geschichte im Repo:** Datierte Specs, Pläne und Analysen unter
   `docs/superpowers/` (rund 570 Stellen) — als Geschichte stehen lassen wie den CHANGELOG, oder
   umschreiben? Vorschlag: datierte Dokumente bleiben, laufende Doku (README, CLAUDE.md,
   COORDINATION.md, `docs/*.md` ohne Datum) wird umgeschrieben.
2. **Interne API-Werte und Bezeichner** (`source: 'friesenspy'`, Funktionsnamen): mit umbenennen
   (Vorschlag: ja, mit Rückwärtsverstehen) oder nur, was ein Mensch liest?
3. **Zeitfenster** für den Server-Umzug (ein paar Minuten Ausfall).
