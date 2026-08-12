# Geschwindigkeitsverlauf aus OSM-Routen

Lokale Windows-Desktopanwendung zur Routenplanung mit OpenStreetMap-Daten und zur Simulation eines Geschwindigkeits-, Beschleunigungs-, Höhen-, Leistungs- und Energieverlaufs entlang einer realen Straßenroute.

Die Anwendung verbindet **Geodaten, Routing und Fahrdynamik** in einem gemeinsamen Werkzeug. Aus einer vom Benutzer gewählten Route werden Straßeninformationen, Höhenverlauf und erkannte Verkehrselemente aufbereitet. Darauf aufbauend kann untersucht werden, wie unterschiedliche Fahrer-, Fahrzeug- und Umgebungsparameter den zeitlichen Fahrverlauf sowie die resultierenden Radleistungen und Energien beeinflussen.

Die Anwendung läuft vollständig lokal in Python/PySide6. Es ist kein Java, Docker, lokaler Server oder Adminzugriff erforderlich.

## Worum geht es bei dem Projekt?

Eine reine GPS- oder OSM-Route beschreibt zunächst hauptsächlich **wo** ein Fahrzeug fährt. Für viele technische Fragestellungen ist jedoch zusätzlich interessant, **wie** diese Strecke voraussichtlich gefahren wird: Wo wird beschleunigt oder gebremst? Welche Geschwindigkeiten sind aufgrund von Straßenlimit, Kurven oder Verkehrselementen plausibel? Wie wirken Steigungen und Gefälle? Welche Radleistung wird dabei benötigt und wie verändert sich der Energiebedarf?

Dieses Projekt bildet die Verbindung zwischen diesen beiden Ebenen:

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

Das Ergebnis ist kein einzelner statischer Fahrzyklus, sondern ein **parametrierbares Simulationswerkzeug**, mit dem dieselbe reale Route unter unterschiedlichen Annahmen betrachtet und verglichen werden kann.

## Hintergrund und Motivation

Für Simulationen von Fahrzeugen oder Antrieben werden häufig Geschwindigkeitsprofile benötigt. Standardisierte Fahrzyklen sind gut vergleichbar, bilden aber eine konkrete reale Straße mit ihren Kurven, Geschwindigkeitsbeschränkungen, Steigungen und Verkehrselementen nur eingeschränkt ab.

Umgekehrt liefern Routing- und Kartendaten zwar eine reale Strecke, aber normalerweise noch keinen technisch nutzbaren Geschwindigkeits- und Lastverlauf.

Die Anwendung soll diese Lücke schließen. Sie erzeugt aus frei gewählten OSM-Routen eine reproduzierbare Grundlage für Fahrverlaufs- und Lastsimulationen, ohne dass für jede Strecke zunächst eine reale Messfahrt erforderlich ist.

Dabei liegt der Schwerpunkt bewusst auf einer **lokalen, nachvollziehbaren und veränderbaren Simulation**. Die verwendeten Fahrerprofile sind technische Modellszenarien. Sie sind keine empirischen Aussagen über reale Personengruppen.

## Welche Problemstellungen kann die Anwendung adressieren?

### 1. Von einer realen Route zu einem Geschwindigkeitsprofil

Eine Liniengeometrie allein reicht für viele Fahrzeugberechnungen nicht aus. Die Anwendung kombiniert unter anderem Straßenlimits, Kurvengeometrie, Fahrerparameter, Beschleunigungs- und Bremsgrenzen sowie erkannte OSM-Verkehrssignale zu einem zeitabhängigen Fahrverlauf.

Damit kann beispielsweise untersucht werden, wie sich eine reale Landstraßen-, Stadt- oder Autobahnroute dynamisch von einem standardisierten Fahrzyklus unterscheidet.

### 2. Vergleich unterschiedlicher Fahrweisen

Dieselbe Strecke kann mit unterschiedlichen Fahrerparametern simuliert werden. Dadurch lassen sich beispielsweise Auswirkungen von

