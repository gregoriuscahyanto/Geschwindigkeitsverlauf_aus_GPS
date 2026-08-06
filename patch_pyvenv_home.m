function pyexe = patch_pyvenv_home_v2(pyMinor)
%PATCH_PYVENV_HOME  Setzt .venv/pyvenv.cfg->home auf passende System-Python;
% Fallback: ersetzt nur den USER-Teil in 'home = C:\Users\<USER>\...'
%
% pyMinor optional: "3.10", "3.11", ...
% Rückgabe: Pfad zum venv-Python

    baseDir = string(pwd);
    if ispc
        pyexe = fullfile(baseDir, ".venv", "Scripts", "python.exe");
    else
        pyexe = fullfile(baseDir, ".venv", "bin", "python");
    end
    cfg = fullfile(baseDir, ".venv", "pyvenv.cfg");

    assert(isfile(cfg),  "pyvenv.cfg nicht gefunden: %s", cfg);
    assert(isfile(pyexe),"Venv-Python nicht gefunden: %s", pyexe);

    % --- Ziel-Minor ermitteln (falls nicht übergeben)
    if nargin < 1 || strlength(pyMinor)==0
        pyMinor = detect_minor_from_cfg(cfg);   % "3.10"
        assert(strlength(pyMinor)>0, ...
            'Konnte Python-Minor nicht aus pyvenv.cfg ermitteln. Übergib z.B. "3.10".');
    end

    % --- 1) try: System-Python home ermitteln
    sysHome = detect_system_python_home(pyMinor);

    if strlength(sysHome)>0 && isfolder(sysHome)
        % normaler Weg: komplettes home setzen
        sysHome = replace(sysHome, "\", "\\");  % Backslashes verdoppeln für INI
        set_pyvenv_home(sysHome, cfg);
        fprintf('[OK] pyvenv.cfg aktualisiert (voll): home = %s\n', sysHome);
    else
        % --- 2) Fallback: nur den Benutzerteil austauschen
        user = string(getenv('USERNAME'));
        fallback_replace_username_in_home(cfg, user);
        fprintf('[OK] pyvenv.cfg aktualisiert (Fallback USER): USER=%s\n', user);
    end
end

% ---------- Helper ----------

function s = detect_minor_from_cfg(cfg)
    s = "";
    txt = fileread(cfg);
    tok = regexp(txt, '^\s*version\s*=\s*([0-9]+\.[0-9]+)\.[0-9]+', ...
                 'tokens', 'once', 'lineanchors');
    if ~isempty(tok), s = string(tok{1}); end
end

function home = detect_system_python_home(pyMinor)
% Liefert sys.base_prefix für die gewünschte Minor (z.B. "3.10")
    if ispc
        home = detect_system_python_home_win(pyMinor);
    else
        % Unix/macOS
        cmd = "python" + pyMinor + " -c " + quote("import sys; print(sys.base_prefix)");
        [st,out] = system(cmd);
        if st==0
            home = canon_dir(strtrim(string(out)));
            if strlength(home)>0, return; end
        end
        cmd = "python3 -c " + quote("import sys; print(sys.version.split()[0]); print(sys.base_prefix)");
        [st,out] = system(cmd);
        if st==0
            lines = splitlines(string(out));
            if numel(lines)>=2 && startsWith(strtrim(lines(1)), pyMinor + ".")
                home = canon_dir(strtrim(lines(2))); return;
            end
        end
        home = "";
    end
end

function home = detect_system_python_home_win(pyMinor)
    % 1) py -<minor>
    [st,out] = run_cmd("py -" + pyMinor + " -c " + quote("import sys; print(sys.base_prefix)"));
    if st==0 && strlength(strtrim(out))>0
        home = canon_dir(strtrim(out)); if strlength(home)>0, return; end
    end
    % 2) where py
    [st,out] = run_cmd("where py");
    if st==0
        for p = splitlines(strtrim(out)).'
            p = strtrim(p);
            if endsWith(lower(p), "py.exe")
                [s2,o2] = run_cmd(quote(p) + " -" + pyMinor + " -c " + quote("import sys; print(sys.base_prefix)"));
                if s2==0 && strlength(strtrim(o2))>0
                    home = canon_dir(strtrim(o2)); if strlength(home)>0, return; end
                end
            end
        end
    end
    % 3) Registry-Schlüssel (HKCU/HKLM)
    keys = [
        "HKCU\Software\Python\PythonCore\" + pyMinor + "\InstallPath"
        "HKLM\Software\Python\PythonCore\" + pyMinor + "\InstallPath"
        "HKLM\Software\WOW6432Node\Python\PythonCore\" + pyMinor + "\InstallPath"
    ];
    for k = 1:numel(keys)
        [st,out] = run_cmd("reg query " + keys(k) + " /ve");
        if st==0
            L = splitlines(string(out));
            for j=1:numel(L)
                parts = regexp(L(j), 'REG_SZ\s+(.*)$', 'tokens', 'once');
                if ~isempty(parts)
                    inst = strtrim(parts{1});
                    py = fullfile(inst, "python.exe");
                    if ~isfile(py), py = fullfile(fileparts(inst), "python.exe"); end
                    if isfile(py)
                        [s2,o2] = run_cmd(quote(py) + " -c " + quote("import sys; print(sys.base_prefix)"));
                        if s2==0 && strlength(strtrim(o2))>0
                            home = canon_dir(strtrim(o2)); if strlength(home)>0, return; end
                        end
                    end
                end
            end
        end
    end
    % 4) typische Installationspfade
    pn = replace(pyMinor,".","");
    candidates = [
        "C:\Users\" + getenv("USERNAME") + "\AppData\Local\Programs\Python\Python" + pn
        "C:\Program Files\Python" + pn
        "C:\Program Files (x86)\Python" + pn
    ];
    for c = candidates(:).'
        py = fullfile(c, "python.exe");
        if isfile(py)
            [s2,o2] = run_cmd(quote(py) + " -c " + quote("import sys; print(sys.base_prefix)"));
            if s2==0 && strlength(strtrim(o2))>0
                home = canon_dir(strtrim(o2)); if strlength(home)>0, return; end
            end
        end
    end
    home = "";
