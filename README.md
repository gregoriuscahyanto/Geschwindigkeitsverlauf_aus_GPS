# Geschwindigkeitsverlauf aus OSM-Routen

Lokale Windows-Desktopanwendung zur Routenplanung mit OpenStreetMap-Daten und zur Simulation eines realistischen Geschwindigkeits-, Beschleunigungs-, Höhen- und Leistungsverlaufs.

Die Anwendung läuft vollständig in Python/PySide6. Es ist kein Java, Docker oder lokaler Server erforderlich.

## Schnellstart unter Windows

Empfohlen: Python 3.11 (64 Bit).

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python qt_route_selector\complete_app.py
```

Nach einem Update genügt normalerweise:

```powershell
git pull --ff-only
python -m pip install -r requirements.txt
python qt_route_selector\complete_app.py
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

## Lokale Daten

Automatisch heruntergeladene OSM- und Höhendaten liegen unter `data/` und werden nicht versioniert. Unterstützt werden regionale Extrakte für Österreich, Baden-Württemberg, Bayern, Hessen und die Schweiz sowie DACH als grenzüberschreitender Fallback.

Für Österreich wird ein landesweites DGM verwendet. Außerhalb Österreichs werden routenbezogen Copernicus-GLO-30-Kacheln gecacht. Ein Terrain-DEM bildet Tunnel- und Brückenfahrbahnen nicht exakt ab; das ist bei starken Höhenunterschieden zu berücksichtigen.

## Projektstruktur

```text
qt_route_selector/
  complete_app.py              # Anwendungseinstieg
  main.py / main.qml           # Routenplanung und Karte
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

Die Dateien unter `_internal/` sind Implementierungsdetails. Externer Code sollte nur `qt_route_selector.integrated_speed_profile` verwenden.

## Tests

```powershell
python -m unittest discover -s qt_route_selector\tests -v
```

GitHub Actions kompiliert das Paket und führt dieselben Unit-/GUI-Smoke-Tests im Qt-Offscreen-Modus aus.

## Generierte Dateien

Routen-JSON, Exporte, heruntergeladene PBF/DEM-Daten und erzeugte Routing-GPKGs sind in `.gitignore` eingetragen und gehören nicht in Git.
