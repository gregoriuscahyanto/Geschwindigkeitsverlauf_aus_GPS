# Lokales Höhenprofil mit DEM / GeoTIFF

Eine OSM-PBF enthält Straßen, Wege, Ampeln und OSM-Tags. Sie enthält normalerweise **kein durchgängiges Geländehöhenmodell** entlang einer berechneten Route. Deshalb kann allein aus der PBF kein zuverlässiges Höhenprofil erzeugt werden.

Die Anwendung unterstützt zusätzlich ein lokales digitales Höhenmodell als GeoTIFF:

```text
*.tif
*.tiff
```

## Empfohlene Datenquellen

### Baden-Württemberg: LGL DGM1

Für Fahrten in Stuttgart und Baden-Württemberg ist das **Digitale Geländemodell DGM1** des Landesamts für Geoinformation und Landentwicklung Baden-Württemberg die beste Wahl.

- Rasterweite: 1 m
- reine Geländeoberfläche ohne Gebäude und Vegetation
- amtliche Höhendaten
- Ausgabe als GeoTIFF
- Download im Open GeoData Portal des LGL in 2 km x 2 km großen Kacheln
- Koordinatensystem: ETRS89 / UTM Zone 32N
- Höhenbezug: NHN / DHHN2016

Im Open GeoData Portal nach **Digitales Geländemodell (DGM1)** suchen und alle Kacheln herunterladen, die die Route abdecken. Die Anwendung kann derzeit eine GeoTIFF-Datei auswählen. Bei Routen über mehrere Kacheln sollten die Dateien vorher zu einem Rastermosaik zusammengeführt werden.

### Deutschland und Europa: Copernicus DEM GLO-30

Für größere Gebiete ist das **Copernicus DEM GLO-30** eine einfachere Alternative.

- globale Abdeckung
- Rasterweite ungefähr 30 m
- GeoTIFF verfügbar
- ausreichend für ein grobes Steigungs- und Höhenprofil
- Digitales Oberflächenmodell: Gebäude und Vegetation können die Höhe beeinflussen

Für eine kurze Stadtfahrt ist das LGL DGM1 genauer. Für lange, überregionale Fahrten ist Copernicus GLO-30 meist handlicher.

## Verwendung

1. Anwendung mit `complete_app.py` starten.
2. Zum Tab **Geschwindigkeitsverlauf** wechseln.
3. Im Bereich **Route** auf **DEM / GeoTIFF wählen** klicken.
4. Ein GeoTIFF auswählen, das die berechnete Route geografisch abdeckt.
5. Das Höhenprofil wird sofort neu berechnet.

Das GeoTIFF muss ein gültiges Koordinatensystem (CRS) und mindestens ein Höhenband besitzen. Die Anwendung transformiert die GPS-Koordinaten der Route automatisch in das CRS des Rasters und liest die Höhe an jedem Routenpunkt aus.

## Installation

Die aktualisierten Requirements enthalten `rasterio`:

```powershell
python -m pip install -r qt_route_selector\requirements.txt
```

## Fehlerfälle

- **Keine Höhenwerte:** Noch kein DEM gewählt und `route_result.json` enthält keine Felder wie `elevation_m`, `elevation` oder `ele`.
- **Route außerhalb des Rasters:** Das gewählte GeoTIFF deckt die Route nicht ab.
- **Mehrere DGM1-Kacheln:** Die Route verläuft über mehr als eine Datei; die Kacheln müssen zunächst zu einem GeoTIFF-Mosaik verbunden werden.
- **NoData:** Das Raster besitzt an den Routenkoordinaten keine gültigen Höhenwerte.
- **CRS fehlt:** Das GeoTIFF besitzt keine verwertbare Georeferenzierung.
