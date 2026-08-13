from __future__ import annotations

from typing import Any

from . import complete_app as _complete_app


def _install_persistent_simulation_window() -> type:
    """Make the normal simulation window include route-embedded settings controls.

    The import is deliberately lazy so the large simulation UI is still loaded
    only when tab 2 is opened.
    """

    from . import integrated_speed_profile as public_module
    from .simulation_settings import PersistentSimulationSettingsMixin

    base_window = public_module.IntegratedSpeedProfileWindow
    if issubclass(base_window, PersistentSimulationSettingsMixin):
        return base_window

    class PersistentIntegratedSpeedProfileWindow(
        PersistentSimulationSettingsMixin,
        base_window,
    ):
        """Current simulation UI with settings stored in the route JSON."""

    PersistentIntegratedSpeedProfileWindow.__name__ = "IntegratedSpeedProfileWindow"
    PersistentIntegratedSpeedProfileWindow.__qualname__ = "IntegratedSpeedProfileWindow"
    public_module.IntegratedSpeedProfileWindow = PersistentIntegratedSpeedProfileWindow
    return PersistentIntegratedSpeedProfileWindow


class CompleteApplicationWindow(_complete_app.CompleteApplicationWindow):
    """Normal complete app with persistent route-bound simulation settings."""

    def _ensure_simulation_created(self) -> None:
        _install_persistent_simulation_window()
        super()._ensure_simulation_created()


# complete_app.main resolves CompleteApplicationWindow from its module globals at
# runtime. Replace that one reference so all of its existing startup/data logic
# remains unchanged while the simulation tab gets the persistent subclass above.
_complete_app.CompleteApplicationWindow = CompleteApplicationWindow


def main() -> int:
    return _complete_app.main()


__all__ = ["CompleteApplicationWindow", "main", "_install_persistent_simulation_window"]
