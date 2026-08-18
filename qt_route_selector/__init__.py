"""Qt-based local route selection and offline routing package."""

import sys as _sys

from . import local_router as _local_router
from . import speed_simulation as _speed_simulation
from .curve_radius_policy import install_curve_radius_threshold as _install_curve_radius_threshold
from .driver_presets import install_complete_driver_profiles as _install_complete_driver_profiles
from .segment_snapping import install_segment_snapping as _install_segment_snapping

_install_complete_driver_profiles(_speed_simulation)
_install_curve_radius_threshold(_speed_simulation)
_install_segment_snapping(_local_router)

# The historical Qt shell imports ``local_router`` as a top-level module after
# adding the package directory to sys.path. Reuse the already patched package
# module instead of loading a second, unpatched copy of the same source file.
_sys.modules.setdefault("local_router", _local_router)

del _install_complete_driver_profiles
del _install_curve_radius_threshold
del _install_segment_snapping
