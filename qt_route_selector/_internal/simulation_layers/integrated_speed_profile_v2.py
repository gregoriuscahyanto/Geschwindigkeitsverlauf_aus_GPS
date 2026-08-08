from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from pyproj import Transformer
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
)

try:
    import rasterio
except ImportError:  # pragma: no cover - handled in the UI
    rasterio = None

try:
    from .integrated_speed_profile import IntegratedSpeedProfileWindow as _BaseWindow
except ImportError:
    from integrated_speed_profile import IntegratedSpeedProfileWindow as _BaseWindow


_SETTING_GROUPS = {"Kurven", "Ampeln", "Überholen", "Rauschen", "Fahrzeug"}


class IntegratedSpeedProfileWindow(_BaseWindow):
    """Corrected integrated UI with scrollable settings and optional DEM heights."""

    def __init__(self, route_path: str | Path | None = None) -> None:
        self._dem_path: Path | None = None
        self._dem_cache_key: tuple[Any, ...] | None = None
        self._dem_cache_values: np.ndarray | None = None
        self.dem_status_label: QLabel | None = None
        super().__init__(route_path)
        self._install_dem_controls()
        self._refresh_scroll_area()
        if self._result is not None:
            self._update_plots()

    def _flatten_setting_tabs(self) -> None:
        super()._flatten_setting_tabs()
        for group in self.findChildren(QGroupBox):
            if group.title() not in _SETTING_GROUPS:
                continue
            group.setVisible(True)
            group.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            layout = group.layout()
            if layout is None:
                continue
            for index in range(layout.count()):
                widget = layout.itemAt(index).widget()
                if widget is not None:
                    widget.setVisible(True)
                    widget.setEnabled(True)
                    widget.setSizePolicy(
                        QSizePolicy.Policy.Expanding,
                        QSizePolicy.Policy.Preferred,
                    )
                    widget.adjustSize()
            layout.invalidate()
            layout.activate()
            group.adjustSize()

        self._refresh_scroll_area()

    def _refresh_scroll_area(self) -> None:
        for scroll in self.findChildren(QScrollArea):
            scroll.setWidgetResizable(True)
            scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            content = scroll.widget()
            if content is None:
                continue
            content.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            layout = content.layout()
            if layout is not None:
                layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
                layout.invalidate()
                layout.activate()
            content.adjustSize()

    def _install_dem_controls(self) -> None:
        route_group = next(
            (group for group in self.findChildren(QGroupBox) if group.title() == "Route"),
            None,
        )
        if route_group is None or route_group.layout() is None:
            return

        layout = route_group.layout()
        row = layout.rowCount() if hasattr(layout, "rowCount") else layout.count()

        title = QLabel("Höhenmodell")
        self.dem_status_label = QLabel(
            "Kein DEM gewählt. Automatisch geladene DEM-Kacheln werden hier ebenfalls verwendet."
        )
        self.dem_status_label.setWordWrap(True)

        choose_button = QPushButton("DEM / GeoTIFF wählen")
        choose_button.clicked.connect(self.choose_dem_file)
        clear_button = QPushButton("DEM entfernen")
        clear_button.clicked.connect(self.clear_dem_file)

        if hasattr(layout, "addWidget"):
            layout.addWidget(title, row, 0)
            layout.addWidget(self.dem_status_label, row, 1, 1, 2)
            layout.addWidget(choose_button, row + 1, 0, 1, 2)
            layout.addWidget(clear_button, row + 1, 2)

        route_group.adjustSize()
        self._refresh_scroll_area()

    def choose_dem_file(self) -> None:
        if rasterio is None:
            QMessageBox.warning(
                self,
                "Rasterio fehlt",
                "Für lokale Höhenmodelle wird rasterio benötigt.\n\n"
                "Installiere die aktualisierten Requirements mit:\n"
                "python -m pip install -r qt_route_selector\\requirements.txt",
            )
            return

        if self._dem_path is not None:
            start_path = self._dem_path if self._dem_path.is_dir() else self._dem_path.parent
            start_directory = str(start_path)
        else:
            start_directory = str(self._route_path.parent)
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Digitales Höhenmodell auswählen",
            start_directory,
            "GeoTIFF / DEM (*.tif *.tiff);;Alle Dateien (*)",
        )
        if not selected:
            return

        path = Path(selected).expanduser().resolve()
        try:
            with rasterio.open(path) as dataset:
                if dataset.count < 1:
                    raise ValueError("Das Raster besitzt kein Datenband.")
                if dataset.crs is None:
                    raise ValueError("Das Raster besitzt kein Koordinatensystem (CRS).")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Höhenmodell konnte nicht geöffnet werden",
                str(exc),
            )
            return

        self._dem_path = path
        self._invalidate_dem_cache()
        if self.dem_status_label is not None:
            self.dem_status_label.setText(f"DEM: {path}")
        if self._result is not None:
            self._update_plots()
        self.statusBar().showMessage(f"Höhenmodell geladen: {path.name}")

    def clear_dem_file(self) -> None:
        self._dem_path = None
        self._invalidate_dem_cache()
        if self.dem_status_label is not None:
            self.dem_status_label.setText(
                "Kein DEM gewählt. Automatisch geladene DEM-Kacheln werden hier ebenfalls verwendet."
            )
        if self._result is not None:
            self._update_plots()

    def _invalidate_dem_cache(self) -> None:
        self._dem_cache_key = None
        self._dem_cache_values = None

    def reload_route(self, *_args: Any, silent: bool = False) -> None:
        previous_token = (str(self._route_path), self._last_route_mtime_ns)
        super().reload_route(*_args, silent=silent)
        current_token = (str(self._route_path), self._last_route_mtime_ns)
        if current_token != previous_token:
            self._invalidate_dem_cache()

    def _route_sample_coordinates(
        self,
        sample_distance: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        if self._result is None:
            return None
        distance_data = self._result.get("distance", {})
        try:
            source_distance = np.asarray(distance_data["distance_m"], dtype=float)
            source_latitude = np.asarray(distance_data["latitude"], dtype=float)
            source_longitude = np.asarray(distance_data["longitude"], dtype=float)
        except (KeyError, TypeError, ValueError):
            return None
        if source_distance.size < 2:
            return None
        latitude = np.interp(sample_distance, source_distance, source_latitude)
        longitude = np.interp(sample_distance, source_distance, source_longitude)
        return latitude, longitude

    def _dem_raster_files(self) -> list[Path]:
        if self._dem_path is None:
            return []
        if self._dem_path.is_file():
            return [self._dem_path]
        if self._dem_path.is_dir():
            return sorted(self._dem_path.rglob("*.tif")) + sorted(self._dem_path.rglob("*.tiff"))
        return []

    @staticmethod
    def _raster_signature(files: list[Path]) -> tuple[int, int, int]:
        if not files:
            return (0, 0, 0)
        stats = [path.stat() for path in files]
        return (
            len(files),
            max(stat.st_mtime_ns for stat in stats),
            sum(stat.st_size for stat in stats),
        )

    def _sample_dem_rasters(
        self,
        files: list[Path],
        latitude: np.ndarray,
        longitude: np.ndarray,
    ) -> np.ndarray:
        elevation = np.full(latitude.shape, np.nan, dtype=float)
        for raster_path in files:
            missing = ~np.isfinite(elevation)
            if not np.any(missing):
                break
            with rasterio.open(raster_path) as dataset:
                if dataset.count < 1 or dataset.crs is None:
                    continue
                transformer = Transformer.from_crs(
                    "EPSG:4326",
                    dataset.crs,
                    always_xy=True,
                )
                missing_indexes = np.where(missing)[0]
                x_values, y_values = transformer.transform(
                    longitude[missing_indexes].tolist(),
                    latitude[missing_indexes].tolist(),
                )
                x_values = np.asarray(x_values, dtype=float)
                y_values = np.asarray(y_values, dtype=float)
                bounds = dataset.bounds
                in_bounds = (
                    (x_values >= bounds.left)
                    & (x_values <= bounds.right)
                    & (y_values >= bounds.bottom)
                    & (y_values <= bounds.top)
                )
                if not np.any(in_bounds):
                    continue
                selected_indexes = missing_indexes[in_bounds]
                selected_x = x_values[in_bounds]
                selected_y = y_values[in_bounds]
                scale = float(dataset.scales[0]) if dataset.scales else 1.0
                offset = float(dataset.offsets[0]) if dataset.offsets else 0.0
                for output_index, sample in zip(
                    selected_indexes,
                    dataset.sample(
                        zip(selected_x.tolist(), selected_y.tolist()),
                        indexes=1,
                        masked=True,
                    ),
                ):
                    raw_value = sample[0]
                    if np.ma.is_masked(raw_value):
                        continue
                    value = float(raw_value) * scale + offset
                    if math.isfinite(value):
                        elevation[int(output_index)] = value
        return elevation

    def _spatial_elevation(self, sample_distance: np.ndarray) -> np.ndarray:
        embedded = super()._spatial_elevation(sample_distance)
        if np.count_nonzero(np.isfinite(embedded)) >= 2:
            return embedded
        if self._dem_path is None or rasterio is None:
            return embedded

        coordinates = self._route_sample_coordinates(sample_distance)
        if coordinates is None:
            return embedded
        latitude, longitude = coordinates

        try:
            raster_files = self._dem_raster_files()
            signature = self._raster_signature(raster_files)
        except OSError:
            return embedded
        if not raster_files:
            if self.dem_status_label is not None:
                self.dem_status_label.setText(
                    f"DEM-Ordner enthält noch keine GeoTIFF-Kacheln: {self._dem_path}"
                )
            return embedded

        cache_key = (
            str(self._dem_path),
            signature,
            str(self._route_path),
            self._last_route_mtime_ns,
            len(sample_distance),
            round(float(sample_distance[0]), 3),
            round(float(sample_distance[-1]), 3),
        )
        if self._dem_cache_key == cache_key and self._dem_cache_values is not None:
            return self._dem_cache_values.copy()

        try:
            elevation = self._sample_dem_rasters(raster_files, latitude, longitude)
        except Exception as exc:
            if self.dem_status_label is not None:
                self.dem_status_label.setText(
                    f"DEM konnte nicht ausgewertet werden: {exc}"
                )
            return embedded

        finite = np.isfinite(elevation)
        finite_count = int(np.count_nonzero(finite))
        if finite_count >= 2:
            elevation = np.interp(
                sample_distance,
                sample_distance[finite],
                elevation[finite],
            )
            if self.dem_status_label is not None:
                source_name = self._dem_path.name
                self.dem_status_label.setText(
                    f"DEM: {source_name} – {finite_count}/{len(elevation)} Punkte aus "
                    f"{len(raster_files)} Rasterkachel(n) gelesen"
                )
        else:
            if self.dem_status_label is not None:
                self.dem_status_label.setText(
                    f"DEM: {self._dem_path.name} – Route liegt außerhalb der vorhandenen Rasterkacheln oder enthält NoData"
                )
            elevation = embedded

        self._dem_cache_key = cache_key
        self._dem_cache_values = elevation.copy()
        return elevation


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = IntegratedSpeedProfileWindow(Path.cwd() / "route_result.json")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