- gewünschter Reisegeschwindigkeit,
- Beschleunigungs- und Bremsverhalten,
- Kurvendynamik,
- Geschwindigkeitsabweichungen,
- Fahrerrauschen,
- Verhalten nach Kurven oder
- optionalen Überholmanövern

auf Fahrzeit, Geschwindigkeit, Beschleunigung und Belastung vergleichen.

Die mitgelieferten Presets dienen dabei als technische Ausgangspunkte und können vollständig angepasst werden.

### 3. Einfluss von Fahrzeug- und Anhängerparametern

Aus Geschwindigkeit, Beschleunigung und Höhenprofil wird die Radleistung aufgeteilt in Beiträge für

- Beschleunigung,
- Steigung bzw. Gefälle,
- Rollwiderstand,
- Luftwiderstand und
- optional einen Anhänger.

Damit können Parameterstudien durchgeführt werden, zum Beispiel zum Einfluss von Fahrzeugmasse, Luftwiderstand, Rollwiderstand oder Anhängerbetrieb.

### 4. Abschätzung von Energiebedarf und Rekuperationspotenzial

Durch Integration der Radleistung werden Antriebsenergie, negative Radarbeit bzw. ideales Rekuperationspotenzial und eine Nettoenergie berechnet.

Das ermöglicht insbesondere **relative Vergleiche** zwischen Routen, Fahrweisen oder Fahrzeugparametern. Die aktuelle Energiebilanz ist bewusst ein Radleistungsmodell und noch kein vollständiges Batterie-, Motor- oder Wirkungsgradmodell.

### 5. Analyse von Steigungen und topografischem Einfluss

Das Höhenprofil wird automatisch aus Geländedaten ergänzt. Dadurch lässt sich sichtbar machen, welchen Einfluss Steigungen und Gefälle auf Geschwindigkeit, Radleistung und Energie haben.

Das ist beispielsweise für Gebirgsstrecken oder längere Überlandfahrten relevant, bei denen reine 2D-Routingdaten die Belastung nur unvollständig beschreiben würden.

### 6. Erzeugung von Lastkollektiven aus realen Strecken

Aus dem simulierten Fahrverlauf kann ein kumuliertes Lastkollektiv der Radleistung erzeugt werden. Positive und negative Leistungsanteile werden getrennt dargestellt.

Damit kann eine Route nicht nur als zeitlicher Verlauf betrachtet werden, sondern auch hinsichtlich der Häufigkeit und Dauer unterschiedlicher Leistungsniveaus.

### 7. Reproduzierbare Simulation ohne Messfahrt

Für frühe Entwicklungs- oder Konzeptphasen existiert häufig noch kein Messfahrzeug oder keine aufgezeichnete GPS-Fahrt. Mit der Anwendung können trotzdem reale Straßenverläufe als Grundlage für erste Simulationen verwendet werden.

Eine reale Messung wird dadurch nicht grundsätzlich ersetzt. Das Werkzeug eignet sich vielmehr dazu, Varianten vorzubereiten, Hypothesen zu untersuchen und relevante Strecken oder Parameter für spätere Messungen einzugrenzen.

### 8. Lokale Arbeit mit großen Geodaten

OSM-, Routing- und Höhendaten werden lokal gecacht. Nach der Vorbereitung eines Gebiets können Routing und Simulation weitgehend mit den lokalen Daten durchgeführt werden.

Das ist besonders nützlich, wenn große Datensätze nicht bei jedem Programmstart erneut geladen werden sollen oder wenn mit reproduzierbaren Datenständen gearbeitet werden soll.

## Typische Anwendungsfälle

Die Anwendung kann beispielsweise als Grundlage dienen für:

