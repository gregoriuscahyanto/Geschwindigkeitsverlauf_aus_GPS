from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _matlab_quote(value: str | Path) -> str:
    """Return a MATLAB single-quoted character vector literal."""

    return "'" + str(value).replace("'", "''") + "'"


def _registry_matlab_candidates() -> list[Path]:
    """Return MATLAB executables registered on Windows without requiring admin rights."""

    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows only
        return []

    candidates: list[Path] = []
    registry_paths = (
        r"SOFTWARE\MathWorks\MATLAB",
        r"SOFTWARE\WOW6432Node\MathWorks\MATLAB",
    )
    for registry_path in registry_paths:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, registry_path) as root_key:
                index = 0
                releases: list[str] = []
                while True:
                    try:
                        releases.append(winreg.EnumKey(root_key, index))
                        index += 1
                    except OSError:
                        break
                for release in sorted(releases, reverse=True):
                    try:
                        with winreg.OpenKey(root_key, release) as release_key:
                            matlab_root, _ = winreg.QueryValueEx(release_key, "MATLABROOT")
                    except OSError:
                        continue
                    executable = Path(str(matlab_root)) / "bin" / "matlab.exe"
                    if executable.is_file():
                        candidates.append(executable)
        except OSError:
            continue
    return candidates


def find_matlab_executable() -> Path | None:
    """Find a local MATLAB executable for non-interactive native MAT creation."""

    explicit = os.environ.get("MATLAB_EXE", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path.resolve()

    matlab_root = os.environ.get("MATLAB_ROOT", "").strip()
    if matlab_root:
        name = "matlab.exe" if os.name == "nt" else "matlab"
        path = Path(matlab_root).expanduser() / "bin" / name
        if path.is_file():
            return path.resolve()

    command = shutil.which("matlab") or shutil.which("matlab.exe")
    if command:
        return Path(command).resolve()

    registry_candidates = _registry_matlab_candidates()
    if registry_candidates:
        return registry_candidates[0]

    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        matlab_parent = Path(program_files) / "MATLAB"
        if matlab_parent.is_dir():
            installations = sorted(matlab_parent.glob("R*"), reverse=True)
            for installation in installations:
                executable = installation / "bin" / "matlab.exe"
                if executable.is_file():
                    return executable.resolve()
    return None


def _build_matlab_statement(raw_path: Path, output_path: Path) -> str:
    """Build MATLAB code that saves only native tables/timetables in the final MAT."""

    raw = _matlab_quote(raw_path)
    output = _matlab_quote(output_path)
    return "".join(
        [
            f"S=load({raw});",
            # Distance-aligned route data.
            "distanceNames=string(S.distance_columns(:))';",
            "distanceNames=matlab.lang.makeUniqueStrings(matlab.lang.makeValidName(distanceNames));",
            "distanceTable=array2table(S.distance_table,'VariableNames',cellstr(distanceNames));",
            # Time-aligned driving data as table + timetable.
            "timeNames=string(S.time_columns(:))';",
            "timeNames=matlab.lang.makeUniqueStrings(matlab.lang.makeValidName(timeNames));",
            "driveTable=array2table(S.time_table,'VariableNames',cellstr(timeNames));",
            "if ~ismember('time_s',driveTable.Properties.VariableNames),error('GPS-Routenplaner:MissingTime','time_s fehlt im MAT-Export.');end;",
            "rowTime=seconds(driveTable.time_s);",
            "driveTimetable=table2timetable(removevars(driveTable,'time_s'),'RowTimes',rowTime);",
            "driveTimetable.Properties.DimensionNames{1}='Time';",
            # Power/energy view.
            "wantedPower={'total_kw','acceleration_kw','grade_kw','rolling_kw','air_kw','trailer_kw','traction_power_kw','recuperation_power_kw','cumulative_traction_energy_kwh','cumulative_recuperation_energy_kwh','cumulative_net_energy_kwh'};",
            "powerNames=wantedPower(ismember(wantedPower,driveTimetable.Properties.VariableNames));",
            "powerTimetable=driveTimetable(:,powerNames);",
            # Traffic-light tables.
            "trafficLightTable=table();",
            "if isfield(S,'events')&&isfield(S.events,'traffic_lights')&&~isempty(S.events.traffic_lights),trafficNames=string(S.events.traffic_lights_columns(:))';trafficNames=matlab.lang.makeUniqueStrings(matlab.lang.makeValidName(trafficNames));trafficLightTable=array2table(S.events.traffic_lights,'VariableNames',cellstr(trafficNames));end;",
            "trafficLightIntervalTable=table();",
            "if isfield(S,'events')&&isfield(S.events,'traffic_light_intervals')&&~isempty(S.events.traffic_light_intervals),intervalNames=string(S.events.traffic_light_intervals_columns(:))';intervalNames=matlab.lang.makeUniqueStrings(matlab.lang.makeValidName(intervalNames));trafficLightIntervalTable=array2table(S.events.traffic_light_intervals,'VariableNames',cellstr(intervalNames));end;",
            # Original route points.
            "routeCoordinateTable=table();",
            "if isfield(S,'route_coordinates')&&~isempty(S.route_coordinates),coordinateNames=string(S.route_coordinate_columns(:))';coordinateNames=matlab.lang.makeUniqueStrings(matlab.lang.makeValidName(coordinateNames));routeCoordinateTable=array2table(S.route_coordinates,'VariableNames',cellstr(coordinateNames));end;",
            # Signed cumulative load collective as one clean long-format table.
            "loadCollectiveTable=table(strings(0,1),zeros(0,1),zeros(0,1),'VariableNames',{'branch','time_share_pct','load_kw'});",
            'if isfield(S,\'load_collective\'),px=[];py=[];nx=[];ny=[];if isfield(S.load_collective,\'positive_time_share_pct\'),px=S.load_collective.positive_time_share_pct(:);end;if isfield(S.load_collective,\'positive_load\'),py=S.load_collective.positive_load(:);end;if isfield(S.load_collective,\'negative_time_share_pct\'),nx=S.load_collective.negative_time_share_pct(:);end;if isfield(S.load_collective,\'negative_load\'),ny=S.load_collective.negative_load(:);end;np=min(numel(px),numel(py));nn=min(numel(nx),numel(ny));px=px(1:np);py=py(1:np);nx=nx(1:nn);ny=ny(1:nn);branch=[repmat("positive",np,1);repmat("negative",nn,1)];loadCollectiveTable=table(branch,[px;nx],[py;ny],\'VariableNames\',{\'branch\',\'time_share_pct\',\'load_kw\'});end;',
            # Scalar settings/results as one-row tables.
            "parametersTable=table();if isfield(S,'parameters')&&isstruct(S.parameters),parametersTable=struct2table(S.parameters,'AsArray',true);end;",
            "summaryTable=table();if isfield(S,'summary')&&isstruct(S.summary),summaryTable=struct2table(S.summary,'AsArray',true);end;",
            "metadataTable=table();if isfield(S,'metadata')&&isstruct(S.metadata),metadataTable=struct2table(S.metadata,'AsArray',true);end;",
            # Keep complete JSON mirrors without exposing strings as top-level variables.
            'routeJson="";simulationJson="";eventsJson="";comparisonJson="";if isfield(S,\'route_json\'),routeJson=string(S.route_json);end;if isfield(S,\'simulation_json\'),simulationJson=string(S.simulation_json);end;if isfield(S,\'events_json\'),eventsJson=string(S.events_json);end;if isfield(S,\'comparison_json\'),comparisonJson=string(S.comparison_json);end;rawContextTable=table(routeJson,simulationJson,eventsJson,comparisonJson,\'VariableNames\',{\'route_json\',\'simulation_json\',\'events_json\',\'comparison_json\'});',
            # Units for convenient MATLAB analysis.
            "distanceUnits=containers.Map({'distance_m','latitude_deg','longitude_deg','elevation_m','curve_radius_m','grade_pct','road_limit_kmh','surface_limit_kmh','curve_limit_kmh','base_target_kmh','planned_speed_kmh','actual_speed_kmh','noise_kmh'},{'m','deg','deg','m','m','%','km/h','km/h','km/h','km/h','km/h','km/h','km/h'});",
            "du=repmat({''},1,width(distanceTable));for k=1:width(distanceTable),n=distanceTable.Properties.VariableNames{k};if isKey(distanceUnits,n),du{k}=distanceUnits(n);end;end;distanceTable.Properties.VariableUnits=du;",
            "timeUnits=containers.Map({'distance_m','latitude_deg','longitude_deg','elevation_m','curve_radius_m','speed_kmh','target_kmh','acceleration_mps2','road_limit_kmh','surface_limit_kmh','curve_limit_kmh','grade_pct','total_kw','acceleration_kw','grade_kw','rolling_kw','air_kw','trailer_kw','traction_power_kw','recuperation_power_kw','cumulative_traction_energy_kwh','cumulative_recuperation_energy_kwh','cumulative_net_energy_kwh'},{'m','deg','deg','m','m','km/h','km/h','m/s^2','km/h','km/h','km/h','%','kW','kW','kW','kW','kW','kW','kW','kW','kWh','kWh','kWh'});",
            "tu=repmat({''},1,width(driveTimetable));for k=1:width(driveTimetable),n=driveTimetable.Properties.VariableNames{k};if isKey(timeUnits,n),tu{k}=timeUnits(n);end;end;driveTimetable.Properties.VariableUnits=tu;",
            "driveTable.Properties.VariableUnits=[{'s'},tu];",
            "if ~isempty(powerNames),powerTimetable.Properties.VariableUnits=driveTimetable.Properties.VariableUnits(ismember(driveTimetable.Properties.VariableNames,powerNames));end;",
            "loadCollectiveTable.Properties.VariableUnits={'','%','kW'};",
            # The final MAT intentionally contains no raw matrices, structs or standalone strings.
            f"save({output},'distanceTable','driveTable','driveTimetable','powerTimetable','loadCollectiveTable','trafficLightTable','trafficLightIntervalTable','routeCoordinateTable','parametersTable','summaryTable','metadataTable','rawContextTable','-v7.3');",
        ]
    )


def convert_to_native_matlab_tables(
    raw_path: str | Path,
    output_path: str | Path,
    *,
    matlab_executable: str | Path | None = None,
    timeout_s: int = 300,
) -> Path:
    """Create a MAT file whose top-level variables are only table/timetable objects.

    Python MAT writers can create MATLAB-compatible staging arrays and structs,
    but native ``table``/``timetable`` objects are MATLAB classes. MATLAB is
    therefore invoked non-interactively with ``-batch`` to construct the final
    file. The staging data is never copied into the final MAT file.
    """

    raw = Path(raw_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    if not raw.is_file():
        raise FileNotFoundError(f"Temporärer MAT-Rohdatensatz fehlt: {raw}")

    if matlab_executable is None:
        executable = find_matlab_executable()
    else:
        executable = Path(matlab_executable).expanduser().resolve()
    if executable is None or not executable.is_file():
        raise RuntimeError(
            "Für einen direkten MAT-Export mit echten MATLAB table/timetable-Variablen "
            "muss MATLAB auf diesem PC installiert sein. matlab.exe wurde nicht gefunden.\n\n"
            "Falls MATLAB an einem ungewöhnlichen Ort installiert ist, kann die Umgebungsvariable "
            "MATLAB_EXE auf den vollständigen Pfad zu matlab.exe gesetzt werden."
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    statement = _build_matlab_statement(raw, output)
    try:
        completed = subprocess.run(
            [str(executable), "-batch", statement],
            capture_output=True,
            text=True,
            timeout=max(30, int(timeout_s)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"MATLAB hat den Export nicht innerhalb von {timeout_s} Sekunden abgeschlossen."
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"MATLAB konnte nicht gestartet werden: {exc}") from exc

    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "Unbekannter MATLAB-Fehler").strip()
        if len(details) > 3000:
            details = details[-3000:]
        raise RuntimeError(f"MATLAB konnte die native MAT-Datei nicht erzeugen.\n\n{details}")
    if not output.is_file():
        raise RuntimeError("MATLAB meldete Erfolg, hat aber keine MAT-Datei erzeugt.")
    return output
