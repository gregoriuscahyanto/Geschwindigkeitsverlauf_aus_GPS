function merge_pbf
% callMergePBF
% - Per uigetfile >=2 .osm.pbf-Dateien wählen (gleiches Dialogverzeichnis)
% - Zielname = Kombination der Basisnamen (z.B. "baden-wuerttemberg+bayern.osm.pbf")
% - Speichern im gleichen Ordner wie die Eingaben
% - Aufruf von merge_pbf_py.py (pyosmium-only)
    
    % Python venv anpassen
    pyexe = patch_pyvenv_home("3.10");   % oder ohne Argument -> Minor aus pyvenv.cfg lesen
    fprintf("Verwende venv Python: %s\n", pyexe);

    %% Projektpfade
    baseDir = string(fileparts(mfilename('fullpath')));
    if baseDir == "", baseDir = string(pwd); end
    dbDir   = fullfile(baseDir, "database");
    if ~isfolder(dbDir), mkdir(dbDir); end

    pyMerge = fullfile(baseDir, "merge_pbf_py.py");
    assert(isfile(pyMerge), "Python-Merger nicht gefunden: %s", pyMerge);

    %% Python-Interpreter (.venv bevorzugt)
    if ispc
        pyexe = fullfile(baseDir, ".venv", "Scripts", "python.exe");
    else
        pyexe = fullfile(baseDir, ".venv", "bin", "python");
    end
    if ~isfile(pyexe)
        pe = string(getenv("PYTHON"));
        if pe ~= "" && isfile(pe)
            pyexe = pe;
        else
            pyexe = "python"; % im PATH
        end
        warning('Kein .venv-Python gefunden – verwende: %s', pyexe);
    end

    %% Eingaben: >=2 PBFs auswählen
    [fns, fp] = uigetfile({'*.pbf','OSM PBF (*.pbf)'}, ...
                          'Wähle ZWEI ODER MEHR OSM PBFs zum Mergen …', ...
                          dbDir, 'MultiSelect','on');
    if isequal(fns,0)
        fprintf('Abgebrochen.\n'); return;
    end
    if ischar(fns), fns = {fns}; end
    if numel(fns) < 2
        errordlg('Bitte mindestens zwei .pbf-Dateien auswählen.','Zu wenige Dateien');
        return;
    end

    inFiles = strings(numel(fns),1);
    bases   = strings(numel(fns),1);
    for i = 1:numel(fns)
        absPath   = string(java.io.File(fullfile(fp, fns{i})).getCanonicalPath());
        inFiles(i) = absPath;
        bases(i)   = local_base_name(string(fns{i}));
    end

    %% Ziel: gleicher Ordner, kombinierter Name
    comboBase = strjoin(bases, "+");
    outPbf    = string(java.io.File(fullfile(fp, comboBase + ".osm.pbf")).getCanonicalPath());

    %% Existenzcheck
    overwriteFlag = "--overwrite";
    if isfile(outPbf)
        btn = questdlg(sprintf('Zieldatei existiert bereits:\n%s\nÜberschreiben?', outPbf), ...
                       'Datei existiert', 'Überschreiben','Abbrechen','Überschreiben');
        if ~strcmp(btn,'Überschreiben')
            fprintf('Abgebrochen.\n'); return;
        end
    end

    %% Merge ausführen
    setenv('PYTHONUNBUFFERED','1'); setenv('PYTHONIOENCODING','utf-8');

    % Korrektes Quoten (doppelte Anführungszeichen in String-Literals)
    q = @(s) """" + string(s) + """";   % <- WICHTIG: keine Backslashes verwenden

    % Kommando bauen
    cmdParts = [ q(pyexe), q(pyMerge), q(inFiles.'), "-o", q(outPbf), overwriteFlag ];
    cmd = strjoin(cmdParts, ' ') + " 2>&1";

    fprintf('[MERGE] %s\n', cmd);
    st = system(cmd);
    if st ~= 0
        error('Merge fehlgeschlagen (Exitcode %d). Siehe obige Fehlermeldung.', st);
    end

    fprintf('[OK] Merge erfolgreich: %s\n', outPbf);
end

function b = local_base_name(fname)
% Basisname ohne Endungen (.osm.pbf | .pbf) und ohne "-latest"
    f = string(fname);
    if endsWith(f, ".osm.pbf", 'IgnoreCase',true)
        f = extractBefore(f, strlength(f) - strlength(".osm.pbf") + 1);
    elseif endsWith(f, ".pbf", 'IgnoreCase',true)
        f = extractBefore(f, strlength(f) - strlength(".pbf") + 1);
    end
    f = regexprep(f, '(-latest)$', '', 'ignorecase');
    b = f;
end
