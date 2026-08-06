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

## Windows Eingabeaufforderung (`cmd.exe`)

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Nur die Qt-Routenanwendung installieren

Diese Variante installiert PySide6 sowie die für das lokale Routing benötigten Geo- und Graphbibliotheken, aber nicht die übrigen GPX-/PBF-Hilfsprogramme des Gesamtprojekts:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
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

Die Anwendung akzeptiert vorbereitete FlatGeobuf-/GeoPackage-Daten sowie direkt eine `.osm.pbf`. Für wiederholte Berechnungen ist ein räumlich indiziertes FGB- oder GeoPackage performanter.

## Tests ausführen

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s qt_route_selector\tests -v
```

Weitere Hinweise zur Bedienung und zum JSON-Ausgabeformat stehen in `qt_route_selector/README.md`.
