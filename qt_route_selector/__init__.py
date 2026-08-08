"""Qt-based local route selection and offline routing package."""

from . import speed_simulation as _speed_simulation
from .driver_presets import install_complete_driver_profiles as _install_complete_driver_profiles

_install_complete_driver_profiles(_speed_simulation)

del _install_complete_driver_profiles
