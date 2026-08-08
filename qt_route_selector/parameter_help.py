from __future__ import annotations

from typing import Final


# Short, user-facing explanations for every simulation parameter. The examples
# are orientation values for the model, not claims about real driver groups.
PARAMETER_HELP: Final[dict[str, tuple[str, str, str]]] = {
    "temperament": (
        "Globaler Faktor für die Fahrerdynamik.",
        "Größere Werte machen Beschleunigen, Bremsen und die Reaktion auf Sollgeschwindigkeit dynamischer.",
        "0,8 = ruhig · 1,0 = neutral · 1,2 = dynamisch",
    ),
    "driver_cruise_kmh": (
        "Gewünschte Reisegeschwindigkeit, wenn Straße und Kurve eine höhere Geschwindigkeit erlauben.",
        "Begrenzt den normalen Geschwindigkeitswunsch des Fahrers; nach Kurven kann ein aktiviertes Überschwingen kurz darüber liegen.",
        "90 km/h = ruhig · 105 km/h = defensiv · 130 km/h = normal auf schneller Straße",
    ),
    "driver_hard_max_kmh": (
        "Absolute Obergrenze des Fahrermodells.",
        "Auch bei Bias, Überholen oder Nach-Kurven-Überschwingen wird dieser Wert nicht überschritten.",
        "120 km/h = defensiv · 140 km/h = Normalo · 190 km/h = sehr dynamisches Modell",
    ),
    "speed_bias_kmh": (
        "Konstanter Versatz zum Geschwindigkeitswunsch.",
        "Positiv fährt das Modell tendenziell etwas schneller, negativ etwas langsamer als der normale Zielwert.",
        "-2 km/h = vorsichtig · 0 = neutral · +3 km/h = zügig",
    ),
    "speed_tolerance_kmh": (
        "Kleine erlaubte Abweichung an Geschwindigkeits- und Kurvengrenzen.",
        "Größere Werte erlauben kurzfristig mehr Überschreitung; 0 bedeutet praktisch keine Toleranz.",
        "0–1 km/h = streng · 3 km/h = moderat · 5 km/h = großzügig",
    ),
    "Kp": (
        "Verstärkung des Geschwindigkeitsreglers.",
        "Höhere Werte reagieren stärker auf die Differenz zwischen Soll- und Istgeschwindigkeit; zu hohe Werte wirken aggressiver.",
        "0,65–0,8 = ruhig · 1,1 = normal · 1,5 = sehr direkt",
    ),
    "a_max_mps2": (
        "Maximale positive Längsbeschleunigung.",
        "Bestimmt, wie schnell das Fahrzeug nach Start, Kurve oder Ampel Geschwindigkeit aufbauen kann.",
        "1,2–1,5 m/s² = ruhig · 2,5–3,0 m/s² = normal · 4+ m/s² = sehr dynamisch",
    ),
    "b_max_mps2": (
        "Maximal zulässige Verzögerung des Fahrers.",
        "Höhere Werte ermöglichen späteres und stärkeres Bremsen; Planungsgrenzen können trotzdem früher abbremsen.",
        "2,0 m/s² = komfortabel · 3,0 m/s² = normal · 4,0 m/s² = dynamisch",
    ),
    "j_max_mps3": (
        "Maximaler Ruck, also Änderung der Beschleunigung pro Sekunde.",
        "Kleine Werte machen Übergänge weich; große Werte lassen Beschleunigung und Bremsung schneller einsetzen.",
        "0,4–0,6 m/s³ = sehr weich · 1,2 = normal · 2,0 = direkt",
    ),
    "start_stop": (
        "Legt fest, ob die Simulation am Start mit 0 km/h beginnt.",
        "Aktiviert erzeugt der Start eine reale Anfahrphase; deaktiviert beginnt das Fahrzeug bereits mit Zielgeschwindigkeit.",
        "Für reale Fahrten normalerweise EIN; für einen bereits fahrenden Messabschnitt AUS.",
    ),
    "end_stop": (
        "Legt fest, ob das Fahrzeug am Routenziel vollständig anhält.",
        "Aktiviert wird vor dem Ziel abgebremst; deaktiviert endet die Simulation im fahrenden Zustand.",
        "Parkplatz/Zieladresse = EIN · ausgeschnittener Streckenabschnitt = oft AUS",
    ),
    "use_post_curve_overshoot": (
        "Aktiviert ein kurzes Beschleunigen über die normale Reisegeschwindigkeit nach einer wirksamen Kurve.",
        "Erzeugt das typische Nachbeschleunigen und anschließende Zurückregeln auf den Reisegeschwindigkeitswert.",
        "Normalo = EIN · sehr defensiv/Anhänger = eher AUS",
    ),
    "post_curve_overshoot_kmh": (
        "Zusätzlicher Geschwindigkeitswunsch nach einer Kurve.",
        "Bestimmt die Höhe des temporären Peaks, ohne Straßen-, Kurven- oder absolute Obergrenzen auszuhebeln.",
        "1 km/h = schwach · 3 km/h = sichtbar · 5 km/h = dynamisch",
    ),
    "post_curve_overshoot_probability_pct": (
        "Anteil geeigneter Kurvenausgänge mit Nach-Kurven-Überschwingen.",
        "Bei 100 % tritt es an jedem geeigneten Kurvenausgang auf; der Simulations-Seed macht die Auswahl reproduzierbar.",
        "20 % = selten · 60 % = regelmäßig · 85 % = häufig",
    ),
    "post_curve_overshoot_distance_m": (
        "Strecke, über die der zusätzliche Geschwindigkeitswunsch wieder abklingt.",
        "Große Werte halten den Effekt länger; kleine Werte führen schneller zur normalen Reisegeschwindigkeit zurück.",
        "60–90 m = schnell · 150 m = langsam/ruhig",
    ),
    "apply_curve_speed": (
        "Aktiviert die geschwindigkeitsabhängige Kurvenbegrenzung aus Radius und Querbeschleunigung.",
        "Ausgeschaltet berücksichtigt die Simulation Kurven nicht als eigene Geschwindigkeitsgrenze.",
        "Für realistische Straßenfahrt normalerweise EIN.",
    ),
    "max_lat_accel_mps2": (
        "Zulässige Querbeschleunigung in Kurven.",
        "Höhere Werte erlauben bei gleichem Radius höhere Kurvengeschwindigkeit; niedrigere Werte fahren Kurven defensiver.",
        "1,2–1,5 m/s² = defensiv · 2,2 = normal · 2,8 = dynamisch",
    ),
    "min_curve_radius_m": (
        "Untergrenze des aus GPS-Geometrie geschätzten Kurvenradius.",
        "Verhindert, dass kleine geometrische Störungen unrealistisch winzige Radien und extreme Geschwindigkeitsabfälle erzeugen.",
        "Etwa 5–10 m für normale Straßendaten.",
    ),
    "max_curve_radius_m": (
        "Obergrenze, bis zu der Geometrie noch als Kurve bewertet wird.",
        "Sehr große Radien verhalten sich praktisch wie eine Gerade; der Wert stabilisiert die Berechnung.",
        "Typisch einige 1000 m; 5000 m ist ein robuster Standardwert.",
    ),
    "curve_sample_distance_m": (
        "Abstand der Punkte, aus denen lokal der Kurvenradius bestimmt wird.",
        "Klein reagiert auf enge Details, groß glättet lokale Geometrie und ignoriert kleine Zacken.",
        "8–15 m für detaillierte OSM-Routen; 20+ m für ruhigere Geometrie.",
    ),
    "curve_smooth_distance_m": (
        "Räumliches Glättungsfenster für den erkannten Kurvenradius.",
        "Größere Fenster reduzieren kurze Radius-Spitzen, können aber kurze echte Kurven verbreitern.",
        "0 m = roh · 20–30 m = moderat · 50+ m = stark geglättet",
    ),
    "curve_plan_decel_mps2": (
        "Verzögerung, mit der die Geschwindigkeit vor einer Kurve vorausgeplant wird.",
        "Höhere Werte erlauben späteres Bremsen; kleinere Werte beginnen früher und komfortabler zu verzögern.",
        "1,2–1,5 m/s² = komfortabel · 1,8 = normal · 2,5+ = sportlich",
    ),
    "use_surface_limit": (
        "Berücksichtigt den OSM-Straßenbelag bei der Zielgeschwindigkeit.",
        "Auf Schotter, Pflaster oder unbefestigten Wegen wird die Zielgeschwindigkeit reduziert.",
        "Für gemischte Straßen/Wirtschaftswege EIN; für reine Asphaltanalyse optional.",
    ),
    "use_traffic_lights": (
        "Aktiviert Stopps an tatsächlich auf der Route erkannten OSM-Ampeln.",
        "Ausgeschaltet werden erkannte Ampeln ignoriert; es werden weiterhin keine künstlichen Ampeln erzeugt.",
        "Für reale Stadtfahrt EIN; für eine Analyse ohne Haltevorgänge AUS.",
    ),
    "traffic_light_count": (
        "Anzahl der erkannten OSM-Ampeln, die als Stopps verwendet werden.",
        "Der Wert kann höchstens so groß sein wie die auf der Route tatsächlich erkannten und gefilterten Ampeln.",
        "0 = keine Stopps · 3 = drei reale OSM-Ampeln verwenden",
    ),
    "traffic_light_dwell_min_s": (
        "Kürzeste angenommene Standzeit an einer roten Ampel.",
        "Zusammen mit dem Maximalwert wird eine reproduzierbare Haltezeit innerhalb dieses Bereichs erzeugt.",
        "10–20 s = kurze Rotphase · 30+ s = längere Mindestwartezeit",
    ),
    "traffic_light_dwell_max_s": (
        "Längste angenommene Standzeit an einer roten Ampel.",
        "Vergrößert die mögliche Wartezeit und damit Fahrtdauer sowie Stop-and-go-Anteil.",
        "40–60 s = übliches Modellfenster · 90+ s = lange Rotphasen",
    ),
    "traffic_light_plan_decel_mps2": (
        "Geplante Verzögerung beim Annähern an eine Ampel.",
        "Klein bremst früh und weich, groß später und stärker.",
        "1,2–1,5 m/s² = komfortabel · 1,8–2,0 = normal · 2,5 = spät/dynamisch",
    ),
    "traffic_light_stop_tolerance_m": (
        "Räumliche Toleranz, innerhalb der ein Ampelstopp als erreicht gilt.",
        "Zu klein kann bei grober Abtastung den Stopp erschweren; zu groß verschiebt die Halteposition sichtbar.",
        "1,5–3 m ist für normale Routendaten sinnvoll.",
    ),
    "use_overtaking": (
        "Aktiviert modellierte Überholvorgänge.",
        "Nur bei aktivierter Funktion werden Folge- und Überholphasen in die Zielgeschwindigkeit eingebaut.",
        "Ohne reales Verkehrsmodell standardmäßig AUS; für Szenarioanalysen gezielt EIN.",
    ),
    "overtaking_count": (
        "Gewünschte Anzahl modellierter Überholvorgänge auf der Fahrt.",
        "Mehr Vorgänge erzeugen mehr Folge-/Beschleunigungsphasen, sofern geeignete Strecken vorhanden sind.",
        "0 = keiner · 1–3 = einzelne Szenarioereignisse",
    ),
    "overtaking_slow_speed_kmh": (
        "Geschwindigkeit des langsameren vorausfahrenden Fahrzeugs.",
        "Vor dem Überholen wird die eigene Zielgeschwindigkeit auf diesen Wert abgesenkt.",
        "60–80 km/h auf Landstraße; Wert muss zum betrachteten Szenario passen.",
    ),
    "overtaking_intensity_kmh": (
        "Zusätzlicher Geschwindigkeitswunsch während des Überholens.",
        "Höhere Werte erzeugen einen stärkeren Geschwindigkeitsbuckel, bleiben aber an harte/gesetzliche Limits gebunden.",
        "+10 km/h = mild · +20 km/h = deutlich · +30 km/h = stark",
    ),
    "overtaking_follow_distance_m": (
        "Streckenlänge der Phase hinter dem langsameren Fahrzeug vor dem Überholen.",
        "Große Werte verlängern die reduzierte Geschwindigkeit vor dem Manöver.",
        "100–200 m = kurze Folgephase · 300+ m = längeres Folgen",
    ),
    "overtaking_pass_distance_m": (
        "Streckenlänge des eigentlichen Überholabschnitts.",
        "Bestimmt, wie lange der erhöhte Geschwindigkeitswunsch wirkt.",
        "80–150 m für ein kurzes Modellereignis; länger bei langsamerem Manöver.",
    ),
    "use_driver_noise": (
        "Aktiviert kleine, zeitlich korrelierte Abweichungen des Fahrers vom Sollwert.",
        "Erzeugt eine weniger ideale, menschlichere Geschwindigkeitsregelung.",
        "Normalo = EIN · sehr ruhiges/deterministisches Modell = AUS",
    ),
    "noise_std_kmh": (
        "Stärke der zufälligen Geschwindigkeitsabweichung.",
        "Höhere Werte machen den Geschwindigkeitsverlauf unruhiger; die Toleranz begrenzt die wirksame Abweichung.",
        "0 = keine Streuung · 1–2 km/h = dezent · 3+ km/h = deutlich",
    ),
    "noise_tau_s": (
        "Zeitkonstante der Fahrerabweichung.",
        "Klein ändert sich das Rauschen schnell; groß führt zu langsam driftenden Abweichungen.",
        "2–4 s = lebendig · 10–15 s = sehr langsame Änderung",
    ),
    "simulation_seed": (
        "Startwert des Zufallszahlengenerators.",
        "Gleicher Seed + gleiche Parameter erzeugen dieselben zufälligen Ampelwartezeiten, Rausch- und Ereignisauswahlen.",
        "42 und 123 sind nur Beispiele; andere Zahl = anderer reproduzierbarer Verlauf.",
    ),
    "use_trailer_model": (
        "Aktiviert zusätzliche Masse und Fahrwiderstände eines Anhängers.",
        "Beeinflusst Beschleunigung, Steigungsleistung, Rollwiderstand, Luftwiderstand und die Leistungsbilanz.",
        "Ohne Anhänger AUS · Gespann EIN",
    ),
    "vehicle_mass_kg": (
        "Masse des Zugfahrzeugs ohne Anhängermasse.",
        "Mehr Masse erhöht Beschleunigungs-, Steigungs- und Rollleistungsbedarf; der Luftwiderstand bleibt davon unabhängig.",
        "1200–1600 kg = leichter Pkw · 1800–2200 kg = größerer Pkw/SUV · 3000+ kg = Transporter",
    ),
    "trailer_mass_kg": (
        "Masse des Anhängers.",
        "Wirkt nur bei aktiviertem Anhängermodell und erhöht Trägheits-, Steigungs- und Rollanteile.",
        "500 kg = leichter Anhänger · 1200 kg = mittleres Gespann · 2000+ kg = schwer",
    ),
    "rolling_resistance_coeff": (
        "Rollwiderstandsbeiwert des Fahrzeugs.",
        "Höhere Werte erhöhen die benötigte Leistung ungefähr proportional zu Geschwindigkeit und Masse.",
        "0,010 = sehr günstig · 0,015 = typischer Modellwert · 0,025+ = hoher Rollwiderstand",
    ),
    "max_drive_force_n": (
        "Maximale verfügbare Antriebskraft für das Massen-/Anhänger-Modell.",
        "Begrenzt bei hoher Gesamtmasse die tatsächlich erreichbare Beschleunigung.",
        "3000 N = schwächer · 5000 N = mittleres Modell · 8000+ N = kräftig",
    ),
    "max_brake_force_n": (
        "Maximal verfügbare Bremskraft für das Massen-/Anhänger-Modell.",
        "Begrenzt die mögliche Verzögerung des schweren Gespanns zusätzlich zur Fahrergrenze.",
        "6000–10000 N für mittlere Modellfahrzeuge; höhere Werte für kräftigere Bremsanlage.",
    ),
    "air_drag_coefficient": (
        "Aerodynamischer Widerstandsbeiwert cW des Fahrzeugs.",
        "Höherer cW steigert den Luftleistungsbedarf stark bei hoher Geschwindigkeit (Leistung etwa proportional zu v³).",
        "0,22–0,28 = aerodynamisch · 0,29–0,35 = normaler Pkw · 0,5+ = ungünstig",
    ),
    "frontal_area_m2": (
        "Projizierte Stirnfläche A des Fahrzeugs.",
        "Größere Fläche erhöht den Luftwiderstand direkt; zusammen mit cW bestimmt sie cW·A.",
        "2,0–2,4 m² = Pkw · 2,5–3,0 m² = SUV · deutlich mehr bei Transportern",
    ),
    "air_density_kg_m3": (
        "Luftdichte für die aerodynamische Widerstandsberechnung.",
        "Höhere Luftdichte erhöht den Luftwiderstand proportional; Höhe und Temperatur verändern diesen Wert real.",
        "1,225 kg/m³ = Standardatmosphäre nahe Meereshöhe · etwa 1,0 kg/m³ = dünnere Luft",
    ),
    "trailer_rolling_resistance_coeff": (
        "Rollwiderstandsbeiwert des Anhängers.",
        "Wirkt bei aktivem Anhängermodell auf den zusätzlichen Rollleistungsbedarf.",
        "0,010–0,015 = leicht rollend · 0,020+ = höherer Widerstand",
    ),
    "trailer_drag_area_m2": (
        "Zusammengefasster aerodynamischer Kennwert cW·A des Anhängers.",
        "Größere Werte erhöhen den zusätzlichen Luftleistungsbedarf des Gespanns stark bei höherem Tempo.",
        "0,5 m² = geringer Zusatz · 1,0 m² = mittleres Modell · 2+ m² = großer aerodynamischer Zusatz",
    ),
    "grade_smoothing_m": (
        "Glättungsstrecke für die aus dem Höhenmodell abgeleitete Straßensteigung.",
        "Größere Werte reduzieren DEM-Rauschen und Leistungsspitzen, können kurze echte Rampen aber abflachen.",
        "20 m = detailreich · 40 m = Standard · 80–120 m = stark geglättet",
    ),
}


SPECIAL_HELP: Final[dict[str, tuple[str, str, str]]] = {
    "driver_profile": (
        "Preset mit zusammenpassenden Fahrerparametern.",
        "Ein Preset setzt Reisegeschwindigkeit, Dynamik, Kurvenverhalten, Rauschen und Nach-Kurven-Verhalten gemeinsam. Einzelwerte können danach angepasst werden.",
        "Normalo = ausgewogen · Rentner = ruhiger/defensiver · Rennfahrer = dynamischer Modellfall",
    ),
    "elevation_smoothing": (
        "Glättungsfenster der sichtbaren Höhenkurve.",
        "Reduziert kleine Raster-/DEM-Zacken in der Darstellung. Die Steigungsberechnung besitzt zusätzlich eine eigene Glättung.",
        "0 m = Rohhöhe · 30 m = Standard · 60–100 m = deutlich geglättet",
    ),
}
