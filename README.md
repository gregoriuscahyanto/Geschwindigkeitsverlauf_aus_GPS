# Geschwindigkeitsverlauf aus OSM-Routen

Lokale Windows-Desktopanwendung zur Routenplanung mit OpenStreetMap-Daten und zur Simulation von Geschwindigkeits-, Beschleunigungs-, Höhen-, Leistungs- und Energieverläufen entlang realer Straßenrouten.

Die Anwendung verbindet **Geodaten, Routing und Fahrdynamik** in einem Werkzeug. Start, Ziel und optionale Zwischenpunkte werden auf der Karte gewählt. Daraus werden lokale OSM-Routingdaten, Straßenattribute, Kurven, reale OSM-Ampeln und ein Höhenprofil aufbereitet. Anschließend können Fahrer- und Fahrzeugparameter verändert und die resultierenden Fahr- und Leistungsprofile verglichen werden.

Die Anwendung läuft lokal mit **Python 3.11 / PySide6**. Java, Docker, ein lokaler Server und Adminrechte sind nicht erforderlich.

## Typischer Ablauf

```text
Start / Ziel / Wegpunkte
        ↓
OpenStreetMap-Routing
        ↓
Straßenattribute + Kurven + reale OSM-Ampeln
        ↓
Höhenprofil
        ↓
Fahrer- und Fahrzeugmodell
        ↓
Geschwindigkeit / Beschleunigung
        ↓
Radleistung / Energie / Lastkollektiv
```

## Installation unter Windows

Benötigt wird **Python 3.11 (64 Bit)**.

Der empfohlene Weg ist ab jetzt immer über die `.cmd`-Dateien im Projektroot. Dadurch muss die PowerShell-Ausführungsrichtlinie nicht manuell geändert werden.

### Einrichten

Im Projektordner ausführen:

```cmd
setup_windows.cmd
```

Das Setup:

- prüft Python 3.11 / 64 Bit,
- erstellt die Python-Umgebung,
- installiert die Abhängigkeiten,
- verwendet ein vorhandenes `wheelhouse` automatisch offline,
- prüft bei Offline-Installation das `wheelhouse` auf Vollständigkeit,
- umgeht Probleme mit deaktiviertem Windows-Long-Path-Support automatisch über kurze Benutzerpfade.

### Starten

```cmd
start_windows.cmd
```

Eine Aktivierung der `.venv` ist nicht notwendig.

Auf normalen Windows-Systemen liegt die Umgebung üblicherweise hier:

```text
<Repository>\.venv\
```

Wenn Windows Long Paths deaktiviert sind, kann das Setup stattdessen automatisch den kurzen Benutzerpfad verwenden:

```text
%LOCALAPPDATA%\GPSRP\venv\
```

`start_windows.cmd` findet die passende Umgebung automatisch.

## Enterprise-PC ohne Internet / hinter Firewall

Der Enterprise-PC benötigt nur **Python 3.11 (64 Bit)**. Python-Pakete sowie OSM-, Routing- und Höhendaten werden vorher auf einem Windows-PC mit Internet vorbereitet und anschließend kopiert.

### 1. Auf dem Internet-PC Python-Pakete vorbereiten

Aktuellen Projektstand holen und im Projektordner ausführen:

```cmd
build_offline_dependencies.cmd
```

Dadurch wird der Ordner

```text
<Repository>\wheelhouse\
```

erzeugt. Er enthält die benötigten Windows-x64-Wheels für Python 3.11 sowie eine `MANIFEST.txt`, mit der das Enterprise-Setup prüft, ob das Wheelhouse vollständig und passend zur aktuellen `requirements.txt` ist.

**Wichtig:** Wenn sich `requirements.txt` geändert hat, das Wheelhouse immer neu erzeugen. Nicht einzelne Wheel-Dateien nachträglich zusammenkopieren.

### 2. OSM-, Routing- und Höhendaten vorbereiten

Auf dem Internet-PC die Anwendung starten und die Gebiete bzw. Routen einmal vorbereiten, die später offline benötigt werden.

Die heruntergeladenen und erzeugten Daten liegen standardmäßig hier:

```text
%LOCALAPPDATA%\GPS-Routenplaner\data\
```

Darin befinden sich je nach Gebiet unter anderem:

```text
OSM-PBF
POLY
Routing-GPKG
Copernicus-/DEM-Höhendaten
```

Für einen vollständig abgeschotteten Rechner den **kompletten `data`-Ordner** kopieren. Fehlende Gebiete oder DEM-Kacheln würden sonst später einen Download benötigen.

