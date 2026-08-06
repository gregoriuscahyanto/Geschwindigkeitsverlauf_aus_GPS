# Qt-Routenauswahl und lokales Python-Routing

Die Anwendung ersetzt den bisherigen manuellen Weg über die GraphHopper-Webseite und eine heruntergeladene GPX-Datei.

## Funktionsumfang

- native Oberfläche mit PySide6/QML
- verschiebbare und zoombare OSM-Karte
- Start- und Zielauswahl per Mausklick
- automatische, gepufferte Bounding Box für die interessante Region
- lokales Routing ohne GraphHopper-, OSRM- oder Valhalla-Server
- Unterstützung für FlatGeobuf, GeoPackage, GeoJSON, Shapefile und als langsamere Fallback-Quelle OSM PBF
- Berücksichtigung von Einbahnstraßen und einfachen OSM-Zugriffsbeschränkungen
- zeitgewichtetes Routing anhand von `maxspeed` bzw. Straßenklassen-Standardwerten
- Anzeige der Route und gefundener Ampeln
- Export als `route_result.json`

## Installation

Aus dem Repository-Stammverzeichnis unter Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r qt_route_selector\requirements.txt
```

## Anwendung starten

```powershell
.\.venv\Scripts\python.exe qt_route_selector\main.py
```

Danach:

1. Startpunkt auf der Karte anklicken.
2. Zielpunkt anklicken.
3. Über **Straßendaten wählen** eine lokale Datei auswählen.
4. **Route berechnen** anklicken.

## Kartenanzeige ohne API-Key

Qt kann seine Anbieterinformationen dynamisch laden. Dabei kann ein Drittanbieter-Kartenstil ausgewählt werden, der einen API-Key verlangt. Die Anwendung deaktiviert diese dynamische Auswahl und verwendet stattdessen ausdrücklich die Standard-Kacheln von OpenStreetMap:

```text
https://tile.openstreetmap.org/{z}/{x}/{y}.png
```

Dafür ist kein API-Key nötig. Die Anwendung setzt einen eigenen User-Agent, zeigt die OpenStreetMap-Attribution an, verwendet den Qt-Kachelcache und deaktiviert das Vorladen unsichtbarer Nachbarkacheln.

Die öffentlichen OpenStreetMap-Kacheln sind nur für normale interaktive Anzeige vorgesehen. Sie dürfen nicht automatisiert für große Gebiete oder als Offline-Kartenpaket heruntergeladen werden.

## Wahl der Straßendaten

### Empfohlen: FlatGeobuf oder GeoPackage

Für wiederholte Routen ist ein räumlich indiziertes Format deutlich schneller als das wiederholte Lesen einer großen PBF-Datei. Das bestehende Skript `build_highways_fgb_v2.py` kann zur Vorbereitung verwendet werden.

### Direkt: `.osm.pbf`

Eine PBF-Datei kann direkt ausgewählt werden. Die Anwendung liest nur Objekte, die die berechnete Bounding Box schneiden. OSM PBF ist intern dennoch ein sequenzielles Format; deshalb kann der erste Lauf mit einer großen Länderdatei deutlich länger dauern.

Die direkte PBF-Unterstützung hängt außerdem davon ab, ob der von Pyogrio verwendete GDAL-Build den OSM-Treiber enthält. Falls der OSM-Treiber fehlt, zuerst eine FGB- oder GeoPackage-Datei erzeugen.

## Ausgabedateien

### `selected_region.json`

Enthält:

- Start- und Zielkoordinate
- westliche, südliche, östliche und nördliche Grenze
- Sicherheitsrand
- gewählte Straßendatei

### `route_result.json`

Enthält:

- Routengeometrie als GPS-Koordinaten
- Segmentlängen
- vorläufige Fahrzeiten
- `maxspeed_kmh`
- `highway`
- `surface`
- Straßenname und Referenz
- Einbahnstraßeninformation
- Ampelpositionen und deren Entfernung vom Routenstart
- Statistik über den aufgebauten Routinggraphen

Diese Datei kann später direkt als Eingang für das Fahrer-, Kurven- und Geschwindigkeitsmodell verwendet werden.

## Tests ausführen

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s qt_route_selector\tests -v
```

## Wichtige Grenzen des aktuellen Routers

Der Router ist als nachvollziehbarer Forschungs- und Simulationsbaustein gedacht, nicht als vollständiges Navigationssystem. Derzeit werden unter anderem noch nicht ausgewertet:

- OSM-Abbiegebeschränkungen aus Relationen
- zeitabhängige Zufahrtsregeln
- Fahrzeughöhe, Fahrzeuggewicht und Gefahrgutregeln
- detaillierte Kreuzungs- und Abbiegekosten
- Fahrspuren und Spurwechsel

Das Routing ist vollständig lokal. Die Hintergrundkarte benötigt beim erstmaligen Anzeigen Internetzugriff. Bereits geladene Kacheln können aus dem Qt-Cache wiederverwendet werden; das ist jedoch kein garantiertes Offline-Kartenpaket. Für einen vollständig offline arbeitenden Kartenhintergrund wird später eine lokal bereitgestellte, lizenzkonforme Tile- oder Vektorkartenquelle benötigt.
