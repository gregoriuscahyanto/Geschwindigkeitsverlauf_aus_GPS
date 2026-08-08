from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

try:
    from .integrated_speed_profile_v5 import IntegratedSpeedProfileWindow as _V5Window
except ImportError:
    from integrated_speed_profile_v5 import IntegratedSpeedProfileWindow as _V5Window


class IntegratedSpeedProfileWindow(_V5Window):
    """V6: explicit integrated drive, recuperation and net-energy balance."""

    @staticmethod
    def _energy_values(data: dict[str, object] | None) -> tuple[float, float, float]:
        if not data:
            return 0.0, 0.0, 0.0
        drive = float(data.get("traction_energy_kwh", 0.0) or 0.0)
        recuperation = float(data.get("recuperation_energy_kwh", 0.0) or 0.0)
        net = float(data.get("net_energy_kwh", drive - recuperation) or 0.0)
        return drive, recuperation, net

    def _update_energy_summary(self) -> None:
        if not hasattr(self, "power_summary_label"):
            return

        if self._comparison_configs and self._comparison_resistance:
            rows: list[str] = []
            names = self._comparison_names or [
                "Aktuell",
                *[str(item["name"]) for item in self._comparison_configs],
            ]
            for index, data in enumerate(self._comparison_resistance):
                drive, recuperation, net = self._energy_values(data)
                name = names[index] if index < len(names) else f"Konfiguration {index + 1}"
                rows.append(
                    f"<b>{name}</b>: Antrieb {drive:.2f} kWh · "
                    f"Rekuperation {recuperation:.2f} kWh · "
                    f"Netto <b>{net:.2f} kWh</b>"
                )
            self.power_summary_label.setText(
                "<b>Energiebilanz aus ∫P·dt</b> — ideale Rekuperation ohne Leistungs-/Kapazitätslimit, η = 100 %<br>"
                + "<br>".join(rows)
            )
            return

        data = self._resistance_time_data
        if not data:
            return
        drive, recuperation, net = self._energy_values(data)
        p95 = float(data.get("p95_positive_kw", 0.0) or 0.0)
        pmax = float(data.get("maximum_kw", 0.0) or 0.0)
        pmin = float(data.get("minimum_kw", 0.0) or 0.0)
        self.power_summary_label.setText(
            "<b>Energiebilanz aus ∫P·dt</b> — ideale, unbegrenzte Rekuperation (η = 100 %)<br>"
            f"Antriebsenergie: <b>{drive:.2f} kWh</b> &nbsp; | &nbsp; "
            f"Rekuperationsenergie: <b>{recuperation:.2f} kWh</b> &nbsp; | &nbsp; "
            f"Nettoenergie: <b>{net:.2f} kWh</b><br>"
            f"P95 positiv: {p95:.1f} kW &nbsp; | &nbsp; "
            f"Pmax: {pmax:.1f} kW &nbsp; | &nbsp; Pmin: {pmin:.1f} kW"
        )

    def _plot_cumulative_collective(self) -> None:
        super()._plot_cumulative_collective()
        self._update_energy_summary()

    def _update_comparison_summary(self) -> None:
        super()._update_comparison_summary()
        self._update_energy_summary()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
