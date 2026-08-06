# Python-Umgebung einrichten

Empfohlen wird Python 3.11 (64-bit). Die virtuelle Umgebung wird direkt im Repository unter `.venv` angelegt.

## Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Falls die Aktivierung durch die PowerShell-Ausführungsrichtlinie blockiert wird, kann die Umgebung ohne Aktivierung verwendet werden:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe qt_route_selector\main.py
```

## Windows Eingabeaufforderung (`cmd.exe`)

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Nur die Qt-Oberfläche installieren

Für einen ersten Test der Karte ohne die vollständige OSM-/GPX-Pipeline:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r qt_route_selector\requirements.txt
.\.venv\Scripts\python.exe qt_route_selector\main.py
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
