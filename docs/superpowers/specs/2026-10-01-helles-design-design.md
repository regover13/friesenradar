# Helles Design – Design

Stand: 01.10.2026, aus einem Gespräch mit dem Nutzer entstanden.

## Ziel

FriesenSpy bekommt neben dem heutigen dunklen ein **helles Design**, umschaltbar auf der Website
und im Kniebrett (Tablet im Sim). Die Wahl wird je Nutzer gespeichert. Gleichzeitig ersetzt auf
der Website das **Zahnrad** die Glocke, und der Schalter steht im selben Einstellungsmenü wie im
Kniebrett.

Beweggrund ist **Geschmack**, nicht Tag/Nacht-Lesbarkeit. Daraus folgt: keine Automatik nach
Tageszeit oder `prefers-color-scheme`.

## Entscheidungen aus dem Gespräch

1. **Standard bleibt Dunkel.** Hell ist eine bewusste Wahl.
2. **Die Karte schaltet nicht mit.** Die Grundkarte wählt der Nutzer ohnehin selbst (Merker
   `friesenspy_layer`), dazu die Kartenhelligkeit im Kniebrett. Alles, was auf der Karte
   gezeichnet wird – Pilotenlinien, Marker, Platzrunden, Kutter, Reddung – behält seine Farben.
3. **Getrennt gespeichert** für Website (`kontext=web`) und Kniebrett (`kontext=panel`).
4. **Aufblitzen im Kniebrett wird in Kauf genommen.** Dort kommt der Wert erst mit der
   Serverantwort (kein Browser-Speicher über einen Sim-Neustart); bis dahin ist die Seite dunkel.
5. **Keine neue Hauptnummer.** Nebenversion (voraussichtlich 15.32.0).
6. **Das dunkle Design bleibt exakt, wie es ist – kein Farbwert ändert sich.** Der Umbau auf
   Variablen ist dort reine Umbenennung: Jede Variable trägt im dunklen Design genau den Wert,
   der vorher an der jeweiligen Stelle stand. Keine Vereinheitlichung, keine „Aufräum"-Angleichung
   ähnlicher Töne. (Das Mockup vom 01.10.2026 wich im Dunklen sichtbar vom Original ab – genau
   das darf der Umbau nicht.)
7. **Die Friesenfarben bleiben.** Die helle Palette stammt aus dem Forum
   (`board.friesenflieger.de`, Stil `Friesen.new/theme/colours.css`) und deckt sich mit der
   Website (`#9ec7f8`, `#053080`) und dem FriesenSpy-Forum-Widget (`#d0e0f0`, `#053080`). Keine
   eigene Palette erfinden.

## Umfang

**Betroffen:** nur `app/static/index.html` (Website und Kniebrett sind dieselbe Datei).

**Nicht betroffen:** `admin.html`, `efb.html`, `impressum.html`, `datenschutz.html`,
`warenweg.html`, das Forum-Widget (`/widget`, ohnehin hell), die vom Server erzeugten Seiten in
`main.py` (`/auth/device`, Push-Übersicht), das MSFS-Paket (nur iframe-Hülle), `badge.py`.

## Bedienung

- **Zahnrad statt Glocke auf der Website.** Der Knopf `#notif-btn` enthält das Zahnrad bereits
  (`notif-zahnrad-panel`), bisher nur im Kniebrett eingeblendet. Es wird überall gezeigt, die
  Twemoji-Glocke (`notif-glocke-web`) entfällt; die gezeichnete Glocke als Verbindungsanzeige
  bleibt, wie sie ist. Der Knopf-Titel lautet „Einstellungen".
- **Menü heißt überall „Einstellungen".** Auf der Website bekommt `#notif-panel` einen Abschnitt
  **„Anzeige"** mit dem Design-Schalter; die bisherigen Push- und Sichtbarkeitsteile folgen
  unverändert unter der Überschrift **„Benachrichtigungen"**. Im Kniebrett kommt der Schalter in
  den vorhandenen Abschnitt „Anzeige" (`#panel-anzeige`) neben Größe und Kartenhelligkeit.
- **Der Schalter** besteht aus zwei Knöpfen „Dunkel" / „Hell", der aktive hervorgehoben. Keine
  Checkbox, kein per `innerHTML` eingesetztes SVG (beides zeigt Coherent GT nicht zuverlässig).
