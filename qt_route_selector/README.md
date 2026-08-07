# Qt-Routenplaner und Live-Geschwindigkeitsverlauf

Die Anwendung berechnet eine Route aus OSM-Daten und erzeugt daraus einen live einstellbaren Geschwindigkeitsverlauf. Karte, Routing und Simulation befinden sich in **einem Fenster mit zwei Tabs**.

## Start

```powershell
.\.venv\Scripts\python.exe -m pip install -r qt_route_selector\requirements.txt
.\.venv\Scripts\python.exe qt_route_selector\complete_app.py
```

## Automatische Datenvorbereitung

Im ersten Tab befindet sich oberhalb der Karte der Bereich **Daten automatisch vorbereiten**.

### Österreich – A10 / Großglockner

Mit **OSM + Höhen automatisch laden** erledigt die Anwendung beim ersten Mal selbstständig:

1. `austria-latest.osm.pbf` von Geofabrik herunterladen,
2. MD5-Prüfsumme kontrollieren,
3. lokalen räumlich indizierten Routing-Cache erzeugen,
4. das österreichweite 10-m-DGM von Geoland/data.gv.at herunterladen,
5. das GeoTIFF entpacken,
6. Routingdatei und Höhenmodell automatisch aktivieren.

Die Dateien landen standardmäßig unter:

```text
data/
├── osm/
│   ├── austria-latest.osm.pbf
│   └── austria-latest_routing.gpkg
└── elevation/
    ├── austria-dgm10.zip
    └── austria-dgm10/
```

Ist eine Datei bereits vorhanden, wird sie wiederverwendet. Ein vorhandener aktueller Routingindex wird nicht erneut aufgebaut. Nach der einmaligen Vorbereitung funktionieren Routing und Höhenprofil lokal/offline.

### Alpen – grenzüberschreitend

Für längere grenzüberschreitende Alpenrouten kann stattdessen der Geofabrik-Extrakt `alps-latest.osm.pbf` verwendet werden. Dieser ist deutlich größer als der Österreich-Extrakt. Das automatisch vorbereitete DGM deckt dabei Österreich ab; für Strecken außerhalb Österreichs ist eine weitere Höhenquelle erforderlich.

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
- reale OSM-Ampelstopps und Rotphasen
- Überholvorgänge
- Fahrerrauschen
- Fahrzeug- und Anhängermasse

Die drei synchronisierten Plots liegen links untereinander:

1. Geschwindigkeit
2. Längsbeschleunigung
3. Höhenprofil

Rechts befindet sich die geografische Kartenansicht. Die gemeinsame X-Achse kann zwischen Zeit und Strecke umgeschaltet werden. Hovering bewegt den gemeinsamen Cursor und gleichzeitig den Fahrzeugmarker auf der Karte.

## Höhenprofil

Höhen können aus einem in der Route enthaltenen Höhenfeld oder aus einem lokalen GeoTIFF-DGM gelesen werden. Der automatische Österreich-Workflow aktiviert das österreichweite 10-m-DGM selbstständig. Alternativ kann weiterhin manuell ein DEM/GeoTIFF ausgewählt werden.

Wichtig für Gebirgsstraßen: Ein DGM beschreibt die Geländeoberfläche. Bei Tunneln liegt die reale Straße unter dem Gelände und bei Brücken über dem Gelände. Tunnel- und Brückenabschnitte müssen deshalb für ein fahrdynamisch korrektes Straßenhöhenprofil separat behandelt bzw. interpoliert werden.

## Ampelregel

Ampelstopps werden **ausschließlich** an OSM-Ampeln erzeugt, die auf der Route gefunden wurden. Sind vier OSM-Ampeln vorhanden, liegt der Einstellbereich bei `0 … 4`; synthetische fünfte Ampeln werden nicht erzeugt.

## Geschwindigkeitsmodell

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

## Export

Über **CSV + JSON exportieren** entstehen beispielsweise:

```text
speed_profile_result.csv
speed_profile_result.json
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s qt_route_selector\tests -v
```
