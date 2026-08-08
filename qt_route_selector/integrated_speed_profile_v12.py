from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDoubleSpinBox

try:
    from . import speed_simulation as _speed_simulation
    from .driver_presets import install_complete_driver_profiles
except ImportError:
    import speed_simulation as _speed_simulation
    from driver_presets import install_complete_driver_profiles

# Install the complete profiles before importing the UI inheritance chain. The
# lower-level UI modules import DRIVER_PROFILES directly from speed_simulation,
# so doing this first guarantees that combo labels and profile_parameters() use
# one consistent source of truth.
install_complete_driver_profiles(_speed_simulation)

try:
    from .integrated_speed_profile_v11 import IntegratedSpeedProfileWindow as _V11Window
except ImportError:
    from integrated_speed_profile_v11 import IntegratedSpeedProfileWindow as _V11Window


class IntegratedSpeedProfileWindow(_V11Window):
    """V12: complete, internally consistent driver presets."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        super().__init__(route_path)
        self._fix_preset_numeric_precision()
        # Re-apply the active profile after precision is corrected so values such
        # as Rentner j_max=0.55 m/s³ are not rounded by a one-decimal spin box.
        current = str(self.profile_combo.currentData()) if hasattr(self, "profile_combo") else "normalo"
        if hasattr(self, "_apply_profile"):
            self._apply_profile(current)

    def _fix_preset_numeric_precision(self) -> None:
        precision = {
            "Kp": 2,
            "j_max_mps3": 2,
            "max_lat_accel_mps2": 2,
        }
        for key, decimals in precision.items():
            widget = self._control_widgets.get(key)
            if isinstance(widget, QDoubleSpinBox):
                widget.setDecimals(decimals)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.resize(1600, 900)
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
