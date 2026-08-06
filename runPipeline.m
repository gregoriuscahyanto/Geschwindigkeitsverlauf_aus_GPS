%% GPX-Fahrprofilsimulation: Bergfahrt mit Anhaenger
% Vollstaendige Version mit:
% - GPX-Auswahl und optionaler PBF/FGB-Augmentierung
% - Fahrerprofilen inklusive "rentner_anhaenger"
% - einstellbarer Reise- und Maximalgeschwindigkeit
% - optionalem, begrenztem Fahrerrauschen
% - Kurvengeschwindigkeit aus lokalem Kurvenradius
% - vorausschauendem Bremsen vor Kurven
% - sanftem Beschleunigungsimpuls am Kurvenausgang
% - Steigungs- und Anhaengermodell aus GPX-Hoehendaten
% - Ampeln, Ueberholen, MAT-Export und Karte

clc; clearvars; close all;

%% ===================== Auswahl =====================
% normalo | rennfahrer | handwerker | rentner | rentner_anhaenger | custom
driverProfile = 'rentner_anhaenger';
DO_SAVE = true;
DO_PLOT = true;

%% ===================== Basis-Konfiguration =====================
default_kmh = 30;
dt = 0.2;
simulationSeed = [];            % [] = zufaellig, Zahl = reproduzierbar

% Geschwindigkeit
driverCruise_kmh = 30;          % gewuenschte Reisegeschwindigkeit
driverHardMax_kmh = 35;        % absolute Grenze der Sollgeschwindigkeit
speedBias_kmh = 0;
speedTolerance_kmh = 1.0;
allowSpeedVariation = false;

% Fahrerrauschen
useDriverNoise = false;
noiseStd_kmh = 0;
noiseTau_s = 15;

% Regler und Laengsdynamik
Kp = 0.65;
a_max = 1.2;
b_max = -2.0;
j_max = 0.40;

% Kurvenmodell
applyCurveSpeed = true;
maxLatAccel_mps2 = 1.25;
minCurveRadius_m = 8;
maxCurveRadius_m = 5000;
curveSampleDistance_m = 12;
curveSmoothDistance_m = 25;
curveLookAhead_s = 5.0;
curveLookAheadMin_m = 35;
curveLookAheadMax_m = 180;
curvePlanDecel_mps2 = 1.1;
curveEntryThreshold = 0.98;
curveExitThreshold = 0.995;

% Kurvenausgang
useCurveExitBoost = true;
curveExitDuration_s = 3.0;         % Dauer der staerkeren Rueckbeschleunigung
curveExitAccelFactor = 1.20;       % Regler am Ausgang voruebergehend staerker
curveExitExtraAccel_mps2 = 0.20;   % zusaetzlicher Beschleunigungswunsch
curveExitMinSlowdown_kmh = 3.0;    % nur ausloesen, wenn Kurve mind. 3 km/h bremst
curveExitMinCurveTime_s = 1.5;     % kurze GPS-Zacken ignorieren
curveExitCooldown_s = 8.0;         % Mindestabstand zwischen zwei Impulsen
allowCurveExitOverspeed = false;   % nach Kurve nur bis Reise-/Strassenlimit

% Anhaenger und Bergfahrt
useTrailerModel = true;
vehicleMass_kg = 1800;
trailerMass_kg = 1200;
gravity_mps2 = 9.81;
rollingResistanceCoeff = 0.015;
maxDriveForce_N = 5200;
maxBrakeForce_N = 9000;
gradeSmoothDistance_m = 30;
maxAbsGrade = 0.18;

% Ampeln
useTrafficLights = true;
T_min = 60; T_max = 120;
redFrac_min = 0.40; redFrac_max = 0.60;
minSpacing_m = 15;
stopTol_m = 2.0;
brakeBuffer_m = 14.0;
planDecel = 1.1;
ampelBandHalfWidth_m = 15;

% Ueberholen
useOvertaking = false;
slowRatePerKm = 0.6;
vslow_mean_kmh = 105;
vslow_std_kmh = 8;
overtakeBoost = 20;
minRel_kmh = 6;
waitGap_mean_s = 4.5;
passDist_m = 80;

% Augmentierung
radius_m = 5;
bbox_m = 10;
useRTree = true;
signal_snap_radius = 12;

% Darstellung
timeBandAlpha = 0.45;
redBandColor = [0.95 0.45 0.45];
passBandColor = [0.45 0.70 1.00];
passLineColor = [0.00 0.45 0.74];
ampelLineColor = [0.85 0.33 0.31];
curveLineColor = [0.49 0.18 0.56];
scatterSizePts = 20;
startMarkerSize = 70;

%% ===================== Fahrerprofil anwenden =====================
[profileParams, profileNote] = getDriverProfiles(driverProfile);
applyDriverProfile(profileParams);
fprintf('[PROFILE] %s: %s\n', upper(driverProfile), profileNote);

% Abhaengige Werte erst nach dem Profil festlegen
planDecel = min(planDecel, 0.8*abs(b_max));
curvePlanDecel_mps2 = min(curvePlanDecel_mps2, 0.8*abs(b_max));
totalMass_kg = vehicleMass_kg + trailerMass_kg;

if isempty(simulationSeed), rng('shuffle');
else, rng(simulationSeed,'twister');
end

%% ===================== Verzeichnisse und Python =====================
baseDir = string(fileparts(mfilename('fullpath')));
if baseDir == "", baseDir = string(pwd); end

dbFullDir = fullfile(baseDir,"database");
dbSlimDir = fullfile(baseDir,"databaseSlim");
tracksDir = fullfile(baseDir,"tracks");
augDir = fullfile(baseDir,"augmented");
resultDir = fullfile(baseDir,"results");
ensureFolder(dbFullDir); ensureFolder(dbSlimDir); ensureFolder(tracksDir);
ensureFolder(augDir); ensureFolder(resultDir);