- virtuelle Fahrzyklus-Erzeugung auf frei gewählten realen Routen,
- Vergleich von Fahrer- und Fahrzeugparametern,
- Abschätzung von Radleistungs- und Energieverläufen,
- Untersuchung von Gebirgs-, Stadt-, Landstraßen- und Autobahnstrecken,
- Vorauswahl interessanter Strecken für reale Messfahrten,
- Parameterstudien für Fahrzeug- oder Anhängerkonzepte,
- Erzeugung von Lastkollektiven für nachgelagerte Berechnungen,
- Plausibilitäts- und Sensitivitätsanalysen sowie
- Lehre, Forschung und prototypische Entwicklungsarbeiten rund um Fahrzeug-, Routing- und Geodaten.

## Was die Anwendung bewusst nicht ist

Die Anwendung ist ein technisches Simulations- und Analysewerkzeug und kein sicherheitskritisches Navigationssystem.

Sie berücksichtigt derzeit insbesondere **keine Live-Verkehrslage, keine aktuellen Straßensperrungen und keine garantierte reale Ampelphase**. Ampelpositionen werden ausschließlich aus tatsächlich erkannten OSM-Verkehrssignalen übernommen; es werden keine künstlichen Ampeln erzeugt.

Auch die Energieberechnung ist keine vollständige Fahrzeugverbrauchssimulation: Wirkungsgradkennfelder von Motor, Getriebe, Wechselrichter oder Batterie, Nebenverbraucher, thermische Effekte sowie Rekuperationsgrenzen sind im aktuellen Grundmodell nicht vollständig enthalten.

Das verwendete Höhenmodell beschreibt die Geländeoberfläche. Dadurch können Tunnel und Brücken lokal ein falsches Fahrbahnhöhenniveau erhalten. Ergebnisse auf entsprechenden Strecken müssen daher mit dieser Einschränkung interpretiert werden.

## Typischer Workflow

1. Start, Ziel und optional Zwischenpunkte auf der Karte setzen.
2. Die Anwendung erkennt automatisch das passende OSM-Datengebiet.
3. Vorhandene Routingdaten werden verwendet; fehlende Daten werden bei Bedarf vorbereitet.
4. Die Route wird lokal berechnet.
5. Benötigte Höhendaten werden automatisch ergänzt.
6. Im Simulations-Tab Fahrer- und Fahrzeugparameter wählen oder verändern.
7. Geschwindigkeits-, Beschleunigungs-, Höhen-, Leistungs- und Energieverläufe analysieren.
8. Optional Varianten vergleichen, Lastkollektive betrachten und Ergebnisse exportieren.

## Installation / Einrichtung unter Windows

Die Anwendung benötigt **Python 3.11 (64 Bit)**. Adminrechte sind nicht erforderlich. Das Setup legt eine lokale `.venv` im Projektordner an.

Normale Einrichtung:

```powershell
.\scripts\setup_windows.ps1
```

Danach starten:

```powershell
& ".\.venv\Scripts\python.exe" -m qt_route_selector
```

### Enterprise-PC ohne Internet / hinter Firewall

Der Enterprise-PC braucht nur **Python 3.11 (64 Bit)**. Alle Python-Pakete sowie OSM-, Routing- und Höhendaten können vorher auf einem anderen Windows-PC vorbereitet und anschließend komplett kopiert werden.

#### 1. Auf einem Windows-PC mit Internet vorbereiten

Im Projektordner ausführen:

```powershell
.\scripts\build_offline_dependencies.ps1
```

Dadurch entsteht der Ordner:

```text
<Repository>\wheelhouse\
```

Er enthält alle Python-Pakete für die Offline-Installation.

Danach in der Anwendung einmal die Gebiete bzw. Routen vorbereiten, die später auf dem Enterprise-PC benötigt werden. Die bereits heruntergeladenen Daten liegen hier:

```text
%LOCALAPPDATA%\GPS-Routenplaner\data\
```

Darin befinden sich je nach vorbereitetem Gebiet unter anderem:

```text
OSM-PBF
POLY
Routing-GPKG
Höhendaten / DEM
```

#### 2. Auf den Enterprise-PC kopieren

