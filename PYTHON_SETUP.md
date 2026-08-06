# Python-Umgebung einrichten

Empfohlen wird Python 3.11 (64 Bit). Die virtuelle Umgebung liegt im Repository unter `.venv`.

## Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r qt_route_selector\requirements.txt
```

Ohne Aktivierung der virtuellen Umgebung:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r qt_route_selector\requirements.txt
```

## Anwendung starten

```powershell
.\.venv\Scripts\python.exe qt_route_selector\complete_app.py
```

Es öffnet sich **ein Fenster mit zwei Tabs**:

1. `Route und Karte`
2. `Geschwindigkeitsverlauf`

Nach einer neuen Routenberechnung wird die Simulation im zweiten Tab automatisch aktualisiert.

## Nach einem Git-Update

Die `.venv` muss nicht neu erstellt werden:

```powershell
git fetch origin
git pull --ff-only origin feature/qt-route-selector
.\.venv\Scripts\python.exe -m pip install -r qt_route_selector\requirements.txt
.\.venv\Scripts\python.exe qt_route_selector\complete_app.py
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s qt_route_selector\tests -v
```
