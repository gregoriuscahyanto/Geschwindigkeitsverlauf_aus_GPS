# Geschwindigkeitsverlauf aus OSM-Routen

Lokale Windows-Desktopanwendung zur Routenplanung mit OpenStreetMap-Daten und zur Simulation eines realistischen Geschwindigkeits-, Beschleunigungs-, Höhen- und Leistungsverlaufs.

Die Anwendung läuft vollständig in Python/PySide6. Es ist kein Java, Docker oder lokaler Server erforderlich.

## Schnellstart unter Windows

Empfohlen wird Python 3.11 (64 Bit). Für einen sauberen Checkout legt das Setup die virtuelle Umgebung und alle Laufzeitdaten **außerhalb des Repositories** unter `%LOCALAPPDATA%\GPS-Routenplaner` ab.

```powershell
.\scripts\setup_windows.ps1
```

Danach starten:

```powershell
& "$env:LOCALAPPDATA\GPS-Routenplaner\venv\Scripts\python.exe" -m qt_route_selector
```

Alternativ kann eine bereits vorhandene Python-3.11-Umgebung verwendet werden:

```powershell
python -m pip install -r requirements.txt
python -m qt_route_selector
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

## Laufzeitdaten

Quellcode und Laufzeitdaten sind bewusst getrennt. Standardmäßig verwendet die Anwendung unter Windows:

```text
%LOCALAPPDATA%\GPS-Routenplaner\
  data\      OSM-PBF, POLY, Routing-GPKG und Höhenmodelle
  state\     route_result.json und selected_region.json
  exports\   reservierter Standardordner für Exporte
  venv\      von scripts/setup_windows.ps1 erzeugte Python-Umgebung
```

Der Speicherort kann für Tests oder besondere Installationen über `GPS_ROUTENPLANER_HOME` überschrieben werden.

Für Österreich wird ein landesweites DGM verwendet. Außerhalb Österreichs werden routenbezogen Copernicus-GLO-30-Kacheln gecacht. Ein Terrain-DEM bildet Tunnel- und Brückenfahrbahnen nicht exakt ab; das ist bei starken Höhenunterschieden zu berücksichtigen.

## Bestehenden Checkout einmalig bereinigen

Ein `git pull` löscht ignorierte lokale Ordner wie `.venv`, `data` oder `results` nicht. Deshalb gibt es für ältere Arbeitskopien ein bewusst konservatives Cleanup-Skript. Es migriert ein vorhandenes `data`-Verzeichnis nach `%LOCALAPPDATA%\GPS-Routenplaner\data`, verschiebt Route-JSONs nach `state` und archiviert alte Prototypordner in einem datierten Backup **neben** dem Repository statt sie ungefragt zu löschen.

Zuerst die externe Umgebung anlegen, danach bereinigen:

```powershell
.\scripts\setup_windows.ps1
.\scripts\cleanup_legacy_workspace.ps1 -RemoveVenv
```

Vorab prüfen, ohne Dateien zu verschieben:

```powershell
.\scripts\cleanup_legacy_workspace.ps1 -RemoveVenv -WhatIf
```

Nach der einmaligen Bereinigung sieht der Projektroot im Wesentlichen so aus:

```text
.github/
qt_route_selector/
scripts/
.gitattributes
.gitignore
README.md
requirements.txt
```

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

## Tests

```powershell
python -m unittest discover -s qt_route_selector\tests -v
```

GitHub Actions installiert `requirements.txt`, kompiliert das Paket und führt dieselben Unit-/GUI-Smoke-Tests im Qt-Offscreen-Modus aus.

## Generierte Dateien

Laufzeitdaten gehören nicht in Git. Die `.gitignore` enthält zusätzlich die Verzeichnisnamen des alten Prototyp-Workspaces, damit sie bei bestehenden Checkouts nicht versehentlich erneut committed werden.
