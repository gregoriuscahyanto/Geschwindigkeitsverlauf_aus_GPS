# Qt-Routenauswahl mit Online-OSM und Offline-Fallback

Die Anwendung ersetzt den manuellen Weg über die GraphHopper-Webseite und eine heruntergeladene GPX-Datei. Routing und OSM-Auswertung laufen lokal in Python. Für die Kartenanzeige wird standardmäßig die Online-Karte von OpenStreetMap verwendet; wenn sie nicht erreichbar ist, schaltet der Modus **Automatisch** auf die lokale Vektorkarte um.

## Funktionsumfang

- native Oberfläche mit PySide6/QML
- Online-OSM als schnelle Standardkarte, ohne API-Key
- automatischer Fallback auf die vollständig lokale Vektorkarte
- manuelle Auswahl zwischen `Automatisch`, `Online OSM` und `Komplett offline`
- Start, beliebig viele Zwischenziele und Ziel per Mausklick
- lokale Routenberechnung ohne GraphHopper-, OSRM- oder Valhalla-Server
- drei Routingprofile:
  - **Hauptstraßen bevorzugen**: Autobahn, Bundesstraße, Landstraße, regionale Straße, Seitenstraße
  - **Schnellste Route**: reine OSM-Fahrzeit
  - **Kürzeste Route**: reine Entfernung
- Berücksichtigung von Einbahnstraßen, Kreisverkehren und einfachen Zufahrtsregeln
- Anzeige von Route und gefundenen Ampeln
- Export als `selected_region.json` und `route_result.json`
- wiederverwendbarer Graph-Cache für erneute Routen in derselben Region

## Installation

Aus dem Repository-Stammverzeichnis unter Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r qt_route_selector\requirements.txt
```

Nach einem Git-Update muss die virtuelle Umgebung nicht neu erstellt werden. Es reicht:

```powershell
.\.venv\Scripts\python.exe -m pip install -r qt_route_selector\requirements.txt
```

## Anwendung starten

```powershell
.\.venv\Scripts\python.exe qt_route_selector\main.py
```

## Bedienung

1. Die Online-OSM-Karte erscheint standardmäßig sofort.
2. Startpunkt anklicken.
3. Weitere Punkte in Fahrreihenfolge anklicken. Der erste Punkt ist der Start, der letzte Punkt das Ziel, alle Punkte dazwischen sind Zwischenziele.
4. Über **Straßendaten wählen** eine lokale `.osm.pbf`, `.gpkg`, `.fgb`, `.geojson` oder `.shp` auswählen.
5. Routingprofil auswählen.
6. **Route berechnen** anklicken.

Mit **Letzten Punkt entfernen** lässt sich die Klickfolge korrigieren.

## Warum das direkte PBF-Lesen langsam ist

Eine OSM-PBF ist kompakt und ideal als Austauschformat. Sie besitzt aber keinen räumlichen Index für schnelle beliebige Kartenausschnitte. Beim direkten Lesen kann GDAL deshalb große Teile der Datei sequenziell durchsuchen. Das betrifft sowohl die lokale Kartenanzeige als auch den ersten Aufbau des Routinggraphen.

Die Online-Hintergrundkarte ist davon nicht betroffen. Verschieben und Zoomen funktionieren dort unabhängig von der PBF schnell.

## Empfohlen: PBF-Schnellindex

Nach Auswahl einer PBF erscheint die Schaltfläche **PBF-Schnellindex erstellen**. Sie erzeugt einmalig neben der PBF eine Datei wie:

```text
baden-wuerttemberg-260805_routing.gpkg
```

Die Konvertierung verwendet Pyosmium und liest die PBF nur einmal. Das GeoPackage enthält:

- befahrbare Straßen mit relevanten OSM-Tags
- räumlichen Index
- Ampeln in einer separaten Ebene

Nach Abschluss aktiviert die Anwendung das GeoPackage automatisch. Weitere Karten- und Routingabfragen sind dann wesentlich schneller. Wird später dieselbe PBF erneut gewählt und ein aktueller Schnellindex liegt daneben, verwendet die Anwendung ihn automatisch.

## Kartenmodi

### Automatisch

Die Anwendung startet mit Online-OSM. Ein kurzer Verbindungstest und Qt-Kartenfehler führen bei Nichterreichbarkeit zum Offline-Fallback. Die Erreichbarkeit wird in größeren Abständen erneut geprüft.

### Online OSM

Erzwingt die Online-Karte. Das lokale Routing verwendet weiterhin ausschließlich deine lokale Straßendatei.

### Komplett offline

Verwendet den nativen Qt-Vektorrenderer. Bei GeoPackage/FGB wird der sichtbare Ausschnitt nach einer kurzen Pause automatisch nachgeladen. Kleine Kartenbewegungen verwenden einen vergrößerten In-Memory-Cache. Bei einer direkten PBF ist automatisches Nachladen deaktiviert, damit nicht nach jeder Bewegung ein langer PBF-Scan beginnt; hier sollte der Schnellindex erstellt werden.

## Straßenpriorisierung

Das Standardprofil **Hauptstraßen bevorzugen** verwendet eine moderate Gewichtung. Die Rangfolge lautet:

1. Autobahn (`motorway`, Referenz `A`)
2. Bundesstraße (Referenz `B`, typischerweise `trunk`/`primary`)
3. Landstraße (Referenz `L`)
4. Kreis- und regionale Straßen (`K`, `secondary`, `tertiary`)
5. unklassifizierte und Wohnstraßen
6. verkehrsberuhigte Bereiche und Servicewege

Die Gewichtung bevorzugt Hauptstraßen, erzwingt aber keine extremen Umwege. Für eine rein zeitbasierte Entscheidung kann auf **Schnellste Route** gewechselt werden.

## Ausgabedateien

### `selected_region.json`

Enthält alle gewählten GPS-Punkte, die gepufferte Arbeitsregion und die gewählte Straßendatei.

### `route_result.json`

Enthält:

- Routengeometrie als GPS-Koordinaten
- Teilstrecken zwischen den gewählten Punkten
- Segmentlängen und vorläufige Fahrzeiten
- `maxspeed_kmh`
- `highway`, Straßenkategorie und Prioritätsfaktor
- `surface`, Straßenname, Referenz und Einbahnstraßeninformation
- Ampelpositionen und deren Entfernung vom Routenstart
- Routingprofil und Graph-Cache-Status

Diese Daten können direkt in das Fahrer-, Kurven- und Geschwindigkeitsmodell übernommen werden.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s qt_route_selector\tests -v
```

## Grenzen des aktuellen Routers

Der Router ist ein nachvollziehbarer Forschungs- und Simulationsbaustein, kein vollständiges Navigationssystem. Noch nicht ausgewertet werden unter anderem:

- OSM-Abbiegebeschränkungen aus Relationen
- zeitabhängige Zufahrtsregeln
- Fahrzeughöhe, Gewicht und Gefahrgutregeln
- detaillierte Kreuzungs- und Abbiegekosten
- Fahrspuren und Spurwechsel

Die lokale Fallback-Karte zeichnet derzeit Straßen, Route, Punkte und Ampeln, aber noch keine vollständige kartografische Basiskarte mit Gebäuden, Gewässern und Landnutzung.