augmentPy = fullfile(baseDir,"augment_gpx_v2.py");
buildFgbPy = fullfile(baseDir,"build_highways_fgb_v2.py");
assert(isfile(augmentPy),'Skript nicht gefunden: %s',augmentPy);
assert(isfile(buildFgbPy),'Skript nicht gefunden: %s',buildFgbPy);

if ispc
    pyexe = fullfile(baseDir,".venv","Scripts","python.exe");
else
    pyexe = fullfile(baseDir,".venv","bin","python");
end
assert(isfile(pyexe),'.venv-Python nicht gefunden: %s',pyexe);

%% ===================== GPX waehlen und augmentieren =====================
[fn,fp] = uigetfile({'*.gpx','GPX (*.gpx)'},'GPX-Datei waehlen',tracksDir);
if isequal(fn,0), error('Keine GPX gewaehlt.'); end
gpxIn = canonicalPath(fullfile(fp,fn));
[~,inBase] = fileparts(gpxIn);
gpxOut = fullfile(augDir,inBase+"_with_maxspeed.gpx");

if isfile(gpxOut)
    gpxFile = gpxOut;
    usedSourceKind = "existing";
    fprintf('[GPX] Vorhandene augmentierte Datei: %s\n',gpxFile);
else
    dataSrcAbs = ""; srcKind = "";
    fgbFiles = dir(fullfile(dbSlimDir,"*.fgb"));
    if ~isempty(fgbFiles)
        labels = string({fgbFiles.name});
        [idx,ok] = listdlg('PromptString', ...
            'Vorhandene FGB waehlen oder Abbrechen fuer PBF:', ...
            'SelectionMode','single','ListString',cellstr(labels));
        if ok
            dataSrcAbs = canonicalPath(fullfile(fgbFiles(idx).folder,fgbFiles(idx).name));
            srcKind = "fgb";
        end
    end

    if dataSrcAbs == ""
        [fnpbf,fppbf] = uigetfile({'*.pbf','OSM PBF (*.pbf)'}, ...
            'OSM-PBF waehlen',dbFullDir);
        if isequal(fnpbf,0), error('Keine PBF gewaehlt.'); end
        pbfFullAbs = canonicalPath(fullfile(fppbf,fnpbf));
        highwaysFgbAbs = canonicalPath(fullfile(dbSlimDir,deriveFgbName(fnpbf)));
        if isfile(highwaysFgbAbs)
            dataSrcAbs = highwaysFgbAbs; srcKind = "fgb";
        else
            choice = questdlg('FGB erzeugen oder direkt aus PBF augmentieren?', ...
                'Datenquelle','FGB erzeugen','Direkt PBF','Abbrechen','FGB erzeugen');
            if strcmp(choice,'FGB erzeugen')
                ensureHighwaysFGB(pbfFullAbs,highwaysFgbAbs,buildFgbPy,pyexe,0.0008);
                dataSrcAbs = highwaysFgbAbs; srcKind = "fgb";
            elseif strcmp(choice,'Direkt PBF')
                dataSrcAbs = pbfFullAbs; srcKind = "pbf";
            else
                error('Abgebrochen.');
            end
        end
    end

    setenv('PYTHONUNBUFFERED','1'); setenv('PYTHONIOENCODING','utf-8');
    q = @(s) ['"',char(s),'"'];
    if srcKind == "fgb", srcArgs = ["--highways_fgb",string(q(dataSrcAbs))];
    else, srcArgs = ["--pbf",string(q(dataSrcAbs))];
    end
    rtreeArg = ""; if ~useRTree, rtreeArg = "--no_rtree"; end
    args = [string(q(pyexe)),"-X","utf8","-u",string(q(augmentPy)), ...
        srcArgs,"--gpx_in",string(q(gpxIn)),"--gpx_out",string(q(gpxOut)), ...
        "--radius",string(radius_m),"--bbox_margin",string(bbox_m), ...
        "--signal_snap_radius",string(signal_snap_radius),rtreeArg];
    args(args=="")=[];
    cmdAug = strjoin(args,' ')+" 2>&1";
    fprintf('[AUGMENT] %s\n',cmdAug);
    status = system(cmdAug);
    if status~=0, error('Augmentor fehlgeschlagen, Status %d.',status); end
    assert(isfile(gpxOut),'Augmentierte GPX wurde nicht erzeugt.');
    writeAugmentMeta2(gpxIn,dataSrcAbs,srcKind,gpxOut,struct( ...
        'radius_m',radius_m,'bbox_m',bbox_m,'useRTree',useRTree, ...
        'signal_snap_radius',signal_snap_radius));
    gpxFile = gpxOut; usedSourceKind = srcKind;
end

%% ===================== GPX lesen =====================
xDoc = xmlread(char(gpxFile));
trkpts = xDoc.getElementsByTagName('trkpt');
numPts = trkpts.getLength;
if numPts<2, error('Zu wenige Trackpunkte.'); end

lat=zeros(numPts,1); lon=zeros(numPts,1); ele=nan(numPts,1);
vmax_kmh=nan(numPts,1); isSignal=false(numPts,1); highways=strings(numPts,1);
for ii=0:numPts-1
    pt=trkpts.item(ii);
    lat(ii+1)=str2double(pt.getAttribute('lat'));
    lon(ii+1)=str2double(pt.getAttribute('lon'));
    en=pt.getElementsByTagName('ele');
    if en.getLength>0, ele(ii+1)=str2double(en.item(0).getTextContent()); end
    exts=pt.getElementsByTagName('extensions');
    if exts.getLength>0
        ext=exts.item(0);
        ms=ext.getElementsByTagName('maxspeed');
        if ms.getLength>0, vmax_kmh(ii+1)=parseMaxspeed(string(ms.item(0).getTextContent())); end
        sg=ext.getElementsByTagName('traffic_signal');
        if sg.getLength>0
            sv=string(sg.item(0).getTextContent());
            isSignal(ii+1)=any(strcmpi(strtrim(sv),["true","1","yes"]));
        end
        hw=ext.getElementsByTagName('highway');
        if hw.getLength>0, highways(ii+1)=string(hw.item(0).getTextContent()); end
    end
