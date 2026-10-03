# TV-Modus — technische Notizen

Für Mitglieder steht die Bedienung in der README („📺 TV-Modus“). Hier steht, was man wissen
muss, bevor man am Code etwas ändert. Der Code liegt in `app/static/index.html` zwischen
`//  TV-MODUS (?tv=1)` und `//  ENDE TV-MODUS`; die Tests in `tests/test_tv_modus.py`.

Stand: 03.10.2026, Branch `bruegge-radar` (Teil von 16.0.0 „Lichtblick“). Erprobt am Fire TV
Stick 4K mit Fully Kiosk Browser 1.61.3 (WebView, Chrome 148).

## Ein- und Ausschalten

- `html.tv` setzt das Kopfskript ganz oben in der Seite: bei `?tv=1` **oder** wenn im
  Browser-Speicher `friesenradar_tv = '1'` steht. Im Kniebrett (`/panel`, `?vr=1`) nie; auf
  schmalen Bildschirmen (≤ 600 px) gilt der Merker nicht.
- Der Schalter „TV-Modus An/Aus“ in den Einstellungen (`#einst-tv`, im Kniebrett und auf dem
  Handy ausgeblendet) schreibt den Merker und lädt neu (`_tvModusSetzen`).
- **Der Merker gehört dem Gerät, nicht dem Konto** (Nutzerentscheidung): Sonst startete auch
  der PC desselben Mitglieds im TV-Modus. Also `localStorage`, nicht `_prefSchreib`.
- Das Kartenvollbild des TV-Modus ist erzwungen und wird **nicht** gemerkt
  (`toggleMapFullscreen` schreibt im TV-Modus keinen Merker); „Aus“ setzt ihn zurück.
- Weitere Parameter: `&rundflug=1` (alt: `&rundgang=1`) startet den Rundflug, `&mitte=lat,lon`
  `&zoom=n` hält einen festen Ausschnitt, `&diag=1` schreibt Abrufe `/api/tv-diag?…` ins
  nginx-Log (Fernsicht auf den Stick), `&zurueck=0` legt keine Historien-Einträge an.

## Fernbedienung

- Pfeile springen **räumlich** zum nächsten Ziel (`_tvNaechstes`), OK löst aus, Zurück schließt.
  Fully Kiosk macht aus „Zurück“ ein `history.back()` — deshalb legt jeder Tastendruck einen
  Historien-Eintrag an (`_tvHistorieAuflegen`), sonst beendet Zurück die App.
- Am Fire TV sind `+`/`−` die Lautstärke; gezoomt wird mit den Spultasten.
- **Was anwählbar ist, entscheidet der Hand-Zeiger** (`cursor: pointer`), nicht eine
  Klassenliste (`_tvFokussierbarMachen`). Die Zeilen der Event- und Statistik-Listen sind `<tr>`
  mit Klick-Lauscher, ohne Klasse und ohne `onclick` — eine Liste fände sie nie vollständig.
  **Deshalb darf der TV-Modus den Mauszeiger nicht per `cursor: none` ausblenden.**
- Bereich (`_tvBereich`): offenes Fenster → offene Ebenen-Liste → **sichtbares** Kartenvollbild
  → Seite. Eine Vollbild-Klasse an einer unsichtbaren Karte zählt nicht (Fund am Stick: Pfeile
  tot auf dem Live-Tab).
- Keine Sprungziele: die Karte selbst (finge jeden Pfeil ab), Links nach außen (dort führt kein
  Weg zurück), Fensterkästen mit `onclick="event.stopPropagation()"`.
- Fokus: oranger Schein ohne Rahmen (`html.tv *:focus`); Tabellenzeilen zusätzlich mit orangem
  Grund, weil nicht jeder Browser den Schein an `<tr>` zeichnet.

## Rundflug (im Code `_tvRundgang…`)

- 30 s je Flugzeug, Zoomstufe 12, Schwenk 5 s; gewählt wird, wer sich bewegt (ab 1 kt),
  Stehende nur, wenn niemand fliegt. Während der Verweilzeit wird im Sekundentakt nachgeführt —
  nur bei mindestens 3 Bildpunkten Abweichung und ohne Animation.
- **Die Kachel-Unterlage** (`_tvUnterlage…`) ist der Grund, warum der Schwenk nicht ins Weiße
  fährt. Drei gemessene Tatsachen dahinter:
  1. Der Kachelserver der Flugkarte schickt **keine Cache-Angaben**. Ein vorab mit `new Image()`
     geholtes Bild ist beim zweiten Mal wieder ein Netzabruf — Vorladen ohne DOM ist wirkungslos.
  2. Leaflet hält den Stick für ein Mobilgerät (`updateWhenIdle: true`) und lädt Kacheln erst,
     wenn die Bewegung endet. `updateWhenIdle: false` macht es bei schwachem Netz **schlechter**.
  3. Die Flugkarte liefert unterhalb von Stufe 7 nur leere Kacheln, und `flyTo` zoomt beim
     Schwenk um die halbe Welt bis Stufe 2–4 heraus.
- Deshalb: eigene Kachel-Ebenen im Feld `tvUnterlage` (unter der Grundkarte), je eine feste
  Stufe, `_update` abgeschaltet — gefüllt wird gezielt per `_addTile`: die ganze Welt in Stufe 2,
  der Weg in der feinsten Stufe mit vertretbar vielen Kacheln, das Ziel in Stufe 12 und 10.
  Unterhalb von Stufe 7 kommt die Unterlage vom Satellitenbild. Flugkarten-Kacheln sind
  durchsichtig und bekommen den Grund der Karte; nach dem Schwenk wird das Feld ausgeblendet.
  Die Unterlage für den **nächsten** Schwenk lädt während der Verweilzeit.
- Gemessen (Kennung des Sticks, gedrosselte Leistung): vorher 0–10 % Karte am weitesten Punkt,
  jetzt 75–100 %, auch Deutschland–Neuseeland.
- Benutzt Leaflet-Interna (`_addTile`, `_removeTile`, `_level`, `_tiles`); Leaflet 1.9.4 ist
  per Integritätsprüfung festgenagelt. Wer Leaflet hebt, prüft die Unterlage im Browser.

## Schwache Hardware

Im TV-Modus läuft keine Keyframe-Animation, Scanline und Gitter sind aus (`html.tv …`).
Übergänge (`transition`) bleiben — daran hängen Leaflets Zoom und das Ausblenden der Knöpfe.

## Ruhezustand

Nach 10 s ohne Taste verschwinden die Knöpfe der Vollbild-Karte (`html.tv.tv-ruhe`), oben
mittig steht das Logo in der Fassung der eingestellten Darstellung — ohne Hintergrund, die
Logofarben werden nie geändert. Die Rundflug-Zeile bleibt stehen (schlicht, ohne Schein und
Rahmen). Die Quellenangabe der Karte bleibt immer sichtbar (Lizenzpflicht).

## Syntax

Dieselbe Datei lädt Coherent GT (Chrome 49) im Kniebrett. Im TV-Block deshalb keine
Pfeilfunktionen, kein `?.`/`??`, kein `NodeList.forEach` — der Block läuft dort nie, muss aber
geparst werden können.

## Offen (Nutzer hat entschieden: so lassen)

- Das Logo kann im Ruhezustand über einer Beschriftung liegen.
- Fremdverkehr-Beschriftungen überlagern sich bei viel Verkehr.
- Das Mikrofonsymbol von Fire OS sitzt oben rechts und verdeckt derzeit nichts.
