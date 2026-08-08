from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QSplitter, QVBoxLayout

try:
    from ._internal.simulation_layers import integrated_speed_profile as _base_layer
    from ._internal.simulation_layers.integrated_speed_profile import _osm_only_event_positions
    from ._internal.simulation_layers.integrated_speed_profile_v16 import (
        IntegratedSpeedProfileWindow as _CurrentWindow,
    )
except ImportError:
    from _internal.simulation_layers import integrated_speed_profile as _base_layer
    from _internal.simulation_layers.integrated_speed_profile import _osm_only_event_positions
    from _internal.simulation_layers.integrated_speed_profile_v16 import (
        IntegratedSpeedProfileWindow as _CurrentWindow,
    )

# The implementation layers live below _internal, while QML resources remain
# next to the public application modules.
_base_layer.APP_DIR = Path(__file__).resolve().parent


class IntegratedSpeedProfileWindow(_CurrentWindow):
    """Public simulation window with the compact current application shell."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        super().__init__(route_path)
        self._merge_summary_cards()

    def _merge_summary_cards(self) -> None:
        """Show route statistics and energy in one responsive summary card."""
        outer = self.centralWidget()
        if not isinstance(outer, QSplitter) or outer.count() < 2:
            return
        plot_root = outer.widget(1)
        layout = plot_root.layout()
        if not isinstance(layout, QVBoxLayout):
            return

        summary = getattr(self, "summary_label", None)
        energy = getattr(self, "energy_header_label", None)
        if not isinstance(summary, QLabel) or not isinstance(energy, QLabel):
            return
        if getattr(self, "overview_card", None) is not None:
            return

        positions = [index for index in (layout.indexOf(summary), layout.indexOf(energy)) if index >= 0]
        insert_at = min(positions) if positions else 0
        layout.removeWidget(summary)
        layout.removeWidget(energy)

        card = QFrame(plot_root)
        card.setObjectName("overviewCard")
        card.setStyleSheet(
            "QFrame#overviewCard { background:palette(base); border:1px solid palette(midlight); "
            "border-radius:10px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 9, 14, 9)
        card_layout.setSpacing(5)

        for label in (summary, energy):
            label.setParent(card)
            label.setStyleSheet("QLabel { border:0; background:transparent; padding:0; }")
            label.setWordWrap(True)
            card_layout.addWidget(label)

        layout.insertWidget(insert_at, card)
        self.overview_card = card


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.resize(1600, 900)
    window.show()
    QTimer.singleShot(120, lambda: window.reload_route(silent=True))
    return app.exec()


__all__ = ["IntegratedSpeedProfileWindow", "_osm_only_event_positions", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
