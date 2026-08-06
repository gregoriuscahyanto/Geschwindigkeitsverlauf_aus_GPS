# Qt-Routenplaner und Live-Geschwindigkeitsverlauf

Die Anwendung berechnet eine Route aus lokalen OSM-Daten und erzeugt daraus einen einstellbaren Geschwindigkeitsverlauf. Karte, Routing und Simulation befinden sich in **einem Fenster mit zwei Tabs**.

## Start

```powershell
.\.venv\Scripts\python.exe -m pip install -r qt_route_selector\requirements.txt
.\.venv\Scripts\python.exe qt_route_selector\complete_app.py
```

## Tab 1: Route und Karte

- Online-OSM als Standardkarte
- automatischer Offline-Fallback
- lokale `.osm.pbf`, `.gpkg`, `.fgb`, `.geojson` oder `.shp` als Routingquelle
- Start, beliebig viele Zwischenziele und Ziel per Klick
- Routingprofile für Hauptstraßen, schnellste oder kürzeste Route
- PBF-Schnellindex für wiederholte, schnelle lokale Abfragen

Nach **Route berechnen** wird `route_result.json` geschrieben und automatisch an den zweiten Tab übergeben.

## Tab 2: Geschwindigkeitsverlauf

Die Simulation wird nach einer Parameteränderung mit kurzer Verzögerung neu berechnet. Einstellbar sind unter anderem:

- Fahrer-Preset und Temperament
- Reisegeschwindigkeit, Fahrerobergrenze und Bias
- Beschleunigung, Verzögerung, Ruck und Reglerverstärkung
- Kurvenverhalten und maximale Querbeschleunigung
- Straßenbelag
- Ampelstopps und Rotphasen
- Überholvorgänge
- Fahrerrauschen
- Fahrzeug- und Anhängermasse

### Synchronisierter Hover-Cursor

Beim Bewegen der Maus über das Zeitdiagramm werden gleichzeitig angezeigt:

- eine vertikale Linie im Geschwindigkeits-Zeitdiagramm
- eine vertikale Linie im Beschleunigungsdiagramm
- die zugehörige Strecke im Streckendiagramm
- aktuelle Zeit, Geschwindigkeit, Sollgeschwindigkeit und Beschleunigung
- aktuelle GPS-Koordinate
- ein beweglicher Marker in der GPS-Routenansicht

Die GPS-Ansicht verwendet die Koordinaten aus der berechneten Route und funktioniert vollständig lokal.

## Ampelregel

Ampelstopps werden **ausschließlich** an OSM-Ampeln erzeugt, die auf der Route gefunden wurden.

Beispiel: Sind auf der Route vier OSM-Ampeln vorhanden, liegt der Einstellbereich bei `0 … 4`. Ein fünfter Ampelstopp kann nicht eingestellt oder synthetisch ergänzt werden. Bei weniger ausgewählten Stopps wird eine Teilmenge der realen OSM-Positionen verwendet.

## Geschwindigkeitsmodell

Der Basisverlauf entsteht aus dem OSM-Attribut `maxspeed`. Darauf werden weitere Grenzen und Ereignisse angewendet:

```text
OSM-Straßenlimit
    ↓
Fahrer-Reisegeschwindigkeit und absolute Obergrenze
    ↓
Straßenbelag
    ↓
Kurvenlimit aus Radius und Querbeschleunigung
    ↓
reale OSM-Ampelstopps und Überholvorgänge
    ↓
Fahrerrauschen
    ↓
Beschleunigungs-, Brems- und Ruckbegrenzung
```

Gezeigt werden:

- Geschwindigkeit über Strecke
- GPS-Routenansicht mit aktuellem Positionsmarker
- Geschwindigkeit über Zeit
- Längsbeschleunigung über Zeit

## Export

Über **CSV + JSON exportieren** entstehen beispielsweise:

```text
speed_profile_result.csv
speed_profile_result.json
```

Die CSV enthält Zeit, Strecke, Geschwindigkeit, Sollgeschwindigkeit und Beschleunigung. Die JSON-Datei enthält zusätzlich Parameter, räumliche Profile und Ereignisse.

## PBF-Schnellindex

Direktes Lesen einer großen PBF ist langsam, weil sie für räumliche Ausschnitte sequenziell durchsucht werden muss. Nach Auswahl einer PBF kann deshalb einmalig **PBF-Schnellindex erstellen** ausgeführt werden. Die Anwendung erzeugt ein räumlich indiziertes `*_routing.gpkg` und verwendet es anschließend automatisch.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s qt_route_selector\tests -v
```

Die Tests prüfen unter anderem Routing, Fahrerprofile, Kurven, OSM-Ampelobergrenze, Überholen, Rauschen und Kartenprojektion.

## Aktuelle Grenze

Die Route enthält derzeit kein digitales Höhenprofil. Masse, Rollwiderstand, Antriebs- und Bremskraft werden bereits berücksichtigt; Steigung und Gefälle benötigen später ein lokales DEM/Höhenmodell.