### 3. Auf den Enterprise-PC kopieren

Kopiert werden genau zwei Dinge:

1. der **gesamte Projektordner inklusive `wheelhouse`**
2. der komplette Datenordner

```text
%LOCALAPPDATA%\GPS-Routenplaner\data\
```

Die `.venv` muss **nicht** mitkopiert werden.

Auf dem Enterprise-PC die Geodaten wieder unter

```text
%LOCALAPPDATA%\GPS-Routenplaner\data\
```

ablegen.

### 4. Auf dem Enterprise-PC installieren

Im kopierten Projektordner einfach ausführen:

```cmd
setup_windows.cmd
```

Das Setup verwendet das lokale Wheelhouse mit `--no-index`; für die Paketinstallation wird daher kein Zugriff auf PyPI benötigt.

Falls die Windows-Pfadlängenunterstützung deaktiviert ist, verwendet das Setup automatisch kurze Pfade unter

```text
%LOCALAPPDATA%\GPSRP\
```

für Python-Umgebung und temporäre Installationsdateien. Eine Registry-Änderung oder Adminfreigabe für Windows Long Paths ist dafür nicht erforderlich.

### 5. Starten

```cmd
start_windows.cmd
```

Das ist auch auf Enterprise-Rechnern der empfohlene Startweg.

> Falls die Unternehmensrichtlinie die Ausführung von `pip` grundsätzlich verbietet, muss die lokale Python-Installation durch die IT freigegeben oder zentral bereitgestellt werden. Das Offline-Setup selbst verwendet `pip` nur mit lokalen Dateien.

## Anwendung

Die Oberfläche besteht aus drei Tabs:

1. **Route und Karte** – Start, Ziel und Zwischenpunkte wählen. Das passende OSM-Gebiet wird automatisch erkannt; vorhandene lokale Daten werden wiederverwendet und fehlende Routing-/Höhendaten bei Bedarf vorbereitet.
2. **Geschwindigkeitsverlauf** – Fahrer-/Fahrzeugparameter, Analyseplot, Karte, Energiebilanz und kumuliertes Lastkollektiv.
3. **Datenabdeckung** – lokale POLY-, PBF- und Routing-GPKG-Abdeckung ansehen, ohne zusätzliche große Downloads auszulösen.

### Fahrer und Simulation

Enthalten sind die Presets **Normalo**, **Rennfahrer**, **Handwerker**, **Rentner** und **Rentner + Anhänger**. Die Presets sind technische Modellszenarien und keine empirischen Aussagen über reale Personengruppen. Alle Werte können verändert und zurückgesetzt werden.

Ampelstopps stammen ausschließlich aus tatsächlich erkannten OSM-Verkehrssignalen. Die Anwendung erzeugt **keine synthetischen Ampeln**.

Die Radleistung berücksichtigt:

- Beschleunigung,
- Steigung bzw. Gefälle,
- Rollwiderstand,
- Luftwiderstand,
- optional einen Anhänger.

Angezeigt werden unter anderem Antriebsenergie, ideales Rekuperationspotenzial und Nettoenergie. Die aktuelle Rekuperationsrechnung nimmt idealisiert 100 % Wirkungsgrad und keine Leistungs- oder Kapazitätsbegrenzung an.

### Rennstrecken

OSM-Rennstrecken mit `highway=raceway`, zum Beispiel die Nürburgring-Nordschleife, werden vom Routing unterstützt. Für Rennstrecken ohne verwertbares OSM-`maxspeed` wird kein künstliches öffentliches Straßenlimit erfunden; das Kurven- und Fahrermodell bestimmt dann den Geschwindigkeitsverlauf.

Wenn sich das Routing-Cache-Format ändert, erzeugt die Anwendung aus der bereits vorhandenen PBF automatisch einen neuen versionierten Routing-GPKG. Die PBF muss dafür nicht erneut heruntergeladen werden.

## MAT-Export

Simulationsergebnisse können direkt aus Python als `.mat` exportiert werden. MATLAB selbst wird für die Erzeugung **nicht** benötigt.

Die Datei enthält kompakte numerische Arrays wie beispielsweise:

```text
time_s
v_kmh
v_target_kmh
a_mps2
distance_m
elevation_m
curve_radius_m
grade_pct
p_total_kw
```

Zusätzlich enthält die MAT-Datei den Struct `sim`, der Daten nach Bezugsachse gruppiert, zum Beispiel:

```matlab
sim.time.time_s
sim.time.v_kmh
sim.route.distance_m
sim.route.elevation_m
sim.route.curve_radius_m
sim.events.traffic_lights.distance_m
sim.load.positive.kw
```

