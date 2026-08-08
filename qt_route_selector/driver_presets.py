from __future__ import annotations

from typing import Any


# Complete behavioural presets. Route/environment quantities such as the number
# of real OSM traffic lights are deliberately not part of a driver preset.
COMPLETE_DRIVER_PROFILES: dict[str, dict[str, Any]] = {
    "normalo": {
        "label": "Normalo",
        "note": "ausgewogen und defensiv",
        "temperament": 1.00,
        "driver_cruise_kmh": 130.0,
        "driver_hard_max_kmh": 140.0,
        "speed_bias_kmh": 0.0,
        "speed_tolerance_kmh": 1.0,
        "Kp": 1.10,
        "a_max_mps2": 2.8,
        "b_max_mps2": 3.0,
        "j_max_mps3": 1.20,
        "max_lat_accel_mps2": 2.2,
        "curve_plan_decel_mps2": 1.8,
        "traffic_light_plan_decel_mps2": 1.8,
        "traffic_light_stop_tolerance_m": 2.0,
        "use_driver_noise": True,
        "noise_std_kmh": 1.8,
        "noise_tau_s": 3.5,
        "use_post_curve_overshoot": True,
        "post_curve_overshoot_kmh": 3.0,
        "post_curve_overshoot_probability_pct": 60.0,
        "post_curve_overshoot_distance_m": 90.0,
        "use_overtaking": False,
        "overtaking_count": 0,
        "use_trailer_model": False,
    },
    "rennfahrer": {
        "label": "Rennfahrer",
        "note": "dynamisch, hohe Beschleunigung und hohe Kurvendynamik",
        "temperament": 1.10,
        "driver_cruise_kmh": 160.0,
        "driver_hard_max_kmh": 190.0,
        "speed_bias_kmh": 3.0,
        "speed_tolerance_kmh": 5.0,
        "Kp": 1.50,
        "a_max_mps2": 4.8,
        "b_max_mps2": 4.0,
        "j_max_mps3": 2.00,
        "max_lat_accel_mps2": 2.8,
        "curve_plan_decel_mps2": 2.6,
        "traffic_light_plan_decel_mps2": 2.4,
        "traffic_light_stop_tolerance_m": 1.5,
        "use_driver_noise": True,
        "noise_std_kmh": 2.5,
        "noise_tau_s": 2.0,
        "use_post_curve_overshoot": True,
        "post_curve_overshoot_kmh": 5.0,
        "post_curve_overshoot_probability_pct": 85.0,
        "post_curve_overshoot_distance_m": 65.0,
        # Overtaking remains opt-in because the application has no real traffic
        # stream from which a physically justified overtaking count could be inferred.
        "use_overtaking": False,
        "overtaking_count": 0,
        "use_trailer_model": False,
    },
    "handwerker": {
        "label": "Handwerker",
        "note": "zügig und pragmatisch",
        "temperament": 1.05,
        "driver_cruise_kmh": 140.0,
        "driver_hard_max_kmh": 155.0,
        "speed_bias_kmh": 2.0,
        "speed_tolerance_kmh": 3.0,
        "Kp": 1.30,
        "a_max_mps2": 3.6,
        "b_max_mps2": 3.2,
        "j_max_mps3": 1.60,
        "max_lat_accel_mps2": 2.5,
        "curve_plan_decel_mps2": 2.1,
        "traffic_light_plan_decel_mps2": 2.0,
        "traffic_light_stop_tolerance_m": 1.8,
        "use_driver_noise": True,
        "noise_std_kmh": 2.0,
        "noise_tau_s": 3.0,
        "use_post_curve_overshoot": True,
        "post_curve_overshoot_kmh": 3.5,
        "post_curve_overshoot_probability_pct": 70.0,
        "post_curve_overshoot_distance_m": 80.0,
        "use_overtaking": False,
        "overtaking_count": 0,
        "use_trailer_model": False,
    },
    "rentner": {
        "label": "Rentner",
        "note": "ruhig und defensiv, niedrigeres Tempo, ohne Fahrerrauschen",
        "temperament": 0.85,
        "driver_cruise_kmh": 105.0,
        "driver_hard_max_kmh": 120.0,
        "speed_bias_kmh": -2.0,
        "speed_tolerance_kmh": 1.0,
        "Kp": 0.75,
        "a_max_mps2": 1.5,
        "b_max_mps2": 2.0,
        "j_max_mps3": 0.55,
        "max_lat_accel_mps2": 1.4,
        "curve_plan_decel_mps2": 1.3,
        "traffic_light_plan_decel_mps2": 1.3,
        "traffic_light_stop_tolerance_m": 2.5,
        "use_driver_noise": False,
        "noise_std_kmh": 0.0,
        "noise_tau_s": 10.0,
        "use_post_curve_overshoot": True,
        "post_curve_overshoot_kmh": 1.0,
        "post_curve_overshoot_probability_pct": 20.0,
        "post_curve_overshoot_distance_m": 150.0,
        "use_overtaking": False,
        "overtaking_count": 0,
        "use_trailer_model": False,
    },
    "rentner_anhaenger": {
        "label": "Rentner + Anhänger",
        "note": "sehr ruhig und defensiv mit Anhänger, ohne Fahrerrauschen",
        "temperament": 0.80,
        "driver_cruise_kmh": 90.0,
        "driver_hard_max_kmh": 100.0,
        "speed_bias_kmh": -3.0,
        "speed_tolerance_kmh": 0.5,
        "Kp": 0.65,
        "a_max_mps2": 1.2,
        "b_max_mps2": 2.0,
        "j_max_mps3": 0.40,
        "max_lat_accel_mps2": 1.25,
        "curve_plan_decel_mps2": 1.1,
        "traffic_light_plan_decel_mps2": 1.1,
        "traffic_light_stop_tolerance_m": 2.8,
        "use_driver_noise": False,
        "noise_std_kmh": 0.0,
        "noise_tau_s": 15.0,
        "use_post_curve_overshoot": False,
        "post_curve_overshoot_kmh": 0.0,
        "post_curve_overshoot_probability_pct": 0.0,
        "post_curve_overshoot_distance_m": 180.0,
        "use_overtaking": False,
        "overtaking_count": 0,
        "use_trailer_model": True,
        "trailer_mass_kg": 1200.0,
    },
}


POST_CURVE_DEFAULTS: dict[str, Any] = {
    "use_post_curve_overshoot": True,
    "post_curve_overshoot_kmh": 3.0,
    "post_curve_overshoot_probability_pct": 60.0,
    "post_curve_overshoot_distance_m": 90.0,
}


def install_complete_driver_profiles(speed_simulation_module: Any) -> None:
    """Install complete profiles into the existing simulation module in-place.

    Keeping the original dictionaries alive matters because several UI modules
    import them directly. Updating in-place makes all of those references see
    the same preset values without changing the established simulation API.
    """

    speed_simulation_module.DEFAULT_PARAMETERS.update(POST_CURVE_DEFAULTS)
    speed_simulation_module.DRIVER_PROFILES.clear()
    speed_simulation_module.DRIVER_PROFILES.update(
        {name: dict(values) for name, values in COMPLETE_DRIVER_PROFILES.items()}
    )