end

function fallback_replace_username_in_home(cfgPath, user)
% Ersetzt NUR den Benutzerteil in der Zeile:
%   home = C:\Users\<USER>\...
% Beibehaltung von Zeilenenden und restlichem Inhalt.

    txt  = fileread(cfgPath);  % char
    user = char(string(user)); % char-Row

    % Multiline-Regex: (?m) -> ^/$ gelten je Zeile.
    % Gruppen:
    %   1 = Prefix 'home = C:\Users\' (auch / oder fehlender Backslash nach Laufwerk erlaubt)
    %   2 = alter Benutzername (ohne / oder \)
    %   3 = restlicher Pfad ab dem nächsten Slash
    pat  = '(?m)^[ \t]*home[ \t]*=[ \t]*([A-Za-z]:[\\/ ]?Users[\\/ ]?)([^\\/]+)([\\/].*)$';
    repl = ['$1' user '$3'];     % <-- $1/$3 statt ${1}/${3}
    txt2 = regexprep(txt, pat, repl);

    txt2 = ['home = ' txt2];

    % Falls nichts ersetzt wurde: Warnung, aber nicht abbrechen
    if isequal(txt2, txt)
        warning('Fallback: Keine passende "home = C:\\Users\\<USER>\\..."-Zeile gefunden – keine Änderung vorgenommen.');
    end

    % Backup + Schreiben
    copyfile(cfgPath, cfgPath + ".bak", 'f');
    fid = fopen(cfgPath, 'w'); assert(fid>0, 'pyvenv.cfg nicht schreibbar');
    cleaner = onCleanup(@() fclose(fid));
    fprintf(fid, '%s', txt2);
end

function set_pyvenv_home(sysHome, cfgPath)
% set_pyvenv_home(sysHome, cfgPath)
%   Ersetzt in .venv/pyvenv.cfg nur die Zeile ab "home = " durch den
%   übergebenen sysHome. Rest bleibt unverändert.
%
%   sysHome : string/char, Zielpfad zur Basis-Python (sys.base_prefix)
%   cfgPath : optionaler Pfad zur pyvenv.cfg (Default: <pwd>/.venv/pyvenv.cfg)

    if nargin < 2 || isempty(cfgPath)
        cfgPath = fullfile(pwd, '.venv', 'pyvenv.cfg');
    end
    sysHome = string(sysHome);
    assert(isfile(cfgPath), 'pyvenv.cfg nicht gefunden: %s', cfgPath);

    txt = fileread(cfgPath);           % char-Text einlesen
    eol = detect_eol(txt);             % EOL-Stil (CRLF/LF) beibehalten

    % Regex: begin of line, optional spaces, "home", optional spaces, "=", Rest bis EOL
    hasHome = ~isempty(regexp(txt, '^[ \t]*home[ \t]*=', 'once', 'lineanchors', 'dotexceptnewline'));

    if hasHome
        % Ersetze NUR die "home = ..." Zeile
        newLine = "home = " + sysHome;
        txt2 = regexprep(txt, '^[ \t]*home[ \t]*=.*$', char(newLine), ...
                         'lineanchors', 'dotexceptnewline');
    else
        % Kein "home" vorhanden → füge am Anfang eine hinzu (mit EOL)
        newLine = "home = " + sysHome;
        txt2 = char(newLine) + eol + txt;
    end

    % Schreiben (Backup optional)
    backup = cfgPath + ".bak";
    copyfile(cfgPath, backup, 'f');

    fid = fopen(cfgPath, 'w');
    assert(fid>0, 'pyvenv.cfg nicht schreibbar: %s', cfgPath);
    cleaner = onCleanup(@() fclose(fid));
    fprintf(fid, '%s', txt2);  % txt2 ist char

    fprintf('[OK] pyvenv.cfg aktualisiert: home = %s\n', sysHome);
end

% ---- Kleinzeug ----
function [st,out] = run_cmd(cmd), [st,out] = system(cmd); out = strrep(string(out), sprintf('\r'), ''); end
function q = quote(s), q = """" + string(s) + """"; end
function d = canon_dir(p), try d = string(java.io.File(char(p)).getCanonicalPath()); catch, d = string(p); end, end
function eol = detect_eol(txt), if contains(txt, sprintf('\r\n')), eol = sprintf('\r\n'); else, eol = sprintf('\n'); end, end