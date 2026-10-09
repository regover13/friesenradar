# Deichkontrolle: eine Strecke gemeinsam abfliegen (Entwurf)

Stand 10.10.2026. GitHub-Issue #22. Besprochen mit dem Nutzer am 09./10.10.2026; was er
entschieden hat, steht in Abschnitt 2 mit Datum, was angenommen ist, in Abschnitt 3.

## 1. Worum es geht

Die Gruppe fliegt gemeinsam eine **Strecke** ab: tief und nah daran entlang. Gewertet wird, welcher
Anteil der Strecke am Ende abgeflogen ist, von allen zusammen. Es gibt keinen Sieger; ein Balken
füllt sich mit Kilometern, wie beim FriesenKutter mit Kilogramm.

**„Deichkontrolle“ ist nur der Name.** Die Strecke ist frei: eine Grenze, eine Küste, ein Fluss,
ein Bergkamm. Nichts im Bau hängt an Deichen oder an der Küste. Im Code heißt der Eventtyp deshalb
neutral `strecke`.

## 2. Entschieden

| | Entscheidung | Nutzer |
|---|---|---|
| E1 | **Nur eine Strecke**, keine Fläche. Flächen sucht die FriesenReddung ab. | 10.10. |
| E2 | **Die Strecke wird in der Verwaltung auf der Karte geklickt.** Keine fremde Datenquelle. | 10.10. |
| E3 | **Die FriesenBrügge ist Pflicht**, weil die genauen Positionen gebraucht werden. | 10.10. |
| E4 | **Höhe wie bei der Reddung:** Geländehöhe aus dem Höhenmodell, hier **je Abschnitt**. Geprüft wird die Höhe über Meer gegen „Gelände am Abschnitt + eingestellte Höhe“. | 10.10. |
| E5 | **Korridor und Höhe sind je Event einstellbar.** | 10.10. |
| E6 | **Geschwindigkeit wie bei der Reddung:** Höchst- und Mindestwert je Event. | 10.10. |
| E7 | **Karte:** Die Strecke ist der Fortschrittsbalken, der Korridor liegt als Band darunter, ein Umschalter wechselt zwischen einer Farbe für alle und einer Farbe je Pilot. | 10.10. |

## 3. Angenommen (bitte beim Lesen prüfen)

| | Annahme |
|---|---|
| A1 | Vorgaben: Korridor **500 m** nach jeder Seite, Höhe **1.000 ft** über der Strecke, Geschwindigkeit **30 bis 140 kt**. |
| A2 | Die **Abschnittslänge ist das Doppelte des Korridors** und wird nicht eigens eingestellt. Wer genau auf der Strecke fliegt, deckt damit lückenlos ab. |
| A3 | Ein Abschnitt gehört dem, der ihn **zuerst** abfliegt. Je Pilot stehen die geholten Kilometer in einer Liste; eine Rangfolge wird nicht ausgerufen. |
| A4 | Angelegt wird **von Hand** in der Verwaltung, wie Kutter und Reddung. |
| A5 | Die Strecke ist **ab Eventbeginn** sichtbar; nach dem Ende bleibt der Endstand stehen. Zu verbergen gibt es nichts. |
| A6 | **VATSIM füllt Lücken der Brügge**, aber nur für Piloten, die im Event schon per Brügge gemeldet haben (dieselbe Regel wie bei der Reddung, Bezug ist der Eventbeginn). |
| A7 | Fehlen die Geländehöhen (Abruf gescheitert), wird **nicht gerechnet**, statt ohne Höhenprüfung zu werten. Verwaltung und Eventansicht sagen das. |

## 4. Nicht im ersten Bau

- Objekte im Simulator, Badge, Push-Meldungen, Forum-Text.
- Die Anzeige, warum ein Pilot gerade nichts holt („zu hoch“, „zu weit weg“).
- Erkennung aus dem Kalender.
- Freie Flächen (E1).

## 5. Datenmodell

Neue Tabelle `strecken_events`:

| Spalte | Inhalt |
|---|---|
| `id`, `name`, `dtstart`, `dtend` | wie `reddung_events`; `dtend` leer heißt Mitternacht des Folgetags |
| `punkte_json` | die geklickten Punkte, `[[lat, lon], …]`, mindestens 2, höchstens 500 |
| `korridor_m` | Vorgabe 500 |
| `hoehe_max_ft` | Vorgabe 1000, **über der Strecke** |
| `gs_max_kt`, `gs_min_kt` | Vorgabe 140 und 30 |
| `grund_json` | Geländehöhe je Abschnitt in ft über Meer, in Reihenfolge der Abschnitte; `NULL`, solange nicht geholt |
| `grund_geholt_am` | Zeitpunkt des letzten erfolgreichen Abrufs |

