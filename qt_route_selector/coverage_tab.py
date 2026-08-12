from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    from .auto_region import (
        DATASET_ORDER,
        coverage_snapshot,
        dataset_storage_state,
    )
except ImportError:
    from auto_region import (
        DATASET_ORDER,
        coverage_snapshot,
        dataset_storage_state,
    )


APP_DIR = Path(__file__).resolve().parent


class CoverageTab(QWidget):
    """Local-only overview of datasets that have both POLY and PBF files."""

    def __init__(
        self,
        data_root: str | Path,
        *,
        active_dataset_key: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.data_root = Path(data_root).expanduser().resolve()
        self.active_dataset_key = active_dataset_key

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(10)

        self.map_widget = QQuickWidget(self)
        self.map_widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.map_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.map_widget.setMinimumSize(650, 500)
        self.map_widget.setSource(QUrl.fromLocalFile(str(APP_DIR / "coverage_map.qml")))
        if self.map_widget.status() == QQuickWidget.Status.Error:
            errors = "\n".join(error.toString() for error in self.map_widget.errors())
            raise RuntimeError(f"Datenabdeckungs-Karte konnte nicht geladen werden:\n{errors}")
        root_layout.addWidget(self.map_widget, 1)

        side = QFrame(self)
        side.setFrameShape(QFrame.Shape.StyledPanel)
        side.setMinimumWidth(330)
        side.setMaximumWidth(410)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(14, 14, 14, 14)
        side_layout.setSpacing(10)

        title = QLabel("Lokale Datenabdeckung", side)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        side_layout.addWidget(title)

        intro = QLabel(
            "Angezeigt werden nur Gebiete, für die sowohl die Gebietsgrenze (.poly) "
            "als auch die OSM-PBF-Datei lokal im data-Ordner vorhanden sind. "
            "Es wird in diesem Tab nichts zusätzlich heruntergeladen.",
            side,
        )
        intro.setWordWrap(True)
        side_layout.addWidget(intro)

        legend = QLabel(
            "<b>Kartenfarben</b><br>"
            "<span style='color:#175a9e'>■</span> OSM-PBF vorhanden<br>"
            "<span style='color:#216b2d'>■</span> Routing-GPKG bereit<br>"
            "<span style='color:#9b5b00'>■</span> GPKG älter als PBF",
            side,
        )
        legend.setTextFormat(Qt.TextFormat.RichText)
        legend.setWordWrap(True)
        side_layout.addWidget(legend)

        divider = QFrame(side)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        side_layout.addWidget(divider)

        status_title = QLabel("Verfügbare Gebiete", side)
        status_title.setStyleSheet("font-weight: 700;")
        side_layout.addWidget(status_title)

        self.inventory_label = QLabel(side)
        self.inventory_label.setWordWrap(True)
        self.inventory_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.inventory_label.setStyleSheet("font-family: monospace;")
        side_layout.addWidget(self.inventory_label)

        self.note_label = QLabel(side)
        self.note_label.setWordWrap(True)
        self.note_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        side_layout.addWidget(self.note_label)
        side_layout.addStretch(1)

        root_layout.addWidget(side)
        self.refresh(active_dataset_key=active_dataset_key)

    @staticmethod
    def _mark(value: bool) -> str:
        return "✓" if value else "–"

    @staticmethod
    def _is_available(state: dict[str, object]) -> bool:
        return bool(state["poly_ready"]) and bool(state["pbf_ready"])

    def refresh(self, *, active_dataset_key: str | None = None) -> None:
        if active_dataset_key is not None:
            self.active_dataset_key = active_dataset_key

        # coverage_snapshot also contains regions for which only a .poly boundary
        # exists. Those are useful for automatic region detection, but they are
        # not usable routing datasets and therefore must not appear in this tab.
        areas = [
            area
            for area in coverage_snapshot(
                self.data_root,
                active_dataset_key=self.active_dataset_key,
            )
            if str(area.get("level", "")) != "poly"
        ]
        root_object = self.map_widget.rootObject()
        if root_object is not None:
            root_object.setProperty("coverageAreas", areas)

        lines: list[str] = []
        available_count = 0
        for dataset_key in DATASET_ORDER:
            state = dataset_storage_state(dataset_key, self.data_root)
            if not self._is_available(state):
                continue

            available_count += 1
            active = "▶ " if dataset_key == self.active_dataset_key else "  "
            lines.append(
                f"{active}{state['label']}\n"
                f"    POLY {self._mark(bool(state['poly_ready']))}   "
                f"PBF {self._mark(bool(state['pbf_ready']))}   "
                f"GPKG {self._mark(bool(state['gpkg_ready']))}"
            )

        if lines:
            self.inventory_label.setText("\n\n".join(lines))
        else:
            self.inventory_label.setText("Keine verfügbaren Gebiete")

        if available_count == 0:
            self.note_label.setText(
                "Ein Gebiet erscheint hier automatisch, sobald seine .poly- und "
                ".osm.pbf-Datei gemeinsam im lokalen data/osm-Ordner liegen."
            )
        else:
            self.note_label.setText(
                "▶ kennzeichnet den aktuell fürs Routing aktivierten Datensatz. "
                "Neue Gebiete erscheinen automatisch, sobald POLY und PBF lokal vorhanden sind."
            )