end

vmax_kmh_raw=vmax_kmh;
vmax_kmh_filled=fillmissing(vmax_kmh,'previous','EndValues','nearest');
vmax_kmh_filled(isnan(vmax_kmh_filled))=default_kmh;

% Strecke
dist=zeros(numPts-1,1); EarthR=6371000;
for ii=1:numPts-1
    dist(ii)=haversine(lat(ii),lon(ii),lat(ii+1),lon(ii+1),EarthR);
end
s=[0;cumsum(dist)]; L=s(end);
if L<=0, error('GPX hat keine positive Streckenlaenge.'); end
[sUnique,uniqueIdx]=unique(s,'stable');

% Hoehenwerte und Steigung
if any(isfinite(ele))
    ele=fillmissing(ele,'linear','EndValues','nearest');
else
    ele=zeros(numPts,1);
    if useTrailerModel
        warning('Keine GPX-Hoehendaten vorhanden. Bergmodell arbeitet mit 0 %% Steigung.');
    end
end
grade_raw=zeros(numPts,1);
if useTrailerModel && numPts>=3
    for ii=2:numPts-1
        ds=s(ii+1)-s(ii-1);
        if ds>0.5, grade_raw(ii)=(ele(ii+1)-ele(ii-1))/ds; end
    end
    grade_raw(1)=grade_raw(2); grade_raw(end)=grade_raw(end-1);
    grade_raw=min(max(grade_raw,-maxAbsGrade),maxAbsGrade);
    grade=spatialMovingMean(s,grade_raw,gradeSmoothDistance_m);
else
    grade=zeros(numPts,1);
end

% Signale
sigIdx=find(isSignal);
if ~isempty(sigIdx)
    keep=true(size(sigIdx)); lastS=-inf;
    for kk=1:numel(sigIdx)
        if s(sigIdx(kk))-lastS<minSpacing_m, keep(kk)=false;
        else, lastS=s(sigIdx(kk)); end
    end
    sigIdx=sigIdx(keep);
end
s_sig=s(sigIdx); nSig=numel(s_sig);

% Autobahn
hLower=lower(strtrim(highways));
isMotorway=ismember(hLower,["motorway","motorway_link","trunk"]);

%% ===================== Kurvenradius und Kurvengeschwindigkeit =====================
vlimit_pts_mps=vmax_kmh_filled/3.6;
curveRadius_m=inf(numPts,1); vcurve_raw_mps=inf(numPts,1);
if applyCurveSpeed && numPts>=3
    for ii=2:numPts-1
        ip=nearestIndexAtDistance(s,ii,-curveSampleDistance_m);
        in=nearestIndexAtDistance(s,ii, curveSampleDistance_m);
        if ip<ii && in>ii
            curveRadius_m(ii)=localCurveRadius(lat(ip),lon(ip),lat(ii),lon(ii),lat(in),lon(in));
            if isfinite(curveRadius_m(ii))
                curveRadius_m(ii)=min(max(curveRadius_m(ii),minCurveRadius_m),maxCurveRadius_m);
                vcurve_raw_mps(ii)=sqrt(maxLatAccel_mps2*curveRadius_m(ii));
            end
        end
    end
    curveRadius_m(1)=curveRadius_m(2); curveRadius_m(end)=curveRadius_m(end-1);
    vcurve_raw_mps(1)=vcurve_raw_mps(2); vcurve_raw_mps(end)=vcurve_raw_mps(end-1);
end
vcurve_mps=spatialMovingMin(s,vcurve_raw_mps,curveSmoothDistance_m);
vref_pts=min(vlimit_pts_mps,vcurve_mps);
curveFactor=min(1,vref_pts./max(vlimit_pts_mps,0.1));
isCurvePoint=curveFactor<curveEntryThreshold;

%% ===================== Ampelzyklen =====================
if useTrafficLights && nSig>0
    T_cyc=T_min+(T_max-T_min)*rand(nSig,1);
    red_frac=redFrac_min+(redFrac_max-redFrac_min)*rand(nSig,1);
    t_offset=T_cyc.*rand(nSig,1);
    isRedAt=@(idx,t) mod(t+t_offset(idx),T_cyc(idx))<red_frac(idx)*T_cyc(idx);
else
    T_cyc=[]; red_frac=[]; t_offset=[]; isRedAt=@(idx,t) false;
end

%% ===================== Ueberholereignisse =====================
overtakeEvents=struct('sStart',{},'vslow',{},'tWait',{},'tPass',{});
if useOvertaking
    motIdx=find(isMotorway);
    if ~isempty(motIdx)
        edges=[1;find(diff(motIdx)>1)+1;numel(motIdx)+1];
        intervals=[motIdx(edges(1:end-1)),motIdx(edges(2:end)-1)];
        for iv=1:size(intervals,1)
            s0=s(intervals(iv,1)); s1=s(intervals(iv,2)); len=max(0,s1-s0);
            nEvt=localPoissrnd(slowRatePerKm/1000*len);
            for jj=1:nEvt
                vs=max(60,vslow_mean_kmh+vslow_std_kmh*randn);
                rel=max(minRel_kmh,overtakeBoost);
                overtakeEvents(end+1)=struct('sStart',s0+rand*len,'vslow',vs, ...
                    'tWait',localExprnd(waitGap_mean_s,1,1), ...
                    'tPass',passDist_m/max(0.1,rel/3.6)); %#ok<SAGROW>
            end
        end
        if ~isempty(overtakeEvents)
            [~,ord]=sort([overtakeEvents.sStart]); overtakeEvents=overtakeEvents(ord);
        end
    end
