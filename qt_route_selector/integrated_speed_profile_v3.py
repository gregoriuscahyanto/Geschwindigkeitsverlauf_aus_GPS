"""Compatibility shim for older launch code.

New code should import :mod:`qt_route_selector.integrated_speed_profile`.
The complete desktop app still imports this shim, so it is also the small
integration point for persistent simulation settings.
"""

try:
    from .integrated_speed_profile import IntegratedSpeedProfileWindow as _BaseWindow, main
    from .simulation_settings import PersistentSimulationSettingsMixin
except ImportError:
    from integrated_speed_profile import IntegratedSpeedProfileWindow as _BaseWindow, main
    from simulation_settings import PersistentSimulationSettingsMixin


class IntegratedSpeedProfileWindow(PersistentSimulationSettingsMixin, _BaseWindow):
    """Current speed-profile window with JSON save/load for all parameters."""


__all__ = ["IntegratedSpeedProfileWindow", "main"]
