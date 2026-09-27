# Messeverkehr – Design

Stand: 27.09.2026, aus einem Gespräch mit dem Nutzer über den FriesenFlieger-Imagefilm/-Messeauftritt
(FS Conference, 21.11.2026, Paderborn/Lippstadt) entstanden.

## Ziel

Auf der echten Live-Karte (`friesenspy.devprops.de`) soll für ausgewählte Betrachter **immer**
Friesen-Verkehr zu sehen sein, auch wenn gerade real niemand fliegt – für den Messestand, damit die
Karte nie leer wirkt. Der simulierte Verkehr soll dort **genauso aussehen wie echter**, sowohl in der
Live-Ansicht (Liste) als auch auf der Karte – keine sichtbare "DEMO"-Kennzeichnung im Frontend.

## Entscheidungen aus dem Gespräch

1. **Kein separates Demo-System.** Der simulierte Verkehr erscheint auf derselben Live-Karte wie
   echter Verkehr, nicht auf einer getrennten Seite.
2. **Visuell nicht unterscheidbar.** Wer ihn sehen darf, sieht ihn wie einen echten Flug – gleiches
   Symbol, gleiche Liste, keine Kennzeichnung im ausgelieferten JSON oder in der Oberfläche.
3. **Nur für eine neue, eigene Berechtigungsgruppe sichtbar**, unabhängig von der bestehenden
   `is_admin`-Rolle (Forum-Gruppe "Events"). Umsetzung als eigene CID-Allowlist
   (`messeverkehr_erlaubt`), nicht als neue Forum-Gruppe – das Board selbst muss dafür nicht
   angefasst werden.
4. **Datenintegrität hat Vorrang.** Simulierte Flüge dürfen niemals in `live_positions`,
   `flights`, `position_history`, `statsim_*` oder eine Event-Wertung (Bummel/Kutter/Reddung)
   einfließen. Eigene Tabelle, eigener CID-Wertebereich (negativ), eigene Generator-Logik.
5. **Server-seitige Sichtbarkeitsprüfung**, nicht clientseitig: Wer nicht auf der Allowlist steht,
   bekommt die simulierten Flüge serverseitig gar nicht erst ausgeliefert – weder über `/api/live`
   noch über den SSE-Strom `/api/sse`. Das Frontend selbst braucht keine Änderung, weil es dieselbe
   Datenform bekommt, die es für echten Verkehr schon rendert.
6. **Feature-Flag als Not-Aus.** Ein `app_settings`-Schalter (`messeverkehr_enabled`) schaltet die
   Erzeugung komplett ab, Vorgabe aus. Wird gezielt für den Messetag aktiviert.

## Warum keine sichtbare Kennzeichnung

Erstentwurf sah ein eigenes Kartensymbol vor ("Demo"-Marker). Nutzerkorrektur: Der simulierte
Verkehr soll am Stand echt wirken – die Trennung bleibt vollständig serverseitig (eigene Tabelle,
eigener CID-Bereich, Ausschluss aus Auswertungen), nicht optisch.

## Architektur

- **Neue Tabelle `messeverkehr_flights`**: Momentaufnahme der simulierten Flüge, gleiche fachliche
  Felder wie `live_positions` (Callsign, Position, Höhe, Geschwindigkeit, Kurs, Abflug/Ziel,
  Pilotenname). CIDs strikt negativ (`cid < 0`), damit sie mit keiner echten VATSIM-CID kollidieren
  können und sich mechanisch aus jeder Stelle ausschließen lassen, die `cid > 0` voraussetzt.
- **Neue Tabelle `messeverkehr_erlaubt`**: CID-Allowlist der Betrachter, die den simulierten Verkehr
  sehen dürfen (echte, eingeloggte CIDs – die Berechtigten selbst, nicht die simulierten Piloten).
- **Neues Modul `app/messeverkehr.py`**: reine Generator-Logik (Route wählen, Fortschritt
  fortschreiben, neuen Flug erzeugen, abgeschlossenen Flug entfernen). Kein Netz, keine
  FastAPI-Abhängigkeit – leicht zu testen, analog zu `app/geo.py`.
- **Poller-Integration** (`app/poller.py`, dieselbe Stelle wie `get_live_positions()` vor
  `broadcast_sse`): Ist das Feature an, wird `advance_messeverkehr()` aufgerufen und das Ergebnis
  den ausgehenden `positions`-Daten beigemischt, mit einem internen Merkmal (`_messeverkehr: True`)
  markiert. Dieses Merkmal verlässt den Server nie – es wird vor jedem Ausliefern entfernt.
- **Sichtbarkeitsfilter an genau zwei Stellen** (dort, wo `positions`-Daten den Server verlassen):
  - `GET /api/live` (Erstladung)
  - `_event_generator` im SSE-Strom `/api/sse` (laufende Updates) – dort gibt es mit dem
    `fremd`-Ausblenden für `kb=1` bereits ein Vorbild für "pro Verbindung etwas aus derselben
    Broadcast-Nachricht herausfiltern".
  Beide Stellen: `cid_hat_messeverkehr_erlaubnis(conn, viewer_cid)` einmal ermitteln (nicht pro
  Nachricht neu), dann `_messeverkehr`-Einträge für nicht Berechtigte verwerfen, für Berechtigte
  das interne Merkmal aus dem JSON entfernen, bevor es rausgeht.
- **Admin-API** zum Pflegen der Allowlist und zum Umschalten des Feature-Flags – wie bestehende
  Admin-Endpunkte über `require_admin`. Eine eigene Admin-Oberfläche (`admin.html`-Abschnitt) ist
  **nicht** Teil dieses Plans; die Endpunkte sind vorerst nur über `curl`/HTTP-Client bedienbar.

## Nicht im Umfang

- Keine Admin-UI (nur API).
- Keine Steuerung "wie viele Flüge gleichzeitig" über die UI – ein fester Wert im Modul.
- Keine realistische Wetter-/Verkehrslage-Simulation – nur plausible Punkt-zu-Punkt-Flüge zwischen
  einer festen Liste norddeutscher Flugplätze.