Die Abschnitte selbst werden nicht gespeichert. Sie entstehen jedes Mal gleich aus `punkte_json` und
`korridor_m` (`abschnitte_aus_linie`, Länge `2 × korridor`). `grund_json` gehört zu genau dieser
Teilung: Ändern sich Punkte oder Korridor, wird es verworfen und neu geholt.

Grenzen beim Speichern: höchstens **2.000 Abschnitte**; mehr lehnt die Verwaltung mit einer
verständlichen Meldung ab (Korridor vergrößern oder Strecke kürzen).

Der Stand liegt in `progress_snapshot` unter `kind = 'strecke'`, mit eigener Fassungsnummer
`_STRECKE_STAND_FASSUNG`.

## 6. Rechnung

Neues Modul `app/strecke.py` (reine Funktionen, kein Datenbankzugriff), nach dem Vorbild von
`app/reddung.py`: Vorgaben, Ziele aus der Strecke, Fenster, Geometrie der Abschnitte für die Karte.

**Erweiterung von `app/abdeckung.py`:** `abdeckung()` kennt bisher eine Höhengrenze für den ganzen
Lauf. Sie bekommt einen wahlfreien Parameter `hoehe_je_ziel` (Schlüssel → Höchsthöhe in ft über
Meer). Ist er gesetzt, wird ein Segment nur dann für ein Ziel gewertet, wenn **beide** Endpunkte
unter der Grenze dieses Ziels liegen; die allgemeine Grenze des Fensters dient dann nur noch als
grober Vorfilter (der höchste Wert aller Ziele). Ohne den Parameter bleibt alles wie bisher, die
Reddung ist nicht berührt.

Die Höchsthöhe eines Abschnitts ist `grund_ft[abschnitt] + hoehe_max_ft`, ungerundet. (Die Reddung
rundet auf 500 ft, um die Geländehöhe am Wrack nicht zu verraten. Hier gibt es nichts zu verbergen.)

**Fortschreiben statt neu rechnen**, wie `reddung_fortschreiben`: Je Takt kommen nur die neuen
Punkte dazu, geprüft werden nur noch offene Abschnitte. Der Stand trägt je Abschnitt den ersten
Piloten und den Zeitpunkt, dazu die Summe je Pilot.

## 7. Positionen

- **Quelle sind die Sekundenpunkte der Brügge** (`bruegge_spur`). Die Wache in
  `bruegge_spur_schreiben` schreibt heute nur im Sektor einer laufenden Reddung; sie wird um den
  Umkreis laufender Strecken erweitert (umschließendes Rechteck der Strecke plus Rand). Damit greift
  auch die vorhandene Ausnahme, dass die Brügge dort trotz meldendem Kniebrett im Regeltakt fragt.
- **VATSIM als Lückenfüller** über die vorhandene Mischfunktion der Reddung, die dafür aus dem
  Reddung-Namen gelöst und von beiden Eventtypen benutzt wird (A6).
- `bruegge_spur` wird nach 12 Stunden aufgeräumt. Der fortgeschriebene Stand überlebt das; ein
  Neuberechnen nach dem Ende fände nur noch VATSIM vor. **Deshalb verwirft das Speichern in der
  Verwaltung den Stand nur, wenn sich ein Rechenwert ändert** (Punkte, Korridor, Höhe,
  Geschwindigkeit, Zeiten), nicht beim Umbenennen. Dieselbe Falle ist bei der Reddung seit 15.25.0 zu.

## 8. Geländehöhen

- Abruf beim Speichern über die vorhandene Abfrage an das Höhenmodell (`_gelaende_ft`, Open-Meteo),
  erweitert auf mehrere Punkte je Anfrage. **Gemessen am 10.10.2026 vom Container:** 100 Koordinaten
  je Anfrage gehen, 101 werden mit 400 abgelehnt. Geholt wird also in Blöcken zu 100, für den
  Mittelpunkt jedes Abschnitts.
- **Kein Netzabruf innerhalb einer Datenbank-Transaktion** (stehende Regel): erst holen, dann mit
  frischer Verbindung schreiben.
- Scheitert der Abruf, wird das Event trotzdem gespeichert, `grund_json` bleibt leer, und es gilt A7.
  Die Verwaltung zeigt einen Hinweis und einen Knopf „Geländehöhen holen“.
- **Bekannte Grenze:** Das Höhenmodell ist gröber als der Simulator und glättet schmale Grate; ein
  Kamm steht dort eher etwas zu niedrig. In der Eifel lagen Modell und Simulator 0,3 ft auseinander.

## 9. Poller

Ein Takt `_check_strecke` nach dem Muster von `_check_reddung`: laufende Events fortschreiben, bei
Änderung den Stand über den Sekundenstrom an die offenen Karten melden. Nach `dtend` wird einmal
abgeschlossen und nicht mehr gerechnet.

## 10. Schnittstellen

