# Qt-Routenauswahl und vollständig lokales Python-Routing

Die Anwendung ersetzt den bisherigen manuellen Weg über die GraphHopper-Webseite und eine heruntergeladene GPX-Datei. Karte, Start-/Zielauswahl, Routing und OSM-Auswertung laufen ohne lokalen Server und ohne Internetverbindung.

## Funktionsumfang

- native Oberfläche mit PySide6/QML
- eigener Qt-Vektorrenderer ohne QtLocation-Kachelserver
- verschiebbare und zoombare Offline-Karte aus lokalen OSM-Straßendaten
- Start- und Zielauswahl per Mausklick
- automatische, gepufferte Bounding Box für die Routingregion
- lokales Routing ohne GraphHopper-, OSRM- oder Valhalla-Server
- Unterstützung für FlatGeobuf, GeoPackage, GeoJSON, Shapefile und als langsamere Fallback-Quelle OSM PBF
- Berücksichtigung von Einbahnstraßen und einfachen OSM-Zugriffsbeschränkungen
- zeitgewichtetes Routing anhand von `maxspeed` bzw. Straßenklassen-Standardwerten
- Anzeige der Route und gefundener Ampeln
- Export als `route_result.json`

## Was für den Offline-Betrieb benötigt wird

- Python 3.11 (64 Bit)
- die virtuelle Python-Umgebung aus `qt_route_selector/requirements.txt`
- eine lokale `.osm.pbf`, `.fgb` oder `.gpkg`

Nicht benötigt werden:

- Internetzugriff
- API-Key
- GraphHopper-/OSRM-/Valhalla-Server
- Java
- Docker
- heruntergeladene Kartenkacheln

Die Kartenansicht zeichnet die Straßen direkt aus der lokalen OSM-Datenquelle. Es werden keine HTTP-Anfragen für die Karte ausgeführt.

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

1. Über **Straßendaten wählen** eine lokale PBF-/FGB-/GeoPackage-Datei auswählen.
2. Die Anwendung lädt automatisch die Straßen im aktuell sichtbaren Ausschnitt.
3. Karte mit gedrückter linker Maustaste verschieben und mit dem Mausrad zoomen.
4. Nach größeren Kartenbewegungen **Kartenausschnitt laden** anklicken.
5. Startpunkt anklicken.
6. Zielpunkt anklicken.
7. **Route berechnen** anklicken.

## Wahl der Straßendaten

### Empfohlen: FlatGeobuf oder GeoPackage

Für wiederholte Routen ist ein räumlich indiziertes Format deutlich schneller als das wiederholte Lesen einer großen PBF-Datei. Das vorhandene Skript kann eine PBF vorbereiten:

```powershell
.\.venv\Scripts\python.exe build_highways_fgb_v2.py `
  --in_pbf "C:\Daten\region.osm.pbf" `
  --out_fgb "C:\Daten\region_highways.fgb" `
  --tiles 8x8
```

Danach in der Qt-Anwendung `region_highways.fgb` auswählen.

### Direkt: `.osm.pbf`

Eine PBF-Datei kann direkt ausgewählt werden. Die Anwendung liest für Karte und Route nur Objekte, die den jeweiligen Kartenausschnitt bzw. die Routing-Bounding-Box schneiden.

OSM PBF ist intern dennoch ein sequenzielles Format. Bei einer sehr großen Länderdatei kann das Laden eines Ausschnitts deshalb wesentlich länger dauern als mit FlatGeobuf oder GeoPackage.

Die direkte PBF-Unterstützung hängt davon ab, ob der von Pyogrio verwendete GDAL-Build den OSM-Treiber enthält. Falls das Lesen der PBF fehlschlägt, zuerst mit `build_highways_fgb_v2.py` eine FGB-Datei erzeugen.

## Offline-Kartenrenderer

Der Renderer befindet sich in `offline_map.py` und verwendet Web-Mercator nur für die Bildschirmprojektion. Gerendert werden aktuell:

- Straßen, farblich und nach Breite anhand der OSM-Straßenklasse
- Start- und Zielmarker
- Routingregion
- berechnete Route
- Ampelmarker
- Maßstabsbalken
- OSM-Attribution

Der sichtbare Straßenbestand wird räumlich begrenzt und leicht vereinfacht. Bei extrem dichten Ausschnitten wird die Darstellung aus Speicher- und Performancegründen begrenzt; die eigentliche Routenberechnung arbeitet trotzdem mit dem vollständig geladenen Routingausschnitt.

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

Diese Datei kann direkt als Eingang für das Fahrer-, Kurven- und Geschwindigkeitsmodell verwendet werden.

## Tests ausführen

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s qt_route_selector\tests -v
```

Die Tests prüfen unter anderem:

- OSM-Geschwindigkeitswerte
- OSM-Zusatztags
- Einbahnstraßen
- zusammenhängendes Routing
- Vorwärts-/Rückwärtsumrechnung der Kartenprojektion

## Wichtige Grenzen des aktuellen Routers

Der Router ist als nachvollziehbarer Forschungs- und Simulationsbaustein gedacht, nicht als vollständiges Navigationssystem. Derzeit werden unter anderem noch nicht ausgewertet:

- OSM-Abbiegebeschränkungen aus Relationen
- zeitabhängige Zufahrtsregeln
- Fahrzeughöhe, Fahrzeuggewicht und Gefahrgutregeln
- detaillierte Kreuzungs- und Abbiegekosten
- Fahrspuren und Spurwechsel

Die Karte zeigt derzeit primär Straßen. Gebäude, Gewässer, Wälder und weitere Flächennutzungen können später als zusätzliche lokale Vektorlayer ergänzt werden.
