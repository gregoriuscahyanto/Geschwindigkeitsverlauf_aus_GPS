"""Qt-based local route selection and offline routing package."""

from . import speed_simulation as _speed_simulation
from .curve_radius_policy import install_curve_radius_threshold as _install_curve_radius_threshold
from .driver_presets import install_complete_driver_profiles as _install_complete_driver_profiles

_install_complete_driver_profiles(_speed_simulation)
_install_curve_radius_threshold(_speed_simulation)

del _install_complete_driver_profiles
del _install_curve_radius_threshold
