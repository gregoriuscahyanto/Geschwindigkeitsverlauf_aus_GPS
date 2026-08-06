# Lokales Höhenprofil mit DEM / GeoTIFF

Eine OSM-PBF enthält Straßen, Wege, Ampeln und OSM-Tags. Sie enthält normalerweise **kein durchgängiges Geländehöhenmodell** entlang einer berechneten Route. Deshalb kann allein aus der PBF kein zuverlässiges Höhenprofil erzeugt werden.

Die Anwendung unterstützt zusätzlich ein lokales digitales Höhenmodell als GeoTIFF:

```text
*.tif
*.tiff
```

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
- **NoData:** Das Raster besitzt an den Routenkoordinaten keine gültigen Höhenwerte.
- **CRS fehlt:** Das GeoTIFF besitzt keine verwertbare Georeferenzierung.
