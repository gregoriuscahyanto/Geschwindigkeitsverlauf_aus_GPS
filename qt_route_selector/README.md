# Qt-Routenplaner und Live-Geschwindigkeitsverlauf

Die Anwendung berechnet lokale OSM-Routen und erzeugt daraus einen live einstellbaren Geschwindigkeits-, Höhen- und Fahrwiderstandsverlauf. Der normale Workflow benötigt keine manuelle Gebiets- oder Straßendateiauswahl.

## Start

```powershell
python -m pip install -r qt_route_selector\requirements.txt
python qt_route_selector\complete_app.py
```

## Oberfläche

Die Anwendung besitzt drei Tabs:

1. **Route und Karte** – Start/Ziel/Zwischenziele setzen und Route berechnen.
2. **Geschwindigkeitsverlauf** – Fahrer-, Fahrzeug- und Fahrwiderstandsparameter sowie Vergleich mehrerer Konfigurationen.
3. **Datenabdeckung** – lokale POLY-, PBF- und GPKG-Abdeckung auf einer Karte anzeigen.

Die beiden schweren Tabs 2 und 3 werden erst beim Öffnen initialisiert. Währenddessen zeigt die Anwendung einen indeterminierten Ladebalken.

## Automatische Gebiets- und Datenwahl

Nach Start und Ziel erkennt die App selbst das kleinste passende unterstützte Gebiet. Unterstützt werden unter anderem:

- Baden-Württemberg
- Bayern
- Hessen
- Schweiz
- Österreich (gesamt)
- DACH für grenzüberschreitende Routen

Fehlende OSM-PBFs werden bei Bedarf geladen, als lokaler Routingindex (`*.gpkg`) vorbereitet und danach wiederverwendet. Vorhandene Daten werden beim nächsten Start automatisch erkannt. Die manuelle Straßendateiauswahl bleibt nur als Experten-Fallback bestehen.

## Höhenmodelle

Höhen werden automatisch aus den für die Route vorbereiteten DEM-Daten gelesen. In Tab 2 gibt es deshalb keine manuelle DEM-Auswahl mehr. Der aktuelle DEM-Status bleibt sichtbar.

Die sichtbare Höhenkurve wird standardmäßig distanzbasiert geglättet. Das Glättungsfenster kann in Metern eingestellt oder mit `0 m` vollständig deaktiviert werden.

Wichtig: Gelände-DGMs beschreiben nicht automatisch die reale Fahrbahnhöhe in langen Tunneln oder auf Brücken. Für eine physikalisch genaue Steigungsleistung müssen solche Abschnitte separat korrigiert werden.

## Geschwindigkeits- und Fahrermodell

Berücksichtigt werden unter anderem:

- Fahrer-Presets und Temperament
- Reisegeschwindigkeit, Bias und absolute Obergrenze
- Beschleunigung, Verzögerung und Ruck
- Kurvenradius und maximale Querbeschleunigung
- Nach-Kurven-Überschwingen
- Straßenbelag
- ausschließlich reale OSM-Ampelstopps
- Überholvorgänge
- korreliertes Fahrerrauschen
- Fahrzeug- und Anhängermasse

Die Geschwindigkeits-Y-Achse orientiert sich am realen Straßenlimit plus Reserve und nicht an mathematisch sehr hohen Kurvenlimit-Spitzen.

## Vier synchronisierte Zeit-/Streckenplots

Links liegen vier synchronisierte Plots:

1. Geschwindigkeit
2. Längsbeschleunigung
3. geglättetes Höhenprofil
4. Fahrwiderstandsleistung am Rad

Die gemeinsame X-Achse kann zwischen Zeit und Strecke umgeschaltet werden. Hover-Cursor und Fahrzeugmarker auf der Karte bleiben synchron. Mit **Ansicht zurücksetzen** werden Zoom und Verschiebung aller Plots zurückgesetzt.