- **Wirkt sofort**, ohne Neuladen.
- **Sichtbarkeit des Knopfes:** Heute erscheint `#notif-btn` auf der Website nur mit gesetztem
  VAPID-Schlüssel. Da das Menü jetzt auch die Anzeige enthält, wird der Knopf **immer** gezeigt;
  ohne VAPID-Schlüssel fehlt dann nur der Abschnitt „Benachrichtigungen".

## Speicherung

- Merker **`friesenspy_theme`** mit den Werten `dunkel` | `hell`, geschrieben über
  `_prefSchreib`, gelesen über `_prefLies`. Unbekannter oder fehlender Wert = `dunkel`.
- Weg wie bei den übrigen Merkern: Cookie → localStorage → `PUT /api/prefs?kontext=…`; beim
  Start gewinnt der Server. Kein neuer Endpunkt, keine Schemaänderung (Grenze 40 Schlüssel je
  Kontext, heute rund 20 belegt).
- **Ohne Board-Login** bleibt die Wahl im Browser (Cookie/localStorage) – `PUT /api/prefs`
  antwortet dort mit 401, das ist das bestehende Verhalten.
- **Früher Anstrich auf der Website:** Das Kopfskript (dort, wo heute `html.vr-panel` gesetzt
  wird) liest den Merker aus dem Cookie und setzt `html.hell` vor dem ersten Rendern.
- **Kniebrett:** `html.hell` wird gesetzt, sobald `_prefVomServerHolen()` antwortet.

## Farbsystem

**Weg:** Farben mit Bedeutung als CSS-Variablen, ein Überschreibungsblock `html.hell { … }`.
Verworfen: Invertier-Filter (verfälscht das Friesenrot, kostet in Coherent GT Leistung – das
Forum nutzt ihn mit der Erweiterung `aurelienazerty/darkmode`, dort sieht man genau das) und zwei
getrennte Stylesheets (jede Änderung doppelt).

### Palette

| Variable | Dunkel (unverändert) | Hell (Forum) | Kontrast auf `#FBFBFB` |
|---|---|---|---|
| `--bg-body` | `#04080f` | `#9FC7F8` Himmelblau | – |
| `--bg-panel` | `#071525` | `#FBFBFB` | – |
| `--bg-panel-2` | `#091b30` | `#F1F8FF` | – |
| `--text-bright` | `#d4e8f5` | `#2B3C5A` | 10,7:1 |
| `--text-label` | `#6b9ab8` | `#536482` | 5,8:1 |
| `--green` (Blau, klickbar) | `#2d9cdb` | `#105289` | 7,8:1 |
| `--green-rgb` (neu, Kanalwerte) | `45,156,219` | `16,82,137` | – |
| `--green-dim/-glow/-faint/-grid` | unverändert | rgba von `#105289` | – |
| `--cyan` (Friesenrot) | `#D31141` | `#D31141` | 5,2:1 |
| `--amber` | `#f0a500` | `#8f5f00` | 5,3:1 |
| `--red` | `#ff5555` | `#c62828` | 5,4:1 |
| `--schleier-rgb` (neu) | `4,8,15` | `251,251,251` | – |
| `--schatten-rgb` (neu) | `0,0,0` | `43,60,90` (Schieferblau, weicher) | – |

**Transparenzstufen bleiben einzeln erhalten.** Im CSS stehen 24 verschiedene
`rgba(45,156,219,x)`-, `rgba(4,8,15,x)`- und `rgba(0,0,0,x)`-Werte. Statt sie auf wenige Stufen
zusammenzulegen (das änderte das dunkle Design), wird nur der Farbkanal zur Variable, die
Deckkraft bleibt an der Stelle: `rgba(45,156,219,0.15)` → `rgba(var(--green-rgb),0.15)`.
Coherent GT (Chrome 49) setzt `var()` innerhalb von `rgba()` ein; das wird in der Probe (Schritt
1) im Sim bestätigt, bevor der Rest darauf aufbaut. Wo ein Rahmen im hellen Design die
Forumsfarbe `#CADCEB` statt eines getönten Blaus braucht, bekommt er eine eigene Variable, deren
dunkler Wert der bisherige Originalwert ist.