Zwei Dinge kopieren:

1. den **gesamten Projektordner inklusive `wheelhouse`**
2. den kompletten Ordner

```text
%LOCALAPPDATA%\GPS-Routenplaner\data\
```

Die `.venv` muss nicht kopiert werden.

Auf dem Enterprise-PC die Geodaten wieder hier ablegen:

```text
%LOCALAPPDATA%\GPS-Routenplaner\data\
```

Der Zielordner kann bei Bedarf einfach angelegt werden.

#### 3. Auf dem Enterprise-PC installieren

PowerShell im kopierten Projektordner öffnen und ausführen:

```powershell
.\scripts\setup_windows.ps1
```

Das Setup erkennt das `wheelhouse` automatisch und installiert die Python-Pakete **nur aus den lokalen Dateien**. Für die Installation wird kein Zugriff auf PyPI benötigt.

#### 4. Starten

```powershell
& ".\.venv\Scripts\python.exe" -m qt_route_selector
```

Damit arbeitet die Anwendung mit den mitkopierten lokalen OSM-, Routing- und Höhendaten.

> Wichtig: Für Gebiete, deren PBF-/Routing-/Höhendaten nicht mitkopiert wurden, kann die Anwendung normalerweise einen Download anfordern. Hinter einer Firewall schlägt dieser Download gegebenenfalls fehl. Deshalb alle benötigten Gebiete vorher auf dem Internet-PC vorbereiten und den kompletten `data`-Ordner kopieren.

> Falls die Unternehmensrichtlinie die Ausführung von `pip` selbst verbietet, muss die lokale Installation durch die IT freigegeben oder zentral bereitgestellt werden. Das Offline-Setup verwendet `pip` nur lokal und greift nicht auf das Internet zu.

### Wenn PowerShell die Aktivierung blockiert

Eine Aktivierung der `.venv` ist nicht notwendig. Die Anwendung kann immer direkt gestartet werden:

```powershell
& ".\.venv\Scripts\python.exe" -m qt_route_selector
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
wheelhouse/               # optional, lokal, für Offline-Installation
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

scripts/
  setup_windows.ps1            # .venv anlegen, Dependencies installieren, optional starten
  build_offline_dependencies.ps1 # vollständiges Windows-x64-Wheelhouse vorbereiten
  cleanup_legacy_workspace.ps1 # alte lokale Workspace-Daten sicher migrieren
```

Die Dateien unter `_internal/` sind Implementierungsdetails. Externer Code sollte nur die öffentlichen Module unter `qt_route_selector` verwenden.

## Abhängigkeiten

`requirements.txt` enthält die für den aktuellen Stand getesteten Python-Versionen. `scripts/setup_windows.ps1` installiert sie automatisch in `.venv` und prüft danach zentrale Laufzeitmodule wie PySide6, PyQtGraph, NumPy, GeoPandas und Rasterio.

Für Offline-Rechner erzeugt `scripts/build_offline_dependencies.ps1` aus derselben `requirements.txt` ein vollständiges lokales `wheelhouse`. Der Ordner ist bewusst per `.gitignore` ausgeschlossen, da die Binärpakete groß, plattformspezifisch und jederzeit reproduzierbar sind. Wenn sich `requirements.txt` ändert, sollte das Wheelhouse neu erzeugt werden.

## Tests

Mit aktivierter `.venv`:

```powershell
python -m unittest discover -s qt_route_selector\tests -v
```

GitHub Actions installiert `requirements.txt`, kompiliert das Paket und führt dieselben Unit-/GUI-Smoke-Tests im Qt-Offscreen-Modus aus.

## Generierte Dateien

Laufzeitdaten gehören nicht in Git. Die `.gitignore` schließt `.venv`, das lokal erzeugte `wheelhouse`, Runtime-Ausgaben, Geodaten und die Verzeichnisnamen des alten Prototype-Workspaces aus, damit sie bei bestehenden Checkouts nicht versehentlich committed werden.