end

%% ===================== Simulation =====================
x=0; v=0; a=0; time=0; V=0; A=0; X=0; Vref_t=0;
RoadLimit_t=vlimit_pts_mps(1); CurveLimit_t=vcurve_mps(1); Grade_t=grade(1);
k=1; passedSig=false(size(s_sig)); noise_kmh=0;
alpha=exp(-dt/max(1e-6,noiseTau_s));
passIntervals_t=[]; passIntervals_x=[]; redStopIntervals_t=[];
evtIdx=1; state="free"; t_state=0; vCap_mps=inf; haveEvt=false;
evtActive=struct('sStart',0,'vslow',0,'tWait',0,'tPass',0);
wasInCurve=false; curveExitActive=false; curveExitTimer_s=0;
curveTime_s=0; curveMinTarget_mps=inf; curveExitCooldownTimer_s=inf;
maxSteps=ceil(max(3600,10*L/max(1,default_kmh/3.6))/dt); stepCount=0;

while x<L && k<numPts
    stepCount=stepCount+1;
    if stepCount>maxSteps, warning('Sicherheitsabbruch der Simulation.'); break; end
    while k<numPts && x>s(k+1), k=k+1; end
    if k>=numPts, break; end

    segLen=max(s(k+1)-s(k),eps);
    frac=min(max((x-s(k))/segLen,0),1);
    grade_now=(1-frac)*grade(k)+frac*grade(k+1);
    roadLimit_mps=vlimit_pts_mps(k);

    % Kurvenvorausschau und bremsbarer Zielwert
    lookAhead_m=min(curveLookAheadMax_m,max(curveLookAheadMin_m,curveLookAhead_s*max(v,1)));
    idxAhead=find(s>=x & s<=min(L,x+lookAhead_m));
    if isempty(idxAhead)
        curveTarget_mps=inf; curveTargetS=x;
    else
        [curveTarget_mps,loc]=min(vcurve_mps(idxAhead)); curveTargetS=s(idxAhead(loc));
    end
    curveDistance_m=max(0,curveTargetS-x);
    curvePlan_mps=sqrt(max(0,curveTarget_mps^2+2*curvePlanDecel_mps2*curveDistance_m));

    % Relevante Kurve erkennen. Ein Ausgangsimpuls wird nur nach einer
    % Kurve ausgeloest, die das Solltempo wirklich merklich reduziert hat.
    curveFactor_now=(1-frac)*curveFactor(k)+frac*curveFactor(k+1);
    isInCurveNow=curveFactor_now<curveEntryThreshold;
    curveExitCooldownTimer_s=curveExitCooldownTimer_s+dt;

    if isInCurveNow
        if ~wasInCurve
            curveTime_s=0;
            curveMinTarget_mps=inf;
        end
        curveTime_s=curveTime_s+dt;
        curveMinTarget_mps=min(curveMinTarget_mps,curveTarget_mps);
    end

    if wasInCurve && ~isInCurveNow
        slowdown_kmh=max(0,driverCruise_kmh-curveMinTarget_mps*3.6);
        validCurve=curveTime_s>=curveExitMinCurveTime_s && ...
            slowdown_kmh>=curveExitMinSlowdown_kmh;
        cooldownReady=curveExitCooldownTimer_s>=curveExitCooldown_s;

        if validCurve && cooldownReady
            curveExitActive=true;
            curveExitTimer_s=0;
            curveExitCooldownTimer_s=0;
        end
        curveTime_s=0;
        curveMinTarget_mps=inf;
    end
    wasInCurve=isInCurveNow;

    % Basissoll
    v_ref_base=min([roadLimit_mps,driverCruise_kmh/3.6,curvePlan_mps]);
    v_ref_eff=v_ref_base;

    % Ampel
    if useTrafficLights && nSig>0
        idxNext=find(~passedSig & s_sig>x,1,'first');
        if ~isempty(idxNext)
            D=s_sig(idxNext)-x; v_est=max([v,v_ref_eff,2]); t_arr=time(end)+D/v_est;
            if isRedAt(idxNext,t_arr)
                v_target=sqrt(max(0,2*planDecel*max(0,D-stopTol_m-brakeBuffer_m)));
                v_ref_eff=min(v_ref_eff,v_target);
                if D<=stopTol_m && v<=0.5
                    Tnow=T_cyc(idxNext); Rred=red_frac(idxNext)*Tnow;
                    phase=mod(time(end)+t_offset(idxNext),Tnow);
                    nHold=max(1,ceil(max(0,Rred-phase)/dt)); t0=time(end)+dt;
                    time=[time;time(end)+(1:nHold)'*dt]; %#ok<AGROW>
                    V=[V;zeros(nHold,1)]; A=[A;zeros(nHold,1)]; %#ok<AGROW>
                    X=[X;repmat(x,nHold,1)]; Vref_t=[Vref_t;zeros(nHold,1)]; %#ok<AGROW>
                    RoadLimit_t=[RoadLimit_t;repmat(roadLimit_mps,nHold,1)]; %#ok<AGROW>
                    CurveLimit_t=[CurveLimit_t;repmat(curveTarget_mps,nHold,1)]; %#ok<AGROW>
                    Grade_t=[Grade_t;repmat(grade_now,nHold,1)]; %#ok<AGROW>
                    redStopIntervals_t=[redStopIntervals_t;t0,time(end)]; %#ok<AGROW>
                    passedSig(idxNext)=true; v=0; a=0;
                end
            elseif D<=stopTol_m
                passedSig(idxNext)=true;
            end
        end
    end

    % Optionales, begrenztes Rauschen
    if useDriverNoise && allowSpeedVariation && v_ref_eff>0.1
        noise_kmh=alpha*noise_kmh+sqrt(1-alpha^2)*noiseStd_kmh*randn;
        noise_kmh=min(max(noise_kmh,-speedTolerance_kmh),speedTolerance_kmh);
        v_ref_eff=v_ref_eff+(speedBias_kmh+noise_kmh)/3.6;
    end

    % Ueberholen, beim Anhaengerprofil standardmaessig deaktiviert
    if useOvertaking && ~isempty(overtakeEvents)
        while evtIdx<=numel(overtakeEvents) && x>=overtakeEvents(evtIdx).sStart
            if state=="free"
                evtActive=overtakeEvents(evtIdx); haveEvt=true;
                state="follow"; t_state=0; vCap_mps=evtActive.vslow/3.6;
            end
            evtIdx=evtIdx+1;
        end
        switch state
            case "free", vCap_mps=inf;
            case "follow"
                vCap_mps=evtActive.vslow/3.6; t_state=t_state+dt;
                if haveEvt && t_state>=evtActive.tWait, state="wait"; t_state=0; end
            case "wait"
                vCap_mps=evtActive.vslow/3.6; t_state=t_state+dt;
                if t_state>=0.5
                    state="pass"; t_state=0; vCap_mps=inf;
                    x_pass_start=x; t_pass_start=time(end);
                end
            case "pass"
                t_state=t_state+dt;
                v_ref_eff=max(v_ref_eff,min(evtActive.vslow+overtakeBoost,driverHardMax_kmh)/3.6);
                if haveEvt && t_state>=evtActive.tPass
                    state="free"; t_state=0; haveEvt=false; vCap_mps=inf;
                    passIntervals_x=[passIntervals_x;x_pass_start,x]; %#ok<AGROW>
                    passIntervals_t=[passIntervals_t;t_pass_start,time(end)]; %#ok<AGROW>
                end
        end
        v_ref_eff=min(v_ref_eff,vCap_mps);
    end

    % Kurvenausgang: nur nach einer relevanten Abbremsung zuegig zur
    % normalen Reisegeschwindigkeit zurueckkehren. Keine Ueberschreitung.
    exitAccelMultiplier = 1.0;
    exitAccelExtra_mps2 = 0.0;
    curveExitAllowance_kmh = 0.0;

    if useCurveExitBoost && curveExitActive
        curveExitTimer_s=curveExitTimer_s+dt;
        boostFraction=max(0,1-curveExitTimer_s/curveExitDuration_s);

        if grade_now>0
            gradeReduction=max(0.40,1-2.5*grade_now);
        else
            gradeReduction=1.0;
        end

        % Nur zur normalen erlaubten Geschwindigkeit zurueckbeschleunigen.
        exitTarget_mps=min(roadLimit_mps,driverCruise_kmh/3.6);
        v_ref_eff=max(v_ref_eff,exitTarget_mps);

        exitAccelMultiplier=1+gradeReduction* ...
            (curveExitAccelFactor-1)*boostFraction;
        exitAccelExtra_mps2=gradeReduction* ...
            curveExitExtraAccel_mps2*boostFraction;

        if curveExitTimer_s>=curveExitDuration_s || ...
                v>=exitTarget_mps-0.15
            curveExitActive=false;
            curveExitTimer_s=0;
        end
    end

    % Harte Sollgrenzen. Der Kurvenausgang bleibt unter Reise- und Strassenlimit.
    allowedRoadMax_mps = roadLimit_mps + ...
        (speedTolerance_kmh + curveExitAllowance_kmh)/3.6;
    hardCurveMax_mps = curvePlan_mps + speedTolerance_kmh/3.6;
    v_ref_eff = max(0,min([v_ref_eff,allowedRoadMax_mps, ...
        driverHardMax_kmh/3.6,hardCurveMax_mps]));

    % Regler mit echtem zusaetzlichem Beschleunigungsimpuls.
    a_controller = exitAccelMultiplier*Kp*(v_ref_eff-v) + ...
        exitAccelExtra_mps2;

    % Physikalisch verfuegbare Beschleunigung mit Masse und Steigung
    if useTrailerModel
        slopeAccel=-gravity_mps2*grade_now;
        if v>0.1, rollingAccel=-rollingResistanceCoeff*gravity_mps2;
        else, rollingAccel=0;
        end
        resistAccel=slopeAccel+rollingAccel;
        maxNetAccel=min(a_max,maxDriveForce_N/totalMass_kg+resistAccel);
        minNetAccel=max(b_max,-maxBrakeForce_N/totalMass_kg+resistAccel);
        if minNetAccel>maxNetAccel
            minNetAccel=maxNetAccel;
        end
        a_des=min(max(a_controller,minNetAccel),maxNetAccel);
    else
        a_des=min(max(a_controller,b_max),a_max);
    end

    % Ruckbegrenzung und Integration
    da=min(max(a_des-a,-j_max*dt),j_max*dt);
    a=min(max(a+da,b_max),a_max);
    v=max(0,v+a*dt);
    x=min(L,x+v*dt);

    time(end+1,1)=time(end)+dt; V(end+1,1)=v; A(end+1,1)=a; X(end+1,1)=x;
    Vref_t(end+1,1)=v_ref_eff; RoadLimit_t(end+1,1)=roadLimit_mps;
    CurveLimit_t(end+1,1)=curveTarget_mps; Grade_t(end+1,1)=grade_now;
end

if state=="pass" && exist('x_pass_start','var')
    passIntervals_x=[passIntervals_x;x_pass_start,x];
    passIntervals_t=[passIntervals_t;t_pass_start,time(end)];
end

%% ===================== Zeitreihen und Speichern =====================
vmaxPlot=fillmissing(vmax_kmh_raw,'previous','EndValues','nearest');
vmaxPlot(isnan(vmaxPlot))=default_kmh;
Vraw_t=interp1(sUnique,vmaxPlot(uniqueIdx)/3.6,X,'previous','extrap');
lat_t=interp1(sUnique,lat(uniqueIdx),X,'linear','extrap');
lon_t=interp1(sUnique,lon(uniqueIdx),X,'linear','extrap');
ele_t=interp1(sUnique,ele(uniqueIdx),X,'linear','extrap');
ampelBands_x=[s_sig-ampelBandHalfWidth_m,s_sig+ampelBandHalfWidth_m];

if DO_SAVE
    T=table(time(:),X(:),V(:)*3.6,Vref_t(:)*3.6,Vraw_t(:)*3.6, ...
        RoadLimit_t(:)*3.6,CurveLimit_t(:)*3.6,A(:),Grade_t(:)*100, ...
        lat_t(:),lon_t(:),ele_t(:),'VariableNames', ...
        {'time_s','distance_m','v_kmh','vref_kmh','vmax_kmh','road_limit_kmh', ...
        'curve_limit_kmh','a_mps2','grade_percent','lat_deg','lon_deg','ele_m'});
    T.marker_overtake=intervalsToMask(time,passIntervals_t);
    T.marker_light=intervalsToMask(time,redStopIntervals_t);
    T.marker_curve=interp1(sUnique,double(isCurvePoint(uniqueIdx)),X,'previous','extrap')>0.5;

    Profile=struct('name',string(driverProfile),'note',string(profileNote));
    Params=struct('dt',dt,'driverCruise_kmh',driverCruise_kmh, ...
        'driverHardMax_kmh',driverHardMax_kmh,'useDriverNoise',useDriverNoise, ...
        'noiseStd_kmh',noiseStd_kmh,'noiseTau_s',noiseTau_s, ...
        'Kp',Kp,'a_max',a_max,'b_max',b_max,'j_max',j_max, ...
        'maxLatAccel_mps2',maxLatAccel_mps2,'useTrailerModel',useTrailerModel, ...
        'vehicleMass_kg',vehicleMass_kg,'trailerMass_kg',trailerMass_kg, ...
        'rollingResistanceCoeff',rollingResistanceCoeff, ...
        'maxDriveForce_N',maxDriveForce_N,'maxBrakeForce_N',maxBrakeForce_N, ...
        'useCurveExitBoost',useCurveExitBoost, ...
        'curveExitDuration_s',curveExitDuration_s, ...
        'curveExitAccelFactor',curveExitAccelFactor, ...
        'curveExitExtraAccel_mps2',curveExitExtraAccel_mps2, ...
        'curveExitMinSlowdown_kmh',curveExitMinSlowdown_kmh, ...
        'curveExitMinCurveTime_s',curveExitMinCurveTime_s, ...
        'curveExitCooldown_s',curveExitCooldown_s, ...
        'allowCurveExitOverspeed',allowCurveExitOverspeed);
    Meta=struct('gpx_input',char(gpxIn),'gpx_augmented',char(gpxFile), ...
        'used_source',char(usedSourceKind),'generated_utc', ...
        char(datetime('now','TimeZone','UTC','Format','yyyy-MM-dd''T''HH:mm:ssXXX')));
    OvertakeIntervals_t=passIntervals_t; OvertakeIntervals_x=passIntervals_x;
    RedStopIntervals_t=redStopIntervals_t; CurveRadius_m=curveRadius_m;
    CurveSpeed_kmh=vcurve_mps*3.6; Grade_percent=grade*100;
    outMat=fullfile(resultDir,string(inBase)+"_sim_"+string(driverProfile)+".mat");
    save(outMat,'T','Profile','Params','Meta','OvertakeIntervals_t', ...
        'OvertakeIntervals_x','RedStopIntervals_t','CurveRadius_m', ...
        'CurveSpeed_kmh','Grade_percent','-v7.3');
    fprintf('[SAVE] %s\n',outMat);
end

%% ===================== Plot =====================
if DO_PLOT
    figure('Name','Bergfahrt mit Anhaenger','Color','w');
    tiled=tiledlayout(2,2,'TileSpacing','compact','Padding','compact');
    title(tiled,sprintf('%s, Reisegeschwindigkeit %.0f km/h',driverProfile,driverCruise_kmh));

    ax1=nexttile(1,[1 2]); hold(ax1,'on'); grid(ax1,'on');
    plot(ax1,time,V*3.6,'LineWidth',2,'DisplayName','v simuliert');
    plot(ax1,time,Vref_t*3.6,'LineWidth',1.2,'DisplayName','v Soll');
    plot(ax1,time,Vraw_t*3.6,'--','LineWidth',1.2,'DisplayName','Strassenlimit');
    curvePlot=CurveLimit_t; curvePlot(~isfinite(curvePlot))=NaN;
    plot(ax1,time,curvePlot*3.6,':','LineWidth',1.2,'DisplayName','Kurvenlimit');
    for r=1:size(redStopIntervals_t,1)
        local_xregion(ax1,redStopIntervals_t(r,1),redStopIntervals_t(r,2),redBandColor,timeBandAlpha);
    end
    for r=1:size(passIntervals_t,1)
        local_xregion(ax1,passIntervals_t(r,1),passIntervals_t(r,2),passBandColor,timeBandAlpha);
    end
    xlabel(ax1,'Zeit [s]'); ylabel(ax1,'Geschwindigkeit [km/h]');
    title(ax1,'Geschwindigkeit'); legend(ax1,'Location','best');

    axGrade=nexttile(3); grid(axGrade,'on');
    plot(axGrade,X/1000,Grade_t*100,'LineWidth',1.5);
    xlabel(axGrade,'Strecke [km]'); ylabel(axGrade,'Steigung [%]');
    title(axGrade,'Geglaettetes Steigungsprofil');

    tempAx=nexttile(4); pos=get(tempAx,'Position'); delete(tempAx);
    gx=geoaxes('Position',pos); hold(gx,'on');
    geoscatter(gx,lat,lon,scatterSizePts,vmaxPlot,'filled','DisplayName','v_{max}');
    geoscatter(gx,lat(1),lon(1),startMarkerSize,'g','filled','DisplayName','Start');
    geoscatter(gx,lat(end),lon(end),startMarkerSize,'k','filled','DisplayName','Ziel');
    if ~isempty(sigIdx), geoscatter(gx,lat(sigIdx),lon(sigIdx),60,'r','^','filled','DisplayName','Ampel'); end
    plotMaskedGeo(gx,lat,lon,distanceIntervalsToMask(s,passIntervals_x), ...
        'LineWidth',2.8,'Color',passLineColor,'DisplayName','Ueberholen');
    plotMaskedGeo(gx,lat,lon,distanceIntervalsToMask(s,ampelBands_x), ...
        'LineWidth',2.8,'Color',ampelLineColor,'DisplayName','Ampelbereich');
    plotMaskedGeo(gx,lat,lon,isCurvePoint,'LineWidth',2.4, ...
        'Color',curveLineColor,'DisplayName','Kurvenbegrenzung');
    try, geobasemap(gx,'topographic'); catch, geobasemap(gx,'streets-light'); end
    cb=colorbar(gx); cb.Label.String='v_{max} [km/h]';
    title(gx,'Strecke'); legend(gx,'Location','best');
end

%% ===================== Lokale Funktionen =====================
function ensureFolder(f), if ~isfolder(f), mkdir(f); end, end
function p=canonicalPath(pth), p=string(java.io.File(char(pth)).getCanonicalPath()); end
function name=deriveFgbName(pbfName)
    name=regexprep(string(pbfName),'(?i)\\.osm\\.pbf$','');
    name=regexprep(name,'(?i)\\.pbf$','')+".highways.fgb";
end
function val=parseMaxspeed(txt)
    txt=lower(strtrim(string(txt)));
    tok=regexp(char(txt),'[-+]?\\d+(?:[.,]\\d+)?','match','once');
    if isempty(tok), val=NaN; return; end
    val=str2double(strrep(tok,',','.')); if contains(txt,'mph'), val=val*1.609344; end
end
function d=haversine(lat1,lon1,lat2,lon2,R)
    p1=deg2rad(lat1); p2=deg2rad(lat2); dp=p2-p1; dl=deg2rad(lon2-lon1);
    h=sin(dp/2).^2+cos(p1).*cos(p2).*sin(dl/2).^2; h=min(max(h,0),1);
    d=2*R*atan2(sqrt(h),sqrt(1-h));
end
function idx=nearestIndexAtDistance(s,i,offset)
    target=s(i)+offset;
    if offset<0, c=1:i-1; else, c=i+1:numel(s); end
    if isempty(c), idx=i; return; end
    [~,j]=min(abs(s(c)-target)); idx=c(j);
end
function radius=localCurveRadius(lat1,lon1,lat2,lon2,lat3,lon3)
    R=6371000; p0=deg2rad(lat2); l0=deg2rad(lon2);
    x1=R*cos(p0)*(deg2rad(lon1)-l0); y1=R*(deg2rad(lat1)-p0);
    x3=R*cos(p0)*(deg2rad(lon3)-l0); y3=R*(deg2rad(lat3)-p0);
    a=hypot(x1,y1); b=hypot(x3,y3); c=hypot(x3-x1,y3-y1);
    twiceArea=abs(x1*y3-x3*y1);
    if min([a b c])<0.5 || twiceArea<1e-3, radius=inf;
    else, radius=(a*b*c)/(2*twiceArea); end
end
function out=spatialMovingMin(s,v,w)
    out=v; for i=1:numel(s), out(i)=min(v(abs(s-s(i))<=w)); end
end
function out=spatialMovingMean(s,v,w)
    out=zeros(size(v));
    for i=1:numel(s)
        z=v(abs(s-s(i))<=w); z=z(isfinite(z));
        if isempty(z), out(i)=0; else, out(i)=mean(z); end
    end
end
function mask=intervalsToMask(axisValues,intervals)
    mask=false(size(axisValues));
    for r=1:size(intervals,1), mask=mask|(axisValues>=intervals(r,1)&axisValues<=intervals(r,2)); end
end
function mask=distanceIntervalsToMask(s,intervals), mask=intervalsToMask(s,intervals); end
function n=localPoissrnd(lambda)
    if lambda<=0, n=0; return; end
    if lambda<30
        lim=exp(-lambda); p=1; k=0;
        while p>lim, k=k+1; p=p*rand; end
        n=k-1;
    else, n=max(0,round(lambda+sqrt(lambda)*randn)); end
end
function x=localExprnd(mu,m,n), x=-mu*log(max(realmin,rand(m,n))); end
function writeAugmentMeta2(gpxIn,srcPath,srcKind,gpxOut,params)
    M=struct('gpxIn',char(gpxIn),'srcPath',char(srcPath),'srcKind',char(srcKind), ...
        'params',params,'generated_utc',char(datetime('now','TimeZone','UTC', ...
        'Format','yyyy-MM-dd''T''HH:mm:ssXXX')));
    fid=fopen(gpxOut+".meta.json",'w'); assert(fid>0,'Meta-Datei nicht schreibbar.');
    c=onCleanup(@() fclose(fid)); %#ok<NASGU>
    fwrite(fid,jsonencode(M),'char');
end
function built=ensureHighwaysFGB(pbf,fgb,script,pyexe,simplify)
    ensureFolder(fileparts(fgb)); need=true;
    if isfile(fgb)
        src=dir(pbf); dst=dir(fgb); need=isempty(src)||isempty(dst)||dst.datenum<src.datenum;
    end
    if ~need, built=false; return; end
    q=@(s) ['"',char(s),'"'];
    cmd=strjoin([string(q(pyexe)),"-X","utf8","-u",string(q(script)), ...
        "--in_pbf",string(q(pbf)),"--out_fgb",string(q(fgb)), ...
        "--simplify",string(simplify),"--single_read"],' ')+" 2>&1";
    st=system(cmd); if st~=0, error('FGB-Erzeugung fehlgeschlagen: %d',st); end
    assert(isfile(fgb),'FGB-Ausgabe fehlt.'); built=true;
end
function local_xregion(ax,t1,t2,rgb,alpha)
    if t2<=t1, return; end, yl=ylim(ax);
    try
        xregion(ax,t1,t2,'FaceAlpha',alpha,'FaceColor',rgb,'EdgeColor','none','HandleVisibility','off');
    catch
        patch(ax,[t1 t2 t2 t1],[yl(1) yl(1) yl(2) yl(2)],rgb, ...
            'FaceAlpha',alpha,'EdgeColor','none','HandleVisibility','off');
    end
end
function hFirst=plotMaskedGeo(gx,lat,lon,mask,varargin)
    hFirst=gobjects(0); idx=find(mask(:)); if isempty(idx), return; end
    edges=[1;find(diff(idx)>1)+1;numel(idx)+1];
    for k=1:numel(edges)-1
        seg=idx(edges(k):edges(k+1)-1); if numel(seg)<2, continue; end
        if isempty(hFirst)||~isvalid(hFirst)
            hFirst=geoplot(gx,lat(seg),lon(seg),varargin{:},'HandleVisibility','on');
        else, geoplot(gx,lat(seg),lon(seg),varargin{:},'HandleVisibility','off'); end
    end
end
function [P,note]=getDriverProfiles(name)
    switch lower(string(name))
        case "normalo"
            P=struct('Kp',1.1,'a_max',2.8,'b_max',-3,'j_max',1.2, ...
                'maxLatAccel_mps2',2.2,'useDriverNoise',true,'allowSpeedVariation',true, ...
                'noiseStd_kmh',1.8,'noiseTau_s',3.5,'speedBias_kmh',0,'useTrailerModel',false);
            note="ausgewogen und defensiv";
        case "rennfahrer"
            P=struct('Kp',1.5,'a_max',4.8,'b_max',-4,'j_max',2, ...
                'maxLatAccel_mps2',2.8,'useDriverNoise',true,'allowSpeedVariation',true, ...
                'noiseStd_kmh',2.5,'noiseTau_s',2,'speedBias_kmh',2,'useTrailerModel',false);
            note="dynamisch";
        case "handwerker"
            P=struct('Kp',1.3,'a_max',3.6,'b_max',-3.2,'j_max',1.6, ...
                'maxLatAccel_mps2',2.5,'useDriverNoise',true,'allowSpeedVariation',true, ...
                'noiseStd_kmh',2,'noiseTau_s',3,'speedBias_kmh',1,'useTrailerModel',false);
            note="zuegig und pragmatisch";
        case "rentner"
            P=struct('Kp',0.75,'a_max',1.5,'b_max',-2,'j_max',0.55, ...
                'maxLatAccel_mps2',1.4,'useDriverNoise',false,'allowSpeedVariation',false, ...
                'noiseStd_kmh',0,'noiseTau_s',10,'speedBias_kmh',0,'useTrailerModel',false);
            note="ruhig und defensiv, ohne Fahrerrauschen";
        case "rentner_anhaenger"
            P=struct('Kp',0.65,'a_max',1.2,'b_max',-2,'j_max',0.40, ...
                ... % Reise- und Hardlimit aus der Basis-Konfiguration beibehalten
                'speedTolerance_kmh',1,'maxLatAccel_mps2',1.25, ...
                'curveLookAhead_s',5,'curveLookAheadMin_m',35, ...
                'curveLookAheadMax_m',180,'curvePlanDecel_mps2',1.1, ...
                'useDriverNoise',false,'allowSpeedVariation',false, ...
                'noiseStd_kmh',0,'noiseTau_s',15,'speedBias_kmh',0, ...
                'useTrailerModel',true,'useOvertaking',false, ...
                'brakeBuffer_m',14,'planDecel',1.1, ...
                'useCurveExitBoost',true, ...
                'curveExitDuration_s',3.0,'curveExitAccelFactor',1.20, ...
                'curveExitExtraAccel_mps2',0.20, ...
                'curveExitMinSlowdown_kmh',3.0, ...
                'curveExitMinCurveTime_s',1.5, ...
                'curveExitCooldown_s',8.0, ...
                'allowCurveExitOverspeed',false);
            note="ruhige Bergfahrt mit Anhaenger, ohne Fahrerrauschen";
        case "custom"
            P=struct(); note="benutzerdefiniert";
        otherwise
            error('Unbekanntes Fahrerprofil: %s',name);
    end
end
function applyDriverProfile(P)
    f=fieldnames(P); for k=1:numel(f), assignin('base',f{k},P.(f{k})); end
end