**Regel aus dem Forum:** Friesenrot steht nie direkt auf Himmelblau (3,1:1), nur auf den hellen
Inhaltsflächen.

**Nebenbei repariert:** die heute benutzten, aber nirgends definierten Variablen `--text-dim`
(11 Stellen), `--blue` (3), `--text` (1) und `--color-label` (1) – sie werden definiert oder auf
vorhandene Variablen umgestellt.

### Umbau der festen Farbwerte

- **CSS (~214 feste Werte):** Jeder Wert wird entweder einer Variablen zugeordnet oder bleibt
  bewusst fest. Fest bleiben: Akzent Friesenrot, alles, was die Karte zeichnet, die Tempo- und
  Höhenschilder (wirken wie echte Schilder), Emoji/Bilder. Die rund 40 `rgba(45,156,219,x)`
  laufen über `--green-rgb`, jede mit ihrer bisherigen Deckkraft.
- **JavaScript:** Betroffen sind nur Farben außerhalb der Karte, vor allem die Statistik
  (Chart.js, `new Chart` ab ~Z. 14547, 16 feste Farben). Sie lesen ihre Farben beim Zeichnen
  per `getComputedStyle` aus den Variablen und werden beim Umschalten neu gezeichnet.
  Leaflet-Popups und -Bedienelemente sind CSS und laufen über die Variablen.
- **Meta-Farbe** `theme-color` folgt dem Design (`#04080f` bzw. `#9FC7F8`).

## Vorgehen und Prüfung

1. **Probe zuerst.** Variablen, Schalter und die Hauptflächen (Kopfzeile, Pilotenliste,
   Seitenleiste, ein Popup, Einstellungsmenü) umstellen. Der Nutzer sieht die Probe als
   Screenshots der echten Seite (Playwright gegen die lokal gestartete App, Website und
   `?vr=1`, beide Designs), abgelegt unter `files.friesenflieger.de/downloads/` und danach wieder
   gelöscht – Dateien im Chat anzeigen geht in dieser Umgebung nicht. Auf dem Server gibt es
   bisher keinen Browser; Chromium wird dafür einmalig im venv `~/.venv-friesenspy` installiert.
   **Weiter erst nach seinem OK.**
2. **Vollständiger Umbau** der übrigen Farbwerte, danach erneut Screenshots aller Reiter.
3. **Nachweis „Dunkel unverändert" (neuer Test):** Er nimmt den CSS-Teil von `index.html` vor dem
   Umbau (Stand aus git) und danach, setzt in der neuen Fassung jedes `var(--…)` mit dem dunklen
   Wert aus `:root` ein und vergleicht Regel für Regel. Abweichen darf nur, was hinzukommt
   (`html.hell`-Blöcke, Schalter-Stile). Dasselbe für die Farben, die JavaScript für die
   Statistik liest. Damit ist die Gleichheit des dunklen Designs belegt, ohne dass ein
   Screenshot-Vergleich Pixel für Pixel nötig wäre.
4. **Kontrasttest (neu):** rechnet für jede Paarung aus Text- und Hintergrundvariable das
   WCAG-Kontrastverhältnis in beiden Designs aus und verlangt ≥ 4,5:1 für Text.
5. **Bestehende Farb-Tests** (u. a. `test_vr_panel.py`, `test_vrp.py`, `test_ground_chart_ui.py`,
   `test_aip_ui.py`, `test_mithoeren.py`, `test_pilot_links.py`, ~12 Assertions mit wörtlichen
   Werten): Wird ein Wert zur Variable, wird die Assertion auf die Variable umgestellt, nicht
   gelöscht. `test_karte_merker.py` bekommt den neuen Merker.
6. **Sim-Prüfung durch den Nutzer:** Kniebrett öffnen, auf Hell schalten, einmal durch alle
   Reiter. Coherent GT ist hier nicht verfügbar; die Screenshots zeigen den Aufbau, nicht die
   Darstellung im Cockpit.

## Abschluss

- README-Absatz (Handbuch) und Hilfetext hinter dem `?` im selben Commit wie die sichtbare
  Änderung.
- CHANGELOG-Eintrag mit `"highlight": false`, Nebenversion.
- Deploy nicht in den laufenden Flugbetrieb; vorher fragen, wenn geflogen wird.
