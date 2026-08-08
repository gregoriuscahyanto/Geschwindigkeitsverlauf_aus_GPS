# Geschwindigkeitsverlauf aus OSM-Routen

Lokale Windows-Desktopanwendung zur Routenplanung mit OpenStreetMap-Daten und zur Simulation eines realistischen Geschwindigkeits-, Beschleunigungs-, Höhen- und Leistungsverlaufs.

Die Anwendung läuft vollständig in Python/PySide6. Es ist kein Java, Docker, lokaler Server oder Adminzugriff erforderlich.

## Schnellstart unter Windows / VS Code

Empfohlen wird Python 3.11 (64 Bit). Das Setup erzeugt eine normale `.venv` direkt im Repository. Dadurch erkennt VS Code die Projektumgebung automatisch bzw. kann sie über **Python: Select Interpreter** auswählen.

```powershell
.\scripts\setup_windows.ps1
```

Danach entweder ein neues VS-Code-Terminal öffnen oder die Umgebung manuell aktivieren:

```powershell
.\.venv\Scripts\Activate.ps1
```

Falls PowerShell die Aktivierung nur wegen der Execution Policy blockiert, reicht für das aktuelle Terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Anschließend startet die Anwendung einfach mit:

```powershell
python -m qt_route_selector
```

Ohne Aktivierung kann sie ebenfalls direkt über die Projektumgebung gestartet werden:

```powershell
& ".\.venv\Scripts\python.exe" -m qt_route_selector
```

Das Setup kann Installation und Start auch zusammen ausführen:

```powershell
.\scripts\setup_windows.ps1 -Run
```

## Anwendung

Die Oberfläche besteht aus drei Tabs:

1. **Route und Karte** – Start, Ziel und Zwischenpunkte wählen. Das passende OSM-Gebiet wird automatisch erkannt; vorhandene lokale Daten werden wiederverwendet und fehlende Routing-/Höhendaten bei Bedarf vorbereitet.
2. **Geschwindigkeitsverlauf** – Fahrer-/Fahrzeugparameter, kombinierter Analyseplot, Karte, Energiebilanz und kumuliertes Lastkollektiv. Parameter besitzen kontextuelle `(i)`-Hilfen und Änderungen gegenüber dem Preset werden sichtbar markiert.
3. **Datenabdeckung** – lokale POLY-, PBF- und Routing-GPKG-Abdeckung ansehen, ohne zusätzliche große Downloads auszulösen.

### Fahrer und Simulation

Enthalten sind die Presets **Normalo**, **Rennfahrer**, **Handwerker**, **Rentner** und **Rentner + Anhänger**. Die Presets setzen vollständige Fahrerverhaltensparameter; alle Werte können anschließend manuell verändert und auf das Preset zurückgesetzt werden.

Ampelstopps stammen ausschließlich aus tatsächlich erkannten OSM-Verkehrssignalen. Die Anwendung erzeugt keine synthetischen Ampeln.

Die Radleistung berücksichtigt Beschleunigung, Steigung, Rollwiderstand, Luftwiderstand und optional den Anhänger. Angezeigt werden Antriebsenergie, ideale Rekuperationsenergie und Nettoenergie. Die aktuelle Energieberechnung nimmt für die Rekuperation 100 % Wirkungsgrad sowie keine Leistungs- oder Kapazitätsbegrenzung an.

## Trennung von Entwicklungsumgebung und Laufzeitdaten

Die lokale Python-Umgebung gehört zum Entwicklungs-Checkout und liegt hier:

```text
<Repository>\.venv\
```

Sie ist per `.gitignore` ausgeschlossen und wird nicht committed.

Große bzw. generierte Anwendungsdaten bleiben bewusst **außerhalb** des Repositories. Standardmäßig verwendet die Anwendung unter Windows:

```text
%LOCALAPPDATA%\GPS-Routenplaner\
  data\      OSM-PBF, POLY, Routing-GPKG und Höhenmodelle
  state\     route_result.json und selected_region.json
  exports\   Standardordner für Exporte
```

Der Runtime-Speicherort kann für Tests oder besondere Installationen über `GPS_ROUTENPLANER_HOME` überschrieben werden.

Für Österreich wird ein landesweites DGM verwendet. Außerhalb Österreichs werden routenbezogen Copernicus-GLO-30-Kacheln gecacht. Ein Terrain-DEM bildet Tunnel- und Brückenfahrbahnen nicht exakt ab; das ist bei starken Höhenunterschieden zu berücksichtigen.

## Bestehenden Checkout einmalig bereinigen

Ein `git pull` löscht ignorierte lokale Ordner wie `data` oder alte Prototype-Verzeichnisse nicht. Das Cleanup-Skript migriert ein vorhandenes `data`-Verzeichnis nach `%LOCALAPPDATA%\GPS-Routenplaner\data`, verschiebt Route-JSONs nach `state` und archiviert alte Prototype-Ordner in einem datierten Backup **neben** dem Repository statt sie ungefragt zu löschen.

Die `.venv` wird dabei absichtlich nicht verändert.

Vorab prüfen:

```powershell
.\scripts\cleanup_legacy_workspace.ps1 -WhatIf
```

Danach ausführen:

```powershell
.\scripts\cleanup_legacy_workspace.ps1
```

Ein typischer lokaler Projektroot sieht danach so aus:

```text
.github/
.venv/                    # lokal, von Git ignoriert
qt_route_selector/
scripts/
.gitattributes
.gitignore
README.md
requirements.txt
```

## VS-Code-Interpreter

Wenn VS Code nicht automatisch `.venv` auswählt:

1. `Ctrl+Shift+P`
2. **Python: Select Interpreter**
3. `<Repository>\.venv\Scripts\python.exe` auswählen

Danach öffnet ein neues VS-Code-Terminal normalerweise direkt mit `(.venv)`.

## Projektstruktur

```text
qt_route_selector/
  __main__.py                  # python -m qt_route_selector
  complete_app.py              # öffentlicher Anwendungseinstieg
  main.py / main.qml           # Routenplanung und Karte
  runtime_paths.py             # per-user Daten-/Statuspfade
  auto_data.py / auto_region.py
  local_router.py / routing_cache.py
  speed_simulation.py          # Fahrdynamik-Grundmodell
  enhanced_speed_simulation.py
  resistance_power.py          # Fahrwiderstände und Energie
  load_collective_curve.py
  integrated_speed_profile.py  # öffentlicher Simulations-UI-Einstieg
  parameter_help.py
  tests/
  _internal/simulation_layers/ # private, getestete UI-Implementierungsschichten
```

Die Dateien unter `_internal/` sind Implementierungsdetails. Externer Code sollte nur die öffentlichen Module unter `qt_route_selector` verwenden.

## Abhängigkeiten

`requirements.txt` enthält die für den aktuellen Stand getesteten Python-Versionen. `scripts/setup_windows.ps1` installiert sie automatisch in `.venv` und prüft danach zentrale Laufzeitmodule wie PySide6, PyQtGraph, NumPy, GeoPandas und Rasterio.

## Tests

Mit aktivierter `.venv`:

```powershell
python -m unittest discover -s qt_route_selector\tests -v
```

GitHub Actions installiert `requirements.txt`, kompiliert das Paket und führt dieselben Unit-/GUI-Smoke-Tests im Qt-Offscreen-Modus aus.

## Generierte Dateien

Laufzeitdaten gehören nicht in Git. Die `.gitignore` schließt `.venv`, Runtime-Ausgaben, Geodaten und die Verzeichnisnamen des alten Prototype-Workspaces aus, damit sie bei bestehenden Checkouts nicht versehentlich committed werden.