## Laufzeitdaten

Große und generierte Daten bleiben außerhalb des Git-Repositories. Standardmäßig verwendet die Anwendung unter Windows:

```text
%LOCALAPPDATA%\GPS-Routenplaner\
  data\      OSM-PBF, POLY, Routing-GPKG und Höhenmodelle
  state\     route_result.json und selected_region.json
  exports\   Standardordner für Exporte
```

Der Runtime-Speicherort kann über `GPS_ROUTENPLANER_HOME` überschrieben werden.

Für Österreich wird ein landesweites DGM verwendet. Außerhalb Österreichs werden routenbezogen Copernicus-GLO-30-Kacheln gecacht.

## Bekannte Einschränkungen

Die Anwendung ist ein technisches Simulations- und Analysewerkzeug und kein sicherheitskritisches Navigationssystem.

Insbesondere werden derzeit keine Live-Verkehrslage, aktuellen Straßensperrungen oder realen Ampelphasen berücksichtigt.

Das Höhenmodell beschreibt die Geländeoberfläche. Tunnel und Brücken können deshalb lokal ein falsches Fahrbahnhöhenniveau erhalten. Auf solchen Abschnitten müssen Höhen-, Steigungs- und Leistungsergebnisse entsprechend vorsichtig interpretiert werden.

Die Energieberechnung ist ein Radleistungsmodell und kein vollständiges Batterie-/Motor-/Wirkungsgradmodell.

## Bestehenden Checkout bereinigen

Ein `git pull` löscht ignorierte lokale Altverzeichnisse nicht. Vor einer Bereinigung zunächst prüfen:

```powershell
.\scripts\cleanup_legacy_workspace.ps1 -WhatIf
```

Danach bei Bedarf ausführen:

```powershell
.\scripts\cleanup_legacy_workspace.ps1
```

Das Skript migriert alte lokale Daten in die aktuellen Runtime-Verzeichnisse und archiviert alte Prototype-Ordner, statt sie ungefragt zu löschen.

## VS Code

Auf einem normalen Entwicklungsrechner ist der Interpreter:

```text
<Repository>\.venv\Scripts\python.exe
```

Wenn das Enterprise-Setup wegen deaktivierter Windows Long Paths die kurze Umgebung verwendet, lautet er stattdessen:

```text
%LOCALAPPDATA%\GPSRP\venv\Scripts\python.exe
```

In VS Code kann der Interpreter über `Ctrl+Shift+P` → **Python: Select Interpreter** ausgewählt werden.

## Projektstruktur

```text
setup_windows.cmd              # empfohlene Windows-/Enterprise-Einrichtung
start_windows.cmd              # Anwendung mit der passenden Python-Umgebung starten
build_offline_dependencies.cmd # Offline-Wheelhouse auf Internet-PC erzeugen

qt_route_selector/
  __main__.py
  complete_app.py
  main.py / main.qml
  runtime_paths.py
  auto_data.py / auto_region.py
  local_router.py / routing_cache.py
  speed_simulation.py
  enhanced_speed_simulation.py
  resistance_power.py
  load_collective_curve.py
  integrated_speed_profile.py
  mat_export.py
  tests/
  _internal/simulation_layers/

scripts/
  setup_windows.ps1
  build_offline_dependencies.ps1
  cleanup_legacy_workspace.ps1
```

Die `.cmd`-Dateien sind die empfohlenen Einstiegspunkte unter Windows. Sie rufen die PowerShell-Skripte mit den passenden Parametern auf. Die `.ps1`-Dateien bleiben für Entwicklung und direkte Nutzung erhalten.

## Abhängigkeiten

`requirements.txt` enthält die getesteten Python-Abhängigkeiten. Das Setup prüft zentrale Laufzeitmodule nach der Installation.

Für Offline-Rechner erzeugt `build_offline_dependencies.cmd` ein vollständiges lokales `wheelhouse` für **Python 3.11 / Windows x64**. Das Wheelhouse ist plattformspezifisch und wird nicht in Git committed.

## Tests

Mit eingerichteter Python-Umgebung:

```powershell
python -m unittest discover -s qt_route_selector\tests -v
```

GitHub Actions installiert `requirements.txt`, kompiliert das Paket, führt die Unit-/GUI-Smoke-Tests aus und validiert zusätzlich den Windows-Offline-Setup-Pfad.

## Generierte Dateien

Laufzeitdaten gehören nicht in Git. `.gitignore` schließt unter anderem `.venv`, `wheelhouse`, Runtime-Ausgaben und große Geodaten aus.