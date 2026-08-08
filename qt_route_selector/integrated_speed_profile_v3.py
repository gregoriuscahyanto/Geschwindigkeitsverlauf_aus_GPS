"""Compatibility shim for older launch code.

New code should import :mod:`qt_route_selector.integrated_speed_profile`.
"""

try:
    from .integrated_speed_profile import IntegratedSpeedProfileWindow, main
except ImportError:
    from integrated_speed_profile import IntegratedSpeedProfileWindow, main

__all__ = ["IntegratedSpeedProfileWindow", "main"]