| Weg | Zweck |
|---|---|
| `GET /api/strecke/events` | Liste mit Zeiten, Vorgaben und Kurzstand, hinter derselben Schranke wie die übrigen Events |
| `GET /api/strecke/events/{id}/stand` | Geometrie der Abschnitte, je Abschnitt Zustand, Pilot und Zeit, Summen je Pilot |
| `GET/POST /api/admin/strecke/events`, `POST …/{id}`, `DELETE …/{id}` | Verwaltung; **Löschen verlangt das Passwort erneut** (ganzer Eintrag) |
| `POST /api/admin/strecke/events/{id}/grund` | Geländehöhen neu holen |

Rufzeichen und Namen in den Antworten folgen den Sichtbarkeitsregeln der Reddung.

## 11. Verwaltung

Ein eigener Block wie bei der Reddung: Liste der Events, Formular mit Name, Zeiten und den vier
Vorgaben. **Die Karte zum Klicken:** jeder Klick hängt einen Punkt an, Punkte lassen sich ziehen und
einzeln entfernen, „letzten Punkt zurück“ und „Strecke leeren“. Die Vorschau zeigt sofort Länge,
Zahl der Abschnitte und den Korridor als Band, damit man die Wirkung der Breite vor dem Speichern
sieht.

## 12. Ansicht für Mitglieder

Nach dem abgestimmten Entwurf (`files.devprops.de/deichkontrolle-karte.html`, Wegwerf-Seite):

- **Live-Karte:** offene Abschnitte blass und gestrichelt, abgeflogene kräftig; darunter der Korridor
  als blasses Band in echter Breite. Gezeichnet als SVG und in wenigen Pfaden (ein Pfad für alles
  Offene, einer je Farbe), weil die Karte mit `leaflet-rotate` läuft und der Canvas-Renderer dort
  nicht trägt.
- **Eventansicht:** Balken mit „x von y km · z %“, die Vorgabe als Satz („höchstens 500 m neben der
  Strecke und höchstens 1.000 ft darüber, 30 bis 140 kt“), die Liste der Piloten mit ihren
  Kilometern, der **Umschalter** für die Farbe. Ein Tipp auf die Strecke nennt Abschnitt, Pilot und
  Uhrzeit.
- **Farbe je Pilot:** feste Palette, vergeben in der Reihenfolge des ersten Treffers. Die Wahl des
  Umschalters merkt sich der Browser; im Kniebrett, das nichts speichern kann, gilt die Vorgabe „eine
  Farbe“.
- **Die Brügge-Pflicht steht in der Eventansicht**, mit dem Verweis auf die Download-Seite.
- **Scrollregel:** Der neue Typ kommt in die Bedingung von `renderEventsResults()`, damit ein
  geöffnetes Event bei seiner Ansicht steht und nicht bei den Flugspuren darunter.
- Geprüft bei Handy (390), iPad quer und Monitor (1668).

## 13. Tests

- `abdeckung`: Höhe je Ziel (zählt nur unter der Grenze des Abschnitts; ohne Parameter unverändert).
- `strecke`: Teilung der Strecke, Geometrie der Abschnitte, Grenzen (zu wenige Punkte, zu viele
  Abschnitte).
- Fortschreiben: erster Abdecker bleibt, späterer Überflug ändert nichts; Stand überlebt das
  Aufräumen der Sekundenspur; Umbenennen verwirft ihn nicht, eine Änderung der Strecke schon.
- Teilnahme: ohne Brügge-Meldung seit Eventbeginn keine Wertung; mit ihr füllt VATSIM Lücken.
- Geländehöhen: Blöcke zu 100, Fehlschlag lässt das Event bestehen und die Rechnung ruhen.
- Endpunkte und Verwaltung: Anlegen, Ändern, Löschen mit Passwort.
- Quelltext-Tests für Scrollregel und Takt, an Namen im Code verankert.
- Jeder neue Test wird gegen den entfernten Code gegengeprüft.

## 14. Doku

README-Absatz und Hilfetext hinter dem „?“ im selben Commit wie die Ansicht; `docs/api.md`,
`docs/architecture.md`, `CLAUDE.md` (Tabelle „Stellt etwas in den Simulator?“ bekommt die Zeile:
nein, aber Brügge Pflicht wegen der Positionen) und `docs/offene-aufgaben.md`.

## 15. Vor der Freigabe zu klären

1. **Name und Zeichen** des Eventtyps für Mitglieder. Arbeitsname ist „Deichkontrolle“ mit 🌊.
2. **Versionsnummer.** Die Ansicht ist eine sichtbare Neuerung außerhalb der Verwaltung; nach der
   stehenden Regel wird der Schritt zur Hauptnummer vorher abgesprochen.
3. **Zeitpunkt des Ausrollens**, nicht zu Flugzeiten.
