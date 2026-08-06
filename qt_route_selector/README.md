# Qt-Routenplaner und Live-Geschwindigkeitsverlauf

Die Anwendung ersetzt den manuellen Weg über die GraphHopper-Webseite und eine heruntergeladene GPX-Datei. Routing und OSM-Auswertung laufen lokal in Python. Für die Kartenanzeige wird standardmäßig die Online-Karte von OpenStreetMap verwendet; wenn sie nicht erreichbar ist, schaltet der Modus **Automatisch** auf die lokale Vektorkarte um.

Zusätzlich berechnet ein zweites Qt-Fenster den Geschwindigkeitsverlauf live. Änderungen an Fahrer, Kurvenmodell, Ampeln, Überholvorgängen oder Fahrerrauschen werden nach kurzer Verzögerung neu berechnet und sofort geplottet.

## Funktionsumfang

- native Routenoberfläche mit PySide6/QML
- Online-OSM als schnelle Standardkarte, ohne API-Key
- automatischer Fallback auf die vollständig lokale Vektorkarte
- Start, beliebig viele Zwischenziele und Ziel per Mausklick
- lokale Routenberechnung ohne GraphHopper-, OSRM- oder Valhalla-Server
- Hauptstraßen-, schnellstes- und kürzestes Routingprofil
- Berücksichtigung von Einbahnstraßen, Kreisverkehren und einfachen Zufahrtsregeln
- Live-Fahrerprofile `Normalo`, `Rennfahrer`, `Handwerker`, `Rentner` und `Rentner + Anhänger`
- live einstellbarer Geschwindigkeitsverlauf mit Straßenlimit, Kurvenlimit und Straßenbelag
- frei wählbare Anzahl von Ampelstopps und Überholvorgängen
- einstellbare Beschleunigung, Verzögerung, Ruck, Temperament und Fahrerrauschen
- Plots über Strecke, Zeit und Längsbeschleunigung
- CSV- und JSON-Export der Simulation

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

## Empfohlener Start: Karte und Live-Simulation gemeinsam

```powershell
.\.venv\Scripts\python.exe qt_route_selector\complete_app.py
```

Dabei öffnen sich zwei Fenster:

1. der Routenplaner mit Karte,
2. der Live-Geschwindigkeitsverlauf mit Einstellungen und Diagrammen.

Nach jeder erfolgreich berechneten Route wird `route_result.json` automatisch in das Simulationsfenster übernommen.

Nur den Routenplaner starten:

```powershell
.\.venv\Scripts\python.exe qt_route_selector\main.py
```

Nur die Live-Simulation starten:

```powershell
.\.venv\Scripts\python.exe qt_route_selector\live_speed_profile.py
```

Das Simulationsfenster überwacht `route_result.json` und lädt Änderungen automatisch nach.

## Bedienung des Routenplaners

1. Die Online-OSM-Karte erscheint standardmäßig sofort.
2. Startpunkt anklicken.
3. Weitere Punkte in Fahrreihenfolge anklicken. Der erste Punkt ist der Start, der letzte Punkt das Ziel, alle Punkte dazwischen sind Zwischenziele.
4. Über **Straßendaten wählen** eine lokale `.osm.pbf`, `.gpkg`, `.fgb`, `.geojson` oder `.shp` auswählen.
5. Routingprofil auswählen.
6. **Route berechnen** anklicken.

Mit **Letzten Punkt entfernen** lässt sich die Klickfolge korrigieren.

## Live-Geschwindigkeitsverlauf

Der erste Referenzverlauf wird aus `maxspeed_kmh` aufgebaut. Darauf werden die weiteren Grenzen und Ereignisse gelegt:

```text
OSM-Straßenlimit
    ↓
Reisegeschwindigkeit und Fahrerobergrenze
    ↓
Straßenbelag
    ↓
Kurvenlimit aus Radius und Querbeschleunigung
    ↓
Ampel- und Überholereignisse
    ↓
Fahrerrauschen
    ↓
Beschleunigungs-, Brems- und Ruckbegrenzung
    ↓
v(s), v(t) und a(t)
```

### Fahrer

Die Fahrer-Presets stammen aus den bisherigen festen Parametern in `runPipeline.m`. Nach Auswahl eines Presets können alle Werte individuell verändert werden:

- Temperament
- Reisegeschwindigkeit und absolute Obergrenze
- Geschwindigkeits-Bias und Toleranz
- Reglerverstärkung `Kp`
- maximale Beschleunigung
- maximale Verzögerung
- maximaler Ruck
- Anhalten an Start und Ziel

### Kurven

Die Route wird auf einen regelmäßigen Abstand resampelt. Aus drei räumlich getrennten Punkten wird ein lokaler Kurvenradius geschätzt. Die Kurvengrenze wird aus Radius und maximaler Querbeschleunigung gebildet. Einstellbar sind:

- Kurvenmodell ein/aus
- maximale Querbeschleunigung
- minimaler und maximaler Radius
- Abtastabstand
- räumliche Glättung
- geplante Verzögerung vor einer Kurve
- Berücksichtigung des Straßenbelags

