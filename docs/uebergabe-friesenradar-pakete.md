# Übergabe an die Sitzung auf dem Simulator-Rechner — Pakete für FriesenRadar

Die App heißt seit 16.0.0 **FriesenRadar** (CLAUDE.md, Abschnitt „Name“). Zwei Pakete müssen
neu gebaut werden: das **Kniebrett 3.0.0** und die **FriesenBrügge** (MSFS 1.19.0, X-Plane
1.5.0). Der Code liegt fertig auf dem Branch **`bruegge-radar`** (enthält auch das Kniebrett);
gebaut wird nur unter Windows.

**Reihenfolge:** Erst wenn der Server-Umzug durch ist (`/opt/friesenradar`), werden Pakete
hochgeladen — die Paketskripte zielen bereits auf den neuen Pfad. Bauen und im Simulator
prüfen geht vorher.

---

## 1. Kniebrett 3.0.0 — neuer Ordner (Variante B, Nutzer 03.10.2026)

Was sich ändert: Paketordner `friesenflieger-friesenradar-efb`, Quellordner
`msfs-panel/PackageSources/FriesenRadar/`, App-Klasse `FriesenRadar`, `efb_apps/FriesenRadar`,
Adresse `friesenradar.devprops.de`, Titel und Symbol. **Die Gerätekennung bleibt
`friesenspy_device`** — daran hängt die Anmeldung jedes Tablets.

Neu in der App: Sie prüft beim Handshake, ob das alte Paket (Klasse `FriesenSpy`) noch
daneben liegt, und meldet `altesPaket: true`. Die Seite zeigt dann einen Kasten, der sich nicht
wegklicken lässt.

### Bauen

```powershell
cd <repo>\msfs-panel\PackageSources\FriesenRadar
npm ci                      # der Ordner ist neu -- node_modules lag unter FriesenSpy\
npm run build
cd ..\..
.\build-package.ps1         # baut msfs-panel\Package\
```

Danach `Package` in **`friesenflieger-friesenradar-efb`** umbenennen und so packen wie bisher
`friesenspy-efb.zip` — nur mit diesem Ordnernamen als oberster Ebene. Name der Datei:
**`friesenradar-efb.zip`**. Gegenprobe (Python):

```python
import zipfile; n = zipfile.ZipFile("friesenradar-efb.zip").namelist()
assert all(x.startswith("friesenflieger-friesenradar-efb/") for x in n), n[:3]
assert "friesenflieger-friesenradar-efb/manifest.json" in n
assert any("efb_apps/FriesenRadar/FriesenRadar.js" in x for x in n)
```

Der Server nennt den Download nach diesem Ordner (`_efb_download_name`). Stimmt der Ordner
nicht, entsteht beim Entpacken ein falsch benannter Ordner.

### Prüfen im Simulator — HARTE SCHRANKE vor dem Hochladen

Ob die Gerätebindung einen neuen Paketordner übersteht, ist **nicht belegt**
(`SetStoredData` paketübergreifend?). Deshalb:

1. **Vorher:** die eigene Gerätekennung notieren — die Server-Sitzung liest sie aus
   `panel_devices` (Paket 2.3.2, letzter Kontakt).
2. **Nur das neue Paket:** alten Ordner `friesenflieger-friesenspy-efb` aus `Community`
   entfernen (nicht löschen, beiseitelegen), neuen hineinlegen, Simulator starten, Tablet
   öffnen.
   - Erwartet: **keine** neue Anmeldung, und im nginx-Log steht
     `/auth/device?device=<DIESELBE Kennung>&…&paket=3.0.0`.
   - **Kommt eine neue Kennung oder fragt das Tablet nach der Anmeldung: STOPP.** Nicht
     hochladen, der Server-Sitzung melden. Dann ist die Bindung paketgebunden, und Variante B
     braucht eine neue Entscheidung des Nutzers.
3. **Beide Pakete:** alten Ordner wieder dazulegen, Simulator neu starten.
   - Erwartet: zwei Apps im Tablet; in **FriesenRadar** steht unten links der Kasten „Das
     alte Kniebrett-Paket liegt noch im Community-Ordner …“, ohne Schließen-Knopf.
   - Danach den alten Ordner endgültig entfernen.
4. **Aussehen:** Name „FriesenRadar“ in der App-Liste, Symbol rotes Flugzeug auf Weiß, Seite
   mit Logo im Streifen, hell und dunkel, Fenster lassen sich schließen.
5. **App neu anheften** — die alte Anheftung gilt nicht für die neue Klasse.

Erst nach 1–4 hochladen: `friesenradar-efb.zip` nach `/opt/friesenradar/data/efb/`. Das
macht die Server-Sitzung auf Wort des Nutzers. Danach dort: `curl -sI` auf `/download/efb`
zeigt `friesenflieger-friesenradar-efb.zip`.

Erst dann prüfbar: Die **alte** App (2.x) zeigt im Hinweis unten links „… Danach den alten
Ordner friesenflieger-friesenspy-efb im Community-Ordner löschen.“

---

## 2. FriesenBrügge — neue Adresse

MSFS **1.19.0**, X-Plane **1.5.0**. Geändert sind nur Zieladresse
(`friesenradar.devprops.de`), Texte und Versionsnummer. Die Kennungsdatei (`\work\` bzw.
`Output/preferences/`) bleibt — die Zuordnung zum Piloten überlebt das Update.

Bauen wie gehabt (`friesenbruegge\msfs\bauen.ps1`, mit `-Fuer2020` für 2020;
`friesenbruegge\xplane\bauen.ps1`), packen mit `paket.ps1`.

Prüfen:
- Log-Zeile `Fassung 1.19.0 startet` (MSFS) bzw. `Fassung 1.5.0 geladen.` und
  `Ziel: friesenradar.devprops.de` (X-Plane).
- Die Server-Sitzung prüft **in der Datenbank**, nicht im nginx-Log (erfolgreiche Meldungen
  werden dort absichtlich nicht protokolliert):
  `SELECT bruegge_version, gesehen_am FROM bruegge_zuordnung ORDER BY gesehen_am DESC LIMIT 5`.

**Möglichst vor dem 24.10.2026 ausliefern:** Ab dann lehnt der Server alte MSFS-Brüggen ab
(`_BRUEGGE_P2_MSFS_BIS`). Kommt die neue vorher, aktualisieren die Piloten einmal statt zweimal.

---

## Was NICHT zu tun ist

- Nichts nach `Community2024` legen (CLAUDE.md, Kniebrett-Standards).
- `DEVICE_KEY` nicht ändern — auch nicht „passend zum neuen Namen“.
- Nicht selbst hochladen; das macht die Server-Sitzung auf Wort des Nutzers.
