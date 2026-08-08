"""Private simulation UI layers.

The public API is ``qt_route_selector.integrated_speed_profile``.  These modules
are kept internal because the current UI grew in small, tested increments.  The
aliases below let the moved layers keep their original relative imports while
runtime modules stay in the package root.
"""

from __future__ import annotations

from importlib import import_module
import sys

_DEPENDENCIES = (
    "speed_simulation",
    "enhanced_speed_simulation",
    "live_speed_profile",
    "resistance_power",
    "load_collective_curve",
    "technical_previews",
    "technical_previews_v2",
    "driver_presets",
    "parameter_help",
)

for _name in _DEPENDENCIES:
    try:
        _module = import_module(f"qt_route_selector.{_name}")
    except ImportError:
        _module = import_module(_name)
    sys.modules.setdefault(f"{__name__}.{_name}", _module)

del _name, _module