### Ampeln

**Anzahl Stopps** gibt die gewünschte Anzahl von Ampelvorgängen an. Zuerst werden erkannte OSM-Ampeln verwendet. Ist die gewünschte Zahl größer, ergänzt das Modell reproduzierbare synthetische Stopppositionen. Einstellbar sind außerdem:

- Rotphase minimal und maximal
- geplante Verzögerung
- Stopptoleranz
- Zufalls-Seed

### Überholen

Überholvorgänge bestehen aus einer Folgephase hinter einem langsameren Fahrzeug und einer anschließenden Überholphase. Einstellbar sind:

- Anzahl der Vorgänge
- Geschwindigkeit des langsamen Fahrzeugs
- Intensität beziehungsweise gewünschter Geschwindigkeits-Boost
- Länge der Folgephase
- Länge der Überholphase

Die Geschwindigkeit bleibt durch Straßen-, Kurven- und Fahrerobergrenzen begrenzt.

### Fahrerrauschen

Das Rauschen ist zeitlich korreliert und nicht von Punkt zu Punkt unabhängig. Einstellbar sind:

- Standardabweichung in km/h
- Zeitkonstante
- Zufalls-Seed

Mit demselben Seed entsteht bei gleichen Parametern derselbe Verlauf.

### Fahrzeug und Anhänger

Das Massenmodell begrenzt die verfügbare Beschleunigung und Bremsung anhand von Fahrzeugmasse, Anhängermasse, Rollwiderstand sowie maximaler Antriebs- und Bremskraft. Das aktuelle Routing besitzt noch kein Höhenprofil; Steigung und Gefälle werden deshalb noch nicht berücksichtigt.

## Diagramme und Export

Das Live-Fenster zeigt:

- `v(s)`: Straßenlimit, Kurvenlimit, Basis-Sollwert, geplante und simulierte Geschwindigkeit
- `v(t)`: Soll- und Istgeschwindigkeit mit markierten Rotphasen
- `a(t)`: Längsbeschleunigung

Über **CSV + JSON exportieren** entstehen:

```text
speed_profile_result.csv
speed_profile_result.json
```

Die CSV enthält Zeit, Strecke, Geschwindigkeit, Sollgeschwindigkeit und Beschleunigung. Die JSON-Datei enthält zusätzlich alle Parameter, räumlichen Profile und Ereignisse.

## Warum das direkte PBF-Lesen langsam ist

Eine OSM-PBF ist kompakt und ideal als Austauschformat. Sie besitzt aber keinen räumlichen Index für schnelle beliebige Kartenausschnitte. Beim direkten Lesen kann GDAL deshalb große Teile der Datei sequenziell durchsuchen. Das betrifft sowohl die lokale Kartenanzeige als auch den ersten Aufbau des Routinggraphen.

Die Online-Hintergrundkarte ist davon nicht betroffen. Verschieben und Zoomen funktionieren dort unabhängig von der PBF schnell.

## Empfohlen: PBF-Schnellindex

Nach Auswahl einer PBF erscheint die Schaltfläche **PBF-Schnellindex erstellen**. Sie erzeugt einmalig neben der PBF eine Datei wie:

```text
baden-wuerttemberg-260805_routing.gpkg
```

Das GeoPackage enthält befahrbare Straßen, relevante OSM-Tags, einen räumlichen Index und Ampeln in einer separaten Ebene. Nach Abschluss aktiviert die Anwendung das GeoPackage automatisch.

## Kartenmodi

- **Automatisch:** Online-OSM mit automatischem Offline-Fallback.
- **Online OSM:** Erzwingt die Online-Karte; das Routing bleibt lokal.
- **Komplett offline:** Verwendet den nativen Qt-Vektorrenderer.

## Straßenpriorisierung

Das Standardprofil **Hauptstraßen bevorzugen** verwendet eine moderate Gewichtung:

1. Autobahn (`motorway`, Referenz `A`)
2. Bundesstraße (Referenz `B`)
3. Landstraße (Referenz `L`)
4. Kreis- und regionale Straßen
5. unklassifizierte und Wohnstraßen
6. verkehrsberuhigte Bereiche und Servicewege

## Ausgabedateien des Routings

### `selected_region.json`

Enthält alle gewählten GPS-Punkte, die gepufferte Arbeitsregion und die gewählte Straßendatei.

### `route_result.json`

Enthält Routengeometrie, Teilstrecken, Segmentlängen, `maxspeed_kmh`, Straßenklasse, Straßenbelag, Ampelpositionen sowie Routing- und Cacheinformationen. Diese Datei ist der Eingang für die Live-Simulation.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s qt_route_selector\tests -v
```

## Grenzen

Der Router und Simulator sind nachvollziehbare Forschungsbausteine, keine vollständige Serien-Navigation oder validierte Fahrdynamiksimulation. Noch nicht berücksichtigt werden unter anderem OSM-Abbiegebeschränkungen, zeitabhängige Regeln, Fahrspuren, Verkehrsdichte und ein digitales Höhenmodell. Die Simulationsparameter sollten anhand realer Messfahrten kalibriert werden.