Die Legenden liegen fest außerhalb der Datenfläche, sind nicht verschiebbar und können dadurch keine Kurven verdecken oder Einträge abschneiden.

## Fahrwiderstandsleistung

Die Radleistung wird in folgende Beiträge zerlegt:

```text
P_gesamt =
    P_Beschleunigung
  + P_Steigung
  + P_Roll
  + P_Luft
  + P_Anhänger
```

Positiv bedeutet benötigte Antriebsleistung am Rad, negativ Brems-/Schubbetrieb. Einstellbar sind unter anderem Fahrzeug- und Anhängermasse, Rollwiderstand, `cW`, Stirnfläche, Luftdichte und Anhänger-`cW·A`.

## Kumuliertes Lastkollektiv / Lastdauerlinie

Rechts unterhalb der geografischen Karte wird die gesamte Fahrt als kumulierte Lastdauerlinie dargestellt:

- **x-Achse:** kumulierter Zeitanteil in %
- **y-Achse:** Radleistung in kW oder normierte Last
- Darstellung als Linie statt Histogramm

Optional können nur positive Antriebsleistungen ausgewertet und die Zeitanteilsachse logarithmisch dargestellt werden. Das entspricht der üblichen Lastkollektiv-/Dauerlinienbetrachtung aus Schwingungs- und Betriebsfestigkeitsauswertungen.

## Mehrere Konfigurationen vergleichen

Im Bereich **Konfigurationen vergleichen** kann die aktuelle Parametrierung als Snapshot gespeichert werden. Danach können Parameter verändert und weitere Snapshots gespeichert werden.

- Bei **einer** Konfiguration zeigt die Geschwindigkeitsdarstellung weiterhin Straßenlimit, Kurvenlimit, Soll- und Istgeschwindigkeit sowie alle einzelnen Fahrwiderstandsanteile.
- Ab **zwei** Konfigurationen wechselt die Oberfläche automatisch in den Vergleichsmodus. Geschwindigkeit, Längsbeschleunigung, gesamte Fahrwiderstandsleistung und Lastdauerlinie zeigen dann genau eine Linie pro Konfiguration.
- Das Höhenprofil wird nur einmal dargestellt, weil die Route für alle verglichenen Fahrer-/Fahrzeugkonfigurationen identisch ist.

Gespeicherte Vergleichskonfigurationen können wieder in die Eingabefelder geladen oder einzeln/komplett gelöscht werden.

## Technische Mini-Plots

Die Parametergruppen besitzen kompakte, live aktualisierte Vorschauplots:

- **Fahrer:** Sollwert und Fahrerreaktion
- **Kurven:** Radius → Kurvengeschwindigkeit
- **Ampeln:** Bremsen – Halt – Anfahren
- **Überholen:** Geschwindigkeitsverlauf eines Überholmanövers
- **Rauschen:** zeitlich korrelierte Geschwindigkeitsabweichung
- **Fahrzeug:** Roll-/Luft-/Gesamtleistungsbedarf über Geschwindigkeit

Damit wird die Wirkung wichtiger Einstellungen direkt visuell erklärt, ohne lange Hilfetexte lesen zu müssen.

## Datenabdeckung

Tab 3 zeigt nur lokal vorhandene Daten und startet selbst keine großen Downloads. Die unterstützten Gebiete werden nach lokalem Status markiert, z. B. nur POLY-Grenze, OSM-PBF vorhanden oder fertiges Routing-GPKG.

## Export

Über **CSV + JSON exportieren** können die Simulationsergebnisse gespeichert werden.

## Tests

```powershell
python -m unittest discover -s qt_route_selector\tests -v
```

GitHub Actions prüft zusätzlich die lazy geladenen Tabs, die vier synchronisierten Plots, Fahrwiderstand, kumulierte Lastdauerlinie, Vergleichssnapshots, technische Mini-Plots, automatische DEM-Verwendung und die Datenabdeckung.