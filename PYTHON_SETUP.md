# Python-Umgebung einrichten

Empfohlen wird Python 3.11 (64-bit). Die virtuelle Umgebung wird direkt im Repository unter `.venv` angelegt und ist über `.gitignore` vom Commit ausgeschlossen.

## Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Falls die Aktivierung durch die PowerShell-Ausführungsrichtlinie blockiert wird, kann die Umgebung ohne Aktivierung verwendet werden:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Nur die Qt-Routenanwendung installieren

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r qt_route_selector\requirements.txt
```

Nach einem Git-Update muss `.venv` nicht neu erstellt werden. Die Requirements erneut zu installieren reicht aus:

```powershell
.\.venv\Scripts\python.exe -m pip install -r qt_route_selector\requirements.txt
```

## Anwendung starten

Mit aktivierter virtueller Umgebung:

```powershell
python qt_route_selector\main.py
```

Ohne Aktivierung:

```powershell
.\.venv\Scripts\python.exe qt_route_selector\main.py
```

Die Anwendung verwendet standardmäßig die schnelle Online-OSM-Karte und schaltet im Modus **Automatisch** bei fehlender Verbindung auf die lokale Vektorkarte um. Das Routing verwendet immer die ausgewählte lokale `.osm.pbf`, `.gpkg`, `.fgb`, `.geojson` oder `.shp`.

Bei einer großen PBF empfiehlt sich nach der Auswahl die einmalige Schaltfläche **PBF-Schnellindex erstellen**. Sie erzeugt ein räumlich indiziertes `*_routing.gpkg`, das anschließend automatisch verwendet wird.

## Tests ausführen

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s qt_route_selector\tests -v
```

Weitere Hinweise zu Kartenmodi, Zwischenzielen, Routingprofilen und dem Schnellindex stehen in `qt_route_selector/README.md`.
